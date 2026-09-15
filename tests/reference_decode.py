"""Optional integration check against an independently installed FFmpeg.

Not part of the default tests: requires a reference binary with libx264/libx265.
Both decoders read the same generated bitstream, and must agree byte-for-byte.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


def run(*args):
    result = subprocess.run(list(map(str, args)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--reference", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ffmpeg-codecs-") as tmp:
        for codec, encoder, suffix in (("H.264", "libx264", "h264"), ("HEVC", "libx265", "hevc")):
            sample = Path(tmp) / ("sample." + suffix)
            extra = ["-x265-params", "pools=1:frame-threads=1:log-level=error"] if encoder == "libx265" else []
            run(args.reference, "-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=8",
                "-frames:v", "8", "-pix_fmt", "yuv420p", "-c:v", encoder, "-threads", "2", *extra, sample)
            decoded = []
            for executable, flags in ((args.reference, []), (args.ffmpeg, []), (args.ffmpeg, ["-cpuflags", "0"])):
                decoded.append(run(executable, "-v", "error", "-nostdin", *flags, "-i", sample,
                                   "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"))
            if any(data != decoded[0] for data in decoded[1:]) or len(decoded[0]) != 128 * 96 * 3 // 2 * 8:
                raise AssertionError(codec + " decoding differs from the reference")
            print(codec + ": C and CPU-optimized decoding match 8 reference frames exactly")


if __name__ == "__main__":
    main()
