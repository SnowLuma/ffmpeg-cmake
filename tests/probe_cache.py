"""Verify cross-directory probe reuse and invalidation with a real compiler."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build import windows_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc")
    parser.add_argument("--cxx")
    args = parser.parse_args()
    if os.name == "nt":
        windows_environment()
    with tempfile.TemporaryDirectory(prefix="ffmpeg-probe-cache-") as tmp:
        directory = Path(tmp)
        base = ["cmake", "-G", "Ninja", "-S", str(ROOT / "tests/probe_cache"),
                "-DCMAKE_C_FLAGS=", "-DFFMPEG_ROOT=" + ROOT.as_posix(),
                "-DFFMPEG_PROBE_CACHE_DIR=" + (directory / "cache").as_posix()]
        if args.cc:
            base += ["-DCMAKE_C_COMPILER=" + args.cc, "-DCMAKE_CXX_COMPILER=" + args.cxx]
        def configure(name, *extra):
            result = subprocess.run([*base, "-B", str(directory / name), *extra], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return result.stdout
        cold = configure("first")
        assert "Performing Test FF_PROBE_FIXTURE_VALID" in cold, cold
        warm = configure("second")
        assert "restored 2 results" in warm and "Performing Test FF_PROBE_FIXTURE" not in warm, warm
        assert (directory / "second/result.txt").read_text() == "1;0"
        changed = configure("second", "-DCMAKE_C_FLAGS=-DCACHE_TEST_FAIL")
        assert "Performing Test FF_PROBE_FIXTURE_VALID - Failed" in changed, changed
        restored = configure("second", "-DCMAKE_C_FLAGS=")
        assert "restored 2 results" in restored and "Performing Test FF_PROBE_FIXTURE" not in restored, restored
        assert (directory / "second/result.txt").read_text() == "1;0"
        print("Probe cache: cold/warm, cached failures, flag invalidation and previous-key reuse passed")


if __name__ == "__main__":
    main()
