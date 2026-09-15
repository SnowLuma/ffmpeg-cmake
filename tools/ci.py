"""Small cross-platform CI steps; workflow policy stays in build.yml."""
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build import windows_environment
from tools import sources


def run(*command):
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def archive(output, entries):
    # Fast gzip; upload-artifact does not recompress the resulting archive.
    with gzip.open(output, "wb", compresslevel=1) as compressed, tarfile.open(fileobj=compressed, mode="w|") as package:
        for path, name in entries:
            package.add(path, arcname=name)


def unpack(archive_path, destination):
    with tarfile.open(archive_path) as package:
        package.extractall(destination, filter="data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("resolve", "source", "prepare", "build", "archive"))
    args = parser.parse_args()
    if args.action == "resolve":
        revision = os.environ.get("FFMPEG_REVISION")
        if not revision:
            revision = sources.git("ls-remote", "--exit-code", sources.URL,
                                   "refs/heads/" + os.environ.get("FFMPEG_BRANCH", "master")).split()[0]
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"revision={revision}\n")
        return
    if args.action == "source":
        sources.fetch(os.environ.get("FFMPEG_BRANCH", "master"), os.environ["FFMPEG_REVISION"])
        archive("ffmpeg-source.tar.gz", [(ROOT / "ffmpeg", "ffmpeg")])
        return
    if os.name == "nt":
        windows_environment()
    os.environ["PATH"] = str(ROOT / ".tools/bin") + os.pathsep + os.environ["PATH"]
    preset = os.environ["PRESET"]
    if args.action in ("prepare", "build"):
        unpack("ffmpeg-source.tar.gz", ROOT)
    if args.action == "prepare":
        run(sys.executable, "build.py", "--preset", preset, "--action", "configure", "--",
            "-DFFMPEG_DEPENDENCIES=all", "-DFFMPEG_GPL=ON", "-DFFMPEG_ASM=ON")
        prefix = Path((ROOT / "build" / preset / "dependency-prefix.txt").read_text())
        report = json.loads((ROOT / "build" / preset / "generated/components.json").read_text())
        expected = {"libopus", "libvorbis", "libwebp", "libwebp_anim", "libaom_av1", "libx265"}
        missing = expected - set(report["components"]["encoders"])
        if missing or "drawtext" not in report["components"]["filters"] or "ffplay" not in report["programs"]:
            raise RuntimeError(f"Requested external components were not enabled: {missing}; check components.json")
        run(sys.executable, "tests/probe_cache.py")
        archive("prepared.tar.gz", [(prefix, "deps"), (ROOT / ".cache/probes", "probes")])
    elif args.action == "build":
        unpack("prepared.tar.gz", ROOT / ".cache/prepared")
        run(sys.executable, "build.py", "--preset", preset, "--action", "test", "--",
            "-DBUILD_SHARED_LIBS=" + os.environ["SHARED"], "-DFFMPEG_ASM=ON", "-DFFMPEG_GPL=ON",
            "-DFFMPEG_DEPENDENCY_PREFIX=" + (ROOT / ".cache/prepared/deps").as_posix(),
            "-DFFMPEG_PROBE_CACHE_DIR=" + (ROOT / ".cache/prepared/probes").as_posix())
        run("cmake", "--install", ROOT / "build" / preset)
        run(sys.executable, "tests/package.py", "--prefix", ROOT / "install" / preset)
        run(sys.executable, "tests/incremental.py", "--build", ROOT / "build" / preset)
    elif args.action == "archive":
        archive(f"ffmpeg-{os.environ['TARGET']}-shared-{os.environ['SHARED']}.tar.gz",
                [(ROOT / "install" / preset, ".")])


if __name__ == "__main__":
    main()
