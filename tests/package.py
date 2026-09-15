"""Build a C-only consumer against an installed FFmpeg package and run it."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build import windows_environment

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--prefix", type=Path, required=True)
args = parser.parse_args()
if os.name == "nt":
    windows_environment()
prefix = args.prefix.resolve()
os.environ["PATH"] = str(prefix / "bin") + os.pathsep + os.environ["PATH"]
directory = ROOT / "build/package-consumer" / prefix.name
subprocess.run(["cmake", "-S", str(ROOT / "tests/consumer"), "-B", str(directory), "-G", "Ninja",
                "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + str(prefix), "-UFFmpeg_DIR"], check=True)
subprocess.run(["cmake", "--build", str(directory)], check=True)
subprocess.run(["ctest", "--test-dir", str(directory), "--output-on-failure"], check=True)
