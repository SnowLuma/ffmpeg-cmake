"""Check that Ninja tracks real header dependencies, including cached MSVC builds.

Run after building avutil. Only the header timestamp is changed, then restored;
the second build is a dry run. Source contents are never changed.
"""
import argparse
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--build", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
command = ["ninja", "-C", str(args.build), "-n", "avutil"]
baseline = subprocess.check_output(command, text=True)
if "no work to do" not in baseline:
    raise SystemExit("Build avutil first; baseline is not up to date:\n" + baseline)
header = root / "ffmpeg/libavutil/adler32.h"
old = header.stat()
try:
    updated = max(time.time_ns(), old.st_mtime_ns + 2_000_000_000)
    os.utime(header, ns=(old.st_atime_ns, updated))
    scheduled = subprocess.check_output(command, text=True)
    if "adler32.c" not in scheduled:
        raise AssertionError("Changing adler32.h did not schedule adler32.c for rebuilding:\n" + scheduled)
finally:
    os.utime(header, ns=(old.st_atime_ns, old.st_mtime_ns))
print("Passed: unchanged tree needs no work; a header change schedules its dependent compilation")
