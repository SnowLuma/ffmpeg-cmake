"""Configure, build, test or install native FFmpeg on Windows, macOS and Linux."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys

from tools import sources

ROOT = Path(__file__).resolve().parent


def run(*command):
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def windows_environment():
    if "VCToolsInstallDir" in os.environ:
        return
    vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    installation = subprocess.check_output([
        str(vswhere), "-latest", "-products", "*", "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath",
    ], text=True).strip()
    if not installation:
        raise SystemExit("Install Visual Studio Build Tools with Desktop development with C++.")
    devcmd = Path(installation) / "Common7/Tools/VsDevCmd.bat"
    # cmd is used only to import the native Visual Studio environment.
    command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{devcmd}" -no_logo -arch=x64 -host_arch=x64 && set"'
    output = subprocess.check_output(command)
    for line in output.decode("mbcs").splitlines():
        key, separator, value = line.partition("=")
        if key and separator:
            os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default={"Windows": "windows-msvc", "Darwin": "macos", "Linux": "linux"}[platform.system()])
    parser.add_argument("--action", choices=("configure", "build", "test", "install"), default="build")
    parser.add_argument("--jobs", type=int, default=0, help="Parallel compile jobs; 0 uses Ninja's default")
    parser.add_argument("--branch", help="Fetch this FFmpeg branch before configuring")
    parser.add_argument("--bootstrap", action="store_true", help="Install portable NASM and sccache on Windows")
    parser.add_argument("--deps", help="Build external dependencies: media, all, or comma-separated library names")
    parser.add_argument("cmake_args", nargs=argparse.REMAINDER, help="Extra CMake options after --")
    args = parser.parse_args()
    if os.name == "nt":
        windows_environment()
    os.environ["PATH"] = str(ROOT / ".tools/bin") + os.pathsep + os.environ["PATH"]
    if args.bootstrap:
        run(sys.executable, ROOT / "tools/bootstrap.py")
    if args.branch or not (ROOT / "ffmpeg/configure").exists():
        sources.fetch(args.branch or "master")
    extra = args.cmake_args[1:] if args.cmake_args[:1] == ["--"] else args.cmake_args
    if args.deps is not None:
        extra = ["-DFFMPEG_DEPENDENCY_PREFIX=", "-DFFMPEG_DEPENDENCIES=" + args.deps.replace(",", ";"), *extra]
    run("cmake", "--preset", args.preset, *extra)
    if args.action != "configure":
        parallel = ("--parallel", args.jobs) if args.jobs else ()
        run("cmake", "--build", "--preset", args.preset, *parallel)
    if args.action == "test":
        run("ctest", "--test-dir", ROOT / "build" / args.preset, "--output-on-failure")
    elif args.action == "install":
        run("cmake", "--install", ROOT / "build" / args.preset)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)
