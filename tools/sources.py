"""Fetch an FFmpeg branch into the ignored ffmpeg/ checkout."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/FFmpeg/FFmpeg.git"


def git(*args):
    return subprocess.check_output(["git", *map(str, args)], text=True).strip()


def fetch(branch="master", revision=None):
    source = ROOT / "ffmpeg"
    if not (source / ".git").exists():
        git("init", source)
        git("-C", source, "remote", "add", "origin", URL)
    else:
        if git("-C", source, "status", "--porcelain"):
            raise SystemExit("ffmpeg/ has local changes; commit or stash them before updating.")
    git("-C", source, "fetch", "--depth=1", "origin", revision or branch)
    git("-C", source, "checkout", "--detach", "FETCH_HEAD")
    print(f"FFmpeg {branch}: {git('-C', source, 'rev-parse', 'HEAD')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", default="master", help="Branch to fetch (default: master)")
    parser.add_argument("--revision", help="Optional commit to reproduce a build")
    args = parser.parse_args()
    fetch(args.branch, args.revision)


if __name__ == "__main__":
    main()
