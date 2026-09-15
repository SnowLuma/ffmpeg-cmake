"""Build pinned external libraries with native CMake/Ninja into a reusable prefix.

Called by cmake/DependencyBuild.cmake; no shell, MSYS2 or system installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools/dependencies.json"


def selected_libraries(manifest, selection, gpl=False):
    recipes = manifest["libraries"]
    ordered = []
    visiting = set()

    def visit(name):
        if name in manifest["presets"]:
            for item in manifest["presets"][name]:
                visit(item)
            return
        if name in ordered:
            return
        if name in visiting:
            raise ValueError(f"Dependency cycle involving {name}")
        recipe = recipes[name]
        if recipe.get("gpl") and not gpl:
            raise ValueError(f"{name} requires -DFFMPEG_GPL=ON")
        visiting.add(name)
        for dependency in recipe.get("requires", []):
            visit(dependency)
        visiting.remove(name)
        ordered.append(name)

    for name in sorted(selection.replace(",", ";").split(";")):
        visit(name)
    return ordered


def run(*args):
    subprocess.run(list(map(str, args)), check=True)


def build(selection, context, output, gpl=False, jobs=0):
    manifest = json.loads(MANIFEST.read_text())
    names = selected_libraries(manifest, selection, gpl)
    identity = {"toolchain": context["identity"],
                "libraries": {name: manifest["libraries"][name] for name in sorted(names)},
                "driver": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    directory = ROOT / ".cache/dependencies" / key
    prefix = directory / "prefix"
    complete = prefix / "share/ffmpeg-cmake/dependencies.json"
    if complete.exists():
        print(f"External dependency cache: hit ({key})", flush=True)
        output.write_text(prefix.as_posix(), encoding="utf-8")
        return
    print(f"External dependency cache: building {', '.join(names)} ({key})", flush=True)
    prefix.mkdir(parents=True, exist_ok=True)
    package_keys = {}
    for name in names:
        recipe = manifest["libraries"][name]
        package_identity = {"toolchain": context["identity"], "driver": identity["driver"], "recipe": recipe,
                            "dependencies": {dep: package_keys[dep] for dep in recipe.get("requires", [])}}
        package_key = hashlib.sha256(json.dumps(package_identity, sort_keys=True).encode()).hexdigest()[:24]
        package_keys[name] = package_key
        package = ROOT / ".cache/dependency-packages" / package_key
        package_prefix = package / "prefix"
        receipt = package_prefix / "share/ffmpeg-cmake" / (name + ".json")
        if receipt.exists():
            print(f"  {name}: binary cache hit ({package_key})", flush=True)
            shutil.copytree(package_prefix, prefix, dirs_exist_ok=True)
            continue
        source = ROOT / ".cache/dependency-sources" / name / recipe["revision"]
        ready = source / ".git/ffmpeg-cmake-ready"
        if not ready.exists():
            if not (source / ".git").exists():
                run("git", "init", source)
                run("git", "-C", source, "remote", "add", "origin", recipe["repository"])
            run("git", "-C", source, "fetch", "--depth=1", "origin", recipe["revision"])
            run("git", "-C", source, "checkout", "--detach", "FETCH_HEAD")
            ready.touch()
        if recipe.get("tag"):
            run("git", "-C", source, "tag", "--force", recipe["tag"], recipe["revision"])
        binary = package / "build"
        print(f"Building {name} {recipe['version']}", flush=True)
        options = {"BUILD_SHARED_LIBS": "OFF", "BUILD_TESTING": "OFF",
                   "CMAKE_POSITION_INDEPENDENT_CODE": "ON", "CMAKE_INSTALL_LIBDIR": "lib",
                   "CMAKE_INSTALL_INCLUDEDIR": "include",
                   "CMAKE_INSTALL_PREFIX": package_prefix.as_posix(), "CMAKE_PREFIX_PATH": prefix.as_posix(),
                   **recipe.get("options", {})}
        if name == "freetype" and os.name == "nt":
            options["ZLIB_LIBRARY"] = (prefix / "lib/zs.lib").as_posix()
        if name == "aom" and os.name == "nt" and not shutil.which("perl"):
            # Git for Windows already ships the interpreter used by AOM's
            # source generator; no additional shell environment is installed.
            options["PERL_EXECUTABLE"] = (Path(shutil.which("git")).parents[1] / "usr/bin/perl.exe").as_posix()
        run(context["cmake"], "-S", source / recipe.get("source_subdir", ""), "-B", binary,
            "-G", "Ninja", *context["arguments"], *(f"-D{k}={v}" for k, v in options.items()))
        run(context["cmake"], "--build", binary, "--config", context["configuration"],
            "--parallel", jobs or os.cpu_count() or 2)
        run(context["cmake"], "--install", binary, "--config", context["configuration"])
        licenses = package_prefix / "share/licenses" / name
        licenses.mkdir(parents=True, exist_ok=True)
        for path in recipe["licenses"]:
            shutil.copy2(source / path, licenses / Path(path).name)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(package_identity, indent=2) + "\n", encoding="utf-8")
        shutil.copytree(package_prefix, prefix, dirs_exist_ok=True)
    complete.parent.mkdir(parents=True, exist_ok=True)
    complete.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    output.write_text(prefix.as_posix(), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gpl", action="store_true")
    parser.add_argument("--jobs", type=int, default=0)
    args = parser.parse_args()
    build(args.selection, json.loads(args.context.read_text(encoding="utf-8")), args.output, args.gpl, args.jobs)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError) as error:
        sys.exit(str(error))
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
