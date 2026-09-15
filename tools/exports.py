"""Generate a Windows DEF file using FFmpeg's public export patterns."""
import argparse
import fnmatch
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cmake", required=True)
parser.add_argument("--objects", type=Path, required=True)
parser.add_argument("--version-script", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
subprocess.run([args.cmake, "-E", "__create_def", str(args.output), str(args.objects)], check=True)
public = args.version_script.read_text().partition("global:")[2].partition("local:")[0]
patterns = public.replace(";", " ").split()
exports = [line for line in args.output.read_text().splitlines()[1:]
           if line.strip() and any(fnmatch.fnmatchcase(line.split()[0], pattern) for pattern in patterns)]
args.output.write_text("EXPORTS\n" + "\n".join(exports) + "\n", encoding="utf-8", newline="\n")
