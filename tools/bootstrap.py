"""Install pinned, portable Windows build helpers locally; no admin or MSYS2."""
import argparse
import hashlib
import io
import os
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    ("nasm", "3.02", "https://www.nasm.us/pub/nasm/releasebuilds/3.02/win64/nasm-3.02-win64.zip",
     "161d0bfaff53c2f9e9f3e69fd0672323ebabafd1268976a5cec11be92a19aee7"),
    ("sccache", "0.18.0", "https://github.com/mozilla/sccache/releases/download/v0.18.0/sccache-v0.18.0-x86_64-pc-windows-msvc.zip",
     "8965c74d5e8a225244f741e18ad2f3f504f48228dc1bac948fc22761a348363d"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("nasm", "sccache"))
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("On Linux/macOS install nasm and ccache/sccache with your package manager.")
    directory = ROOT / ".tools/bin"
    directory.mkdir(parents=True, exist_ok=True)
    for name, version, url, digest in PACKAGES:
        if args.only and name != args.only:
            continue
        archive = ROOT / ".tools/downloads" / url.rsplit("/", 1)[1]
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            print(f"Downloading {name} {version}...", flush=True)
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            archive.write_bytes(data)
        data = archive.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit(f"SHA256 mismatch for cached archive: {archive}")
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            entries = [n for n in package.namelist() if n.rsplit("/", 1)[-1] == name + ".exe"]
            binary = package.read(entries[0])
            target = directory / (name + ".exe")
            target.write_bytes(binary)
            for entry in package.namelist():
                if "license" in entry.lower() and not entry.endswith("/"):
                    (directory / (name + "-" + Path(entry).name)).write_bytes(package.read(entry))
        print(f"Ready: {name} {version} ({target})")


if __name__ == "__main__":
    main()
