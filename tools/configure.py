"""Native build metadata generator. Never executes configure, make, or a shell.

The upstream declarative dependency lists and object lists remain the source of
truth. CMake owns compiler detection, dependency discovery and every build rule.
Only the documented assignment/conditional subset is read, never evaluated as
code. Unknown selected source expressions fail closed instead of dropping code.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

LIBS = ("avutil", "swresample", "avcodec", "avformat", "swscale", "avfilter", "avdevice")
REGISTRIES = {
    "decoder": ("libavcodec/allcodecs.c", "FFCodec", "decoder"),
    "encoder": ("libavcodec/allcodecs.c", "FFCodec", "encoder"),
    "parser": ("libavcodec/parsers.c", "FFCodecParser", "parser"),
    "bsf": ("libavcodec/bitstream_filters.c", "FFBitStreamFilter", "bsf"),
    "hwaccel": ("libavcodec/hwaccels.h", "FFHWAccel", "hwaccel"),
    "demuxer": ("libavformat/allformats.c", "FFInputFormat", "demuxer"),
    "muxer": ("libavformat/allformats.c", "FFOutputFormat", "muxer"),
    "protocol": ("libavformat/protocols.c", "URLProtocol", "protocol"),
    "indev": ("libavdevice/alldevices.c", "FFInputFormat", "demuxer"),
    "outdev": ("libavdevice/alldevices.c", "FFOutputFormat", "muxer"),
    "filter": ("libavfilter/allfilters.c", "FFFilter", "filter"),
}
PROFILES = {
    "full": {},
    "minimal": {kind: "NONE" for kind in REGISTRIES},
    "playback": {
        "decoder": "h264;hevc;av1;vp9;aac;mp3;opus;vorbis;flac;pcm_s16le",
        "demuxer": "mov;matroska;ogg;mp3;flac;wav;aac;mpegts",
        "parser": "h264;hevc;av1;vp9;aac;mpegaudio;opus;vorbis;flac",
        "protocol": "file;pipe;http;https;tcp;udp;rtp",
        "filter": "aresample;scale;aformat;format;anull;null",
    },
    "transcode": {
        "decoder": "h264;hevc;av1;vp9;aac;mp3;opus;flac;pcm_s16le;rawvideo",
        "encoder": "aac;flac;opus;mpeg4;pcm_s16le;rawvideo;ffv1;wrapped_avframe",
        "demuxer": "mov;matroska;wav;mp3;flac;aac;mpegts;rawvideo",
        "muxer": "mp4;matroska;wav;flac;adts;mpegts;null;framehash",
        "parser": "h264;hevc;av1;vp9;aac;mpegaudio;opus;flac",
        "protocol": "file;pipe;http;https;tcp;udp",
        "filter": "aresample;scale;fps;aformat;format;anull;null;testsrc2;sine",
    },
}


def write_if_changed(path: Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != data:
        path.write_text(data, encoding="utf-8", newline="\n")


class Metadata:
    def __init__(self, source: Path):
        self.source = source
        self.text = (source / "configure").read_text(encoding="utf-8")
        # Static assignments only. Shell command substitutions are handled only
        # for the add_suffix list constructor below; no shell is launched.
        self.variables = dict(re.findall(r'^([A-Za-z_0-9]+)="([^"`]*?)"', self.text, re.M))
        self.components = {}
        self.groups = {}
        for kind, (file, ctype, suffix) in REGISTRIES.items():
            symbols = []
            for line in (source / file).read_text(encoding="utf-8").splitlines():
                tokens = line.removesuffix(";").split()
                if tokens[:2] == ["extern", "const"] and ctype in tokens:
                    symbols.append(tokens[-1])
            group = []
            for symbol in symbols:
                if kind == "filter":
                    name = symbol.split("_", 2)[2] + "_filter"
                else:
                    if not symbol.endswith("_" + suffix):
                        continue
                    name = symbol[3:-len(suffix)] + kind
                # These four buffer endpoints and two graph endpoints are
                # unconditionally provided by the base libraries upstream.
                if kind == "bsf" and name in ("source_bsf", "sink_bsf"):
                    continue
                self.components[name] = symbol
                group.append(name)
            self.groups[kind] = list(dict.fromkeys(group))
            self.variables[kind.upper() + "_LIST"] = " ".join(group)
        self.rules = {}
        for key, value in self.variables.items():
            for suffix in ("deps_any", "deps", "select", "suggest", "conflict", "if_any", "if"):
                if key.endswith("_" + suffix):
                    name = key[:-len(suffix)-1].lower()
                    self.rules.setdefault(name, {})[suffix] = self.expand(value).lower().split()
                    break
        self.extra = set(self.words("CONFIG_EXTRA"))

    def expand(self, text, stack=()):
        def suffix(match):
            return " ".join(x + match[1] for x in self.expand(match[2], stack).split())
        text = re.sub(r"\$\(add_suffix\s+(\w+)\s+([^()]+)\)", suffix, text)
        def variable(match):
            key = match[1] or match[2]
            if key in stack:
                raise ValueError("Cyclic metadata variable: " + key)
            return self.expand(self.variables.get(key, ""), (*stack, key))
        return re.sub(r"\$\{(\w+)\}|\$(\w+)", variable, text)

    def words(self, key):
        return self.expand(self.variables.get(key, "")).lower().split()


class Resolver:
    def __init__(self, meta, facts, blocked, roots):
        self.meta, self.facts, self.blocked, self.roots = meta, facts, blocked, set(roots)
        selected_helpers = {dep for rule in meta.rules.values() for dep in rule.get("select", [])}
        # CONFIG_EXTRA mixes build helpers with probed API capabilities (e.g.
        # libx262 and d3d12_motion_estimator). A capability is never available
        # merely because it has a CONFIG_ macro.
        helpers = meta.extra & (selected_helpers | set(meta.rules))
        self.mutable = set(meta.components) | helpers | set(meta.words("SUBSYSTEM_LIST"))
        self.mutable |= set(meta.words("PROGRAM_LIST"))
        self.status, self.reason, self.active = {}, {}, set()

    def possible(self, name, trail=()):
        if name.startswith("!"):
            return not self.possible(name[1:], trail)
        if name in self.blocked:
            self.reason[name] = "explicitly disabled"
            return False
        if name in self.facts:
            if not self.facts[name]:
                self.reason[name] = "not enabled or not detected by CMake"
            return bool(self.facts[name])
        if name in self.status:
            return self.status[name]
        if name in trail:
            raise ValueError("Dependency cycle: " + " -> ".join((*trail, name)))
        if name not in self.mutable:
            self.reason[name] = "dependency has no successful platform/package probe"
            return False
        trail = (*trail, name)
        rules = self.meta.rules.get(name, {})
        for dep in rules.get("deps", []) + rules.get("select", []):
            if not self.possible(dep, trail):
                self.reason[name] = f"requires {dep}: {self.reason.get(dep, 'unavailable')}"
                self.status[name] = False
                return False
        any_deps = rules.get("deps_any", [])
        if any_deps and not any(self.possible(x, trail) for x in any_deps):
            self.reason[name] = "requires one of: " + ", ".join(any_deps)
            self.status[name] = False
            return False
        for dep in rules.get("conflict", []):
            if (dep in self.roots or self.facts.get(dep)) and self.possible(dep, trail):
                self.reason[name] = "conflicts with " + dep
                self.status[name] = False
                return False
        self.status[name] = True
        return True

    def enable(self, name):
        if name.startswith("!") or name in self.active or not self.possible(name):
            return
        self.active.add(name)
        rules = self.meta.rules.get(name, {})
        for dep in rules.get("deps", []) + rules.get("select", []) + rules.get("suggest", []):
            self.enable(dep)
        for dep in rules.get("deps_any", []):
            if self.possible(dep):
                self.enable(dep)


class ObjectLists:
    """Reader for the upstream declarative object/header list subset of make."""
    def __init__(self, source, flags, arch):
        self.source, self.flags, self.arch = source, flags, arch
        self.vars = {"SRC_PATH": source.as_posix(), "ARCH": arch, "COMPAT_OBJS": ""}
        self.inputs = set()

    def expand(self, value, trail=()):
        def replace(match):
            expr = match[1]
            if expr.startswith("if "):
                parts = expr[3:].split(",", 2)
                return parts[1] if parts[0].strip() else (parts[2] if len(parts) > 2 else "")
            if expr.startswith(("CONFIG_", "HAVE_", "ARCH_", "!CONFIG_", "!HAVE_")):
                inverse = expr.startswith("!")
                return "yes" if bool(self.flags.get(expr.lstrip("!"), 0)) != inverse else ""
            if expr in trail:
                raise ValueError("Recursive object list: " + expr)
            if ":%=" in expr:
                var, pattern = expr.split(":%=", 1)
                return " ".join(pattern.replace("%", x) for x in self.expand(self.vars.get(var, ""), (*trail, expr)).split())
            if expr not in self.vars and not expr.startswith("EMMS_OBJS_"):
                raise ValueError("Unknown variable in selected object list: " + expr)
            return self.expand(self.vars.get(expr, ""), (*trail, expr))
        while "$" in value:
            updated = re.sub(r"\$\(([^()]*)\)", replace, value)
            if updated == value:
                raise ValueError("Unsupported selected object expression: " + value)
            value = updated
        return value

    def read(self, file):
        if not file.exists():
            return
        self.inputs.add(file)
        contents = file.read_text(encoding="utf-8").replace("\\\n", " ")
        condition = [True]
        in_define = False
        for raw in contents.splitlines():
            if raw.startswith("\t"):
                continue
            line = raw.split("#", 1)[0].strip()
            if line.startswith("define "):
                in_define = True
            if line == "endef":
                in_define = False
                continue
            if in_define:
                continue
            if line.startswith(("ifdef ", "ifndef ")):
                key = line.split(None, 1)[1]
                value = bool(self.flags.get(key, self.vars.get(key, "")))
                condition.append(condition[-1] and (not value if line.startswith("ifndef") else value))
                continue
            if line.startswith(("ifeq ", "ifneq ")):
                args = self.expand(line[line.index("(") + 1:-1]).split(",", 1)
                value = args[0].strip() == args[1].strip()
                condition.append(condition[-1] and (not value if line.startswith("ifneq") else value))
                continue
            if line == "else":
                condition[-1] = condition[-2] and not condition[-1]
                continue
            if line == "endif":
                condition.pop()
                continue
            if not condition[-1]:
                continue
            if line.startswith(("include ", "-include ")):
                self.read(Path(self.expand(line.split(None, 1)[1])))
                continue
            match = re.match(r"^([^\s=]+)\s*(\+=|:=|\?=|=)\s*(.*)$", line)
            if not match:
                continue
            key, op, value = match.groups()
            # Ignore rule machinery and test-only metadata, including generated
            # table rules: this build uses upstream's runtime table generation.
            if "OBJS" not in key and not key.startswith(("HEADERS", "EMMS")):
                continue
            key = self.expand(key)
            if op == "+=":
                self.vars[key] = self.vars.get(key, "") + " " + value
            elif op != "?=" or key not in self.vars:
                self.vars[key] = self.expand(value) if op == ":=" else value

    def values(self, key):
        return self.expand(self.vars.get(key, "") + " " + self.vars.get(key + "-yes", "")).split()


def parse_selections(meta, options):
    profile = options["profile"]
    if profile not in PROFILES:
        raise ValueError("Unknown profile: " + profile)
    roots, explicit = set(), set()
    for kind, group in meta.groups.items():
        value = options["components"].get(kind, "AUTO")
        if value == "AUTO":
            value = PROFILES[profile].get(kind, "ALL" if profile == "full" else "NONE")
        else:
            explicit.update(group if value == "ALL" else [])
        if value == "ALL":
            roots.update(group)
        elif value != "NONE":
            for token in value.replace(";", " ").replace(",", " ").split():
                name = token if token.endswith("_" + kind) else token + "_" + kind
                if name not in group:
                    raise ValueError(f"Unknown {kind}: {token}. Use tools/configure.py --list {kind}s")
                roots.add(name)
                explicit.add(name)
    return roots, explicit


def generate(source, output, options, facts):
    meta = Metadata(source)
    roots, explicit = parse_selections(meta, options)
    blocked = set(options.get("disable", "").replace(";", " ").replace(",", " ").split())
    unknown = blocked - set(meta.components) - set(meta.words("CONFIG_LIST")) - meta.extra
    if unknown:
        raise ValueError("Unknown disabled components: " + ", ".join(sorted(unknown)))
    for kind, group in meta.groups.items():
        facts[kind + "s"] = bool(roots.intersection(group))
    # Default library subsystems are upstream defaults, not component cropping.
    for name in meta.words("SUBSYSTEM_LIST"):
        if name not in facts:
            roots.add(name)
    roots.update(("faandct", "faanidct", "frame_thread_encoder"))
    if options["programs"]:
        roots.update(("ffmpeg", "ffprobe"))
        explicit.update(("ffmpeg", "ffprobe"))
        if facts.get("sdl2"):
            roots.add("ffplay")
    for name, enabled in facts.items():
        if enabled:
            roots.add(name)
    # Disable component groups belonging to libraries disabled by the user.
    owners = {"decoder": "avcodec", "encoder": "avcodec", "parser": "avcodec", "bsf": "avcodec", "hwaccel": "avcodec",
              "muxer": "avformat", "demuxer": "avformat", "protocol": "avformat",
              "filter": "avfilter", "indev": "avdevice", "outdev": "avdevice"}
    for kind, owner in owners.items():
        if not facts.get(owner):
            blocked.update(meta.groups[kind])
    resolver = Resolver(meta, facts, blocked, roots)
    for name in sorted(roots):
        resolver.enable(name)
    failed = explicit - resolver.active
    if failed:
        raise ValueError("Requested components unavailable:\n" + "\n".join(
            f"  {n}: {resolver.reason.get(n, 'disabled')}" for n in sorted(failed)))
    enabled = resolver.active
    for name in LIBS:
        if name in enabled:
            for dependency in meta.rules.get(name, {}).get("deps", []):
                if dependency not in enabled:
                    raise ValueError(f"lib{name} requires lib{dependency}")
    flags = {}
    for prefix, keys in (("ARCH_", meta.words("ARCH_LIST")), ("HAVE_", meta.words("HAVE_LIST")),
                         ("CONFIG_", meta.words("CONFIG_LIST") + meta.words("CONFIG_EXTRA") + list(meta.components))):
        for name in keys:
            if name.isidentifier():
                flags[prefix + name.upper()] = int(name in enabled)
    # Facts can include probes added upstream but not yet in HAVE_LIST.
    for name, value in options["macros"].items():
        flags[name] = int(value and name.split("_", 1)[1].lower() in enabled)
    for kind, group in meta.groups.items():
        flags["CONFIG_" + kind.upper() + "S"] = int(bool(enabled.intersection(group)))
    asm_features = meta.words("ARCH_EXT_LIST_X86")
    if facts.get("x86asm"):
        for feature in asm_features:
            flags["HAVE_" + feature.upper()] = 1
            flags["HAVE_" + feature.upper() + "_EXTERNAL"] = 1
        flags.update(HAVE_SIMD_ALIGN_16=1, HAVE_SIMD_ALIGN_32=1, HAVE_SIMD_ALIGN_64=1)
    # Public configuration must match the internal one.
    public = "#ifndef AVUTIL_AVCONFIG_H\n#define AVUTIL_AVCONFIG_H\n"
    public += "".join(f"#define AV_HAVE_{n.upper()} {flags.get('HAVE_' + n.upper(), 0)}\n" for n in meta.words("HAVE_LIST_PUB"))
    write_if_changed(output / "libavutil/avconfig.h", public + "#endif\n")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    write_if_changed(output / "libavutil/ffversion.h", f'#define FFMPEG_VERSION "{revision}-cmake"\n')
    license_name = "GPL version 3 or later" if {"gpl", "version3"} <= enabled else "GPL version 2 or later" if "gpl" in enabled else "LGPL version 3 or later" if "version3" in enabled else "LGPL version 2.1 or later"
    config = "#ifndef FFMPEG_CONFIG_H\n#define FFMPEG_CONFIG_H\n"
    public_options = {k: v for k, v in options.items() if k != "macros"}
    strings = {"FFMPEG_CONFIGURATION": "native-cmake " + json.dumps(public_options, sort_keys=True), "FFMPEG_LICENSE": license_name,
               "FFMPEG_DATADIR": options["datadir"], "AVCONV_DATADIR": options["datadir"], "CC_IDENT": options["compiler"],
               "EXTERN_PREFIX": "_" if options["system"] == "Darwin" else "", "BUILDSUF": "", "SLIBSUF": options["shared_suffix"]}
    config += "".join(f"#define {key} {json.dumps(value, ensure_ascii=True)}\n" for key, value in strings.items())
    config += f'#define OS_NAME {options["system"].lower()}\n#define EXTERN_ASM {strings["EXTERN_PREFIX"]}\n'
    config += "#define CONFIG_THIS_YEAR 2026\n#define SWS_MAX_FILTER_SIZE 256\n#define ASSERT_LEVEL 0\n"
    if options["arch"] == "aarch64":
        config += "#define AS_ARCH_LEVEL armv8-a\n"
    config += "".join(f"#define {key} {value}\n" for key, value in sorted(flags.items()) if key not in {"CONFIG_" + n.upper() for n in meta.components})
    config += "#endif\n"
    write_if_changed(output / "config.h", config)
    component_config = "".join(f"#define CONFIG_{n.upper()} {int(n in enabled)}\n" for n in sorted(meta.components))
    write_if_changed(output / "config_components.h", "#pragma once\n" + component_config)
    write_if_changed(output / "config.asm", "".join(f"%define {key} {value}\n" for key, value in sorted(flags.items())))
    write_if_changed(output / "config_components.asm", component_config.replace("#define", "%define"))
    for kinds, path, ctype, array in (
        (("encoder", "decoder"), "libavcodec/codec_list.c", "FFCodec", "codec_list"),
        (("parser",), "libavcodec/parser_list.c", "FFCodecParser", "parser_list"),
        (("bsf",), "libavcodec/bsf_list.c", "FFBitStreamFilter", "bitstream_filters"),
        (("filter",), "libavfilter/filter_list.c", "FFFilter", "filter_list"),
        (("demuxer",), "libavformat/demuxer_list.c", "FFInputFormat", "demuxer_list"),
        (("muxer",), "libavformat/muxer_list.c", "FFOutputFormat", "muxer_list"),
        (("protocol",), "libavformat/protocol_list.c", "URLProtocol", "url_protocols"),
        (("indev",), "libavdevice/indev_list.c", "FFInputFormat", "indev_list"),
        (("outdev",), "libavdevice/outdev_list.c", "FFOutputFormat", "outdev_list"),
    ):
        symbols = [meta.components[n] for kind in kinds for n in meta.groups[kind] if n in enabled]
        if kinds == ("filter",):
            symbols += ["ff_asrc_abuffer", "ff_vsrc_buffer", "ff_asink_abuffer", "ff_vsink_buffer"]
        if kinds == ("bsf",):
            symbols += ["ff_source_bsf", "ff_sink_bsf"]
        write_if_changed(output / path, f"static const {ctype} * const {array}[] = {{\n" + "".join(f"    &{s},\n" for s in dict.fromkeys(symbols)) + "    NULL\n};\n")
    cmake = ["# Generated native CMake source manifest; do not edit."]
    all_inputs = {source / "configure"} | {source / v[0] for v in REGISTRIES.values()}
    def emit_list(key, values):
        cmake.append(f"set({key}\n" + "".join(f'  "{v}"\n' for v in values) + ")")
    for lib in LIBS:
        if lib not in enabled:
            continue
        lists = ObjectLists(source, flags, options["arch"])
        lists.read(source / f"lib{lib}/Makefile")
        lists.read(source / f'lib{lib}/{options["arch"]}/Makefile')
        if facts.get("neon"):
            lists.read(source / f"lib{lib}/neon/Makefile")
        all_inputs.update(lists.inputs)
        objects = lists.values("OBJS")
        objects += lists.values("SHLIBOBJS" if facts.get("shared") else "STLIBOBJS")
        for feature in ("x86asm", "armv8", "neon", "sve", "sve2", "sme", "sme2"):
            if facts.get(feature):
                objects += lists.values(feature.upper() + "-OBJS")
        if flags.get("HAVE_MMX_INLINE"):
            objects += lists.values("MMX-OBJS")
        sources, assembly = [], []
        for obj in sorted(set(objects)):
            if not obj.endswith(".o"):
                raise ValueError(f"Unsupported selected object in lib{lib}: {obj}")
            stem = obj[:-2]
            if lib == "swscale" and stem == "aarch64/ops_neon.gen":
                sources.append((output / "libswscale/aarch64/ops_neon.gen.S").as_posix())
                continue
            candidates = [source / f"lib{lib}/{stem}{ext}" for ext in (".c", ".cpp", ".m", ".S", ".asm")]
            if not any(p.exists() for p in candidates) and "/" not in stem:
                candidates += [source / f"libavutil/{stem}.c", source / f"libavcodec/{stem}.c"]
            found = next((p for p in candidates if p.exists()), None)
            if found is None:
                raise ValueError(f"No native build rule for lib{lib}/{obj}")
            (assembly if found.suffix == ".asm" else sources).append(found.as_posix())
        emit_list(f"FF_SOURCES_{lib}", sorted(set(sources)))
        emit_list(f"FF_ASM_{lib}", sorted(set(assembly)))
        emit_list(f"FF_HEADERS_{lib}", [str(source / f"lib{lib}" / p).replace("\\", "/") for p in lists.values("HEADERS")])
        version_file = source / f"lib{lib}" / ("version.h" if lib == "avutil" else "version_major.h")
        all_inputs.add(version_file)
        major = next(line.split()[2] for line in version_file.read_text().splitlines()
                     if line.startswith(f"#define LIB{lib.upper()}_VERSION_MAJOR "))
        emit_list(f"FF_MAJOR_{lib}", [major])
        if options["system"] == "Linux" and facts.get("shared"):
            version_script = source / f"lib{lib}/lib{lib}.v"
            all_inputs.add(version_script)
            write_if_changed(output / f"lib{lib}.ver", version_script.read_text().replace("MAJOR", major))
    lists = ObjectLists(source, flags, options["arch"])
    lists.read(source / "fftools/Makefile")
    all_inputs.update(lists.inputs)
    for program in ("ffmpeg", "ffprobe", "ffplay"):
        if program not in enabled:
            continue
        objects = lists.values("OBJS-" + program) + [f"fftools/{p}.o" for p in (program, "cmdutils", "opt_common")]
        program_sources = []
        for obj in sorted(set(objects)):
            path = source / (obj[:-2] + ".c")
            if not path.exists():
                resource = source / obj[:-2]
                if resource.suffix not in (".html", ".css") or not resource.exists():
                    raise ValueError("Unsupported program source: " + obj)
                all_inputs.add(resource)
                data = resource.read_bytes()
                symbol = "ff_" + resource.name.replace(".", "_")
                path = output / (obj[:-2] + ".c")
                write_if_changed(path, f"const unsigned char {symbol}_data[] = {{\n" + ",\n".join(",".join(map(str, data[i:i+32])) for i in range(0, len(data), 32)) + f"\n,0}};\nconst unsigned int {symbol}_len = {len(data)};\n")
            program_sources.append(path.as_posix())
        emit_list("FF_SOURCES_" + program, program_sources)
    emit_list("FF_ENABLED_LIBS", [n for n in LIBS if n in enabled])
    emit_list("FF_ENABLED_PROGRAMS", [n for n in ("ffmpeg", "ffprobe", "ffplay") if n in enabled])
    emit_list("FF_METADATA_INPUTS", [p.as_posix() for p in sorted(all_inputs)])
    write_if_changed(output / "sources.cmake", "\n".join(cmake) + "\n")
    report = {"revision": revision, "profile": options["profile"], "license": license_name,
              "libraries": [n for n in LIBS if n in enabled],
              "programs": [n for n in ("ffmpeg", "ffprobe", "ffplay") if n in enabled],
              "unavailable_programs": {}, "components": {}, "disabled": {}}
    for program in ("ffmpeg", "ffprobe", "ffplay"):
        if program not in enabled:
            resolver.possible(program)
            report["unavailable_programs"][program] = resolver.reason.get(program, "programs disabled by option")
    for kind, group in meta.groups.items():
        report["components"][kind + "s"] = [n[:-len(kind)-1] for n in group if n in enabled]
        for name in group:
            if name not in enabled:
                resolver.possible(name)
                report["disabled"][name] = resolver.reason.get(name, "not requested by profile/allowlist")
        print(f"{kind + 's':12s}: {len(report['components'][kind + 's']):4d} / {len(group)}")
    report["enabled_features"] = sorted(enabled - set(meta.components))
    write_if_changed(output / "components.json", json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "ffmpeg")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--options", type=Path)
    parser.add_argument("--facts", type=Path)
    parser.add_argument("--list", choices=[k + "s" for k in REGISTRIES] + ["all"])
    args = parser.parse_args()
    if args.list:
        meta = Metadata(args.source)
        for kind, group in meta.groups.items():
            if args.list in (kind + "s", "all"):
                print(kind + "s: " + ";".join(n[:-len(kind)-1] for n in group))
        return
    if not all((args.output, args.options, args.facts)):
        parser.error("--output, --options and --facts are required for configuration")
    options = json.loads(args.options.read_text(encoding="utf-8"))
    raw_facts = dict(line.split("=", 1) for line in args.facts.read_text().splitlines() if "=" in line)
    facts = {k.lower(): v == "1" for k, v in raw_facts.items() if not k.startswith(("HAVE_", "ARCH_", "CONFIG_"))}
    options["macros"] = {k: int(v) for k, v in raw_facts.items() if k.startswith(("HAVE_", "ARCH_", "CONFIG_"))}
    facts.update({k.split("_", 1)[1].lower(): v == "1" for k, v in raw_facts.items() if k.startswith(("HAVE_", "ARCH_", "CONFIG_"))})
    generate(args.source.resolve(), args.output.resolve(), options, facts)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
