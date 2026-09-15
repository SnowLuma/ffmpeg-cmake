"""Feed Ninja lossless MSVC JSON header dependencies, including cache hits."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    command = [arg for arg in command if arg and arg.lower() not in ("/showincludes", "-showincludes")]
    object_file = None
    for i, arg in enumerate(command):
        if arg[:3].lower() in ("/fo", "-fo"):
            object_file = arg[3:] or command[i + 1]
    if not object_file:
        parser.error("MSVC compile command has no /Fo object output")
    depfile = Path(object_file + ".includes.json")
    depfile.unlink(missing_ok=True)
    command.extend(("/sourceDependencies", str(depfile)))
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    sys.stdout.buffer.write(result.stdout)
    if result.returncode == 0:
        includes = json.loads(depfile.read_text(encoding="utf-8-sig"))["Data"]["Includes"]
        for path in includes:
            sys.stdout.buffer.write(("Note: including file: " + path + "\n").encode("utf-8"))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
