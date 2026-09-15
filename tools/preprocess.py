"""Capture C preprocessor output without shell redirection (also cross-safe)."""
import argparse
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--compiler", required=True)
parser.add_argument("--msvc", action="store_true")
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
flags = ["/nologo", "/EP", "/TC"] if args.msvc else ["-E", "-P", "-x", "c"]
data = subprocess.check_output([args.compiler, *flags, str(args.input)])
args.output.parent.mkdir(parents=True, exist_ok=True)
if not args.output.exists() or args.output.read_bytes() != data:
    args.output.write_bytes(data)
