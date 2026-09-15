"""Capture a build tool's stdout into a generated file, without a shell."""
import argparse
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ["--"] else args.command
data = subprocess.check_output(command)
args.output.parent.mkdir(parents=True, exist_ok=True)
if not args.output.exists() or args.output.read_bytes() != data:
    args.output.write_bytes(data)
