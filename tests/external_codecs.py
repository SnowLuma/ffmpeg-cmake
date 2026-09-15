"""Exercise external encoders and text shaping through the built FFmpeg CLI."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import tempfile
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    ffmpeg = args.ffmpeg.resolve()
    components = json.loads(args.report.read_text())["components"]
    encoders = set(components["encoders"])
    tested = []
    with tempfile.TemporaryDirectory(prefix="ffmpeg-external-") as tmp:
        root = Path(tmp)
        def run(*command):
            result = subprocess.run([str(ffmpeg), "-nostdin", "-y", "-v", "error", *command], cwd=root,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            if result.returncode:
                raise AssertionError(result.stderr.decode(errors="replace"))
            return result.stdout
        samples = b"".join(struct.pack("<h", (i * 317 % 20001) - 10000) for i in range(12000))
        with wave.open(str(root / "input.wav"), "wb") as source:
            source.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            source.writeframes(samples)
        for encoder in ("libopus", "libvorbis"):
            if encoder not in encoders:
                continue
            run("-i", "input.wav", "-c:a", encoder, "audio.ogg")
            decoded = run("-i", "audio.ogg", "-f", "s16le", "-")
            assert len(decoded) >= len(samples) // 2, encoder
            external_decoded = run("-c:a", encoder, "-i", "audio.ogg", "-f", "s16le", "-")
            assert len(external_decoded) >= len(samples) // 2, encoder + " decoder"
            tested.append(encoder)
        pixels = bytes((x * 37 + y * 11) % 256 for y in range(48) for x in range(64 * 3))
        (root / "input.rgb").write_bytes(pixels)
        raw = ("-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "64x48", "-i", "input.rgb")
        if "libwebp" in encoders:
            run(*raw, "-c:v", "libwebp", "-lossless", "1", "still.webp")
            decoded = run("-i", "still.webp", "-pix_fmt", "rgb24", "-f", "rawvideo", "-")
            assert decoded == pixels, "WebP lossless pixels changed"
            tested.append("libwebp")
        if "libwebp_anim" in encoders:
            (root / "motion.rgb").write_bytes(pixels + bytes(255 - x for x in pixels))
            run("-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "64x48", "-framerate", "5",
                "-i", "motion.rgb", "-c:v", "libwebp_anim", "-lossless", "1", "animation.webp")
            animation = (root / "animation.webp").read_bytes()
            assert animation.startswith(b"RIFF") and b"ANIM" in animation and animation.count(b"ANMF") == 2
            tested.append("libwebp_anim")
        for encoder, suffix, options in (
            ("libaom_av1", "ivf", ("-cpu-used", "8", "-crf", "45")),
            ("libx265", "hevc", ("-preset", "ultrafast", "-x265-params", "pools=1:frame-threads=1:log-level=error")),
        ):
            if encoder not in encoders:
                continue
            cli_name = encoder.replace("_", "-") if encoder == "libaom_av1" else encoder
            run(*raw, "-pix_fmt", "yuv420p", "-c:v", cli_name, "-threads", "2", *options, "video." + suffix)
            decoder = ("-c:v", "libaom-av1") if encoder == "libaom_av1" else ()
            decoded = run(*decoder, "-i", "video." + suffix, "-pix_fmt", "rgb24", "-f", "rawvideo", "-")
            assert len(decoded) == len(pixels), encoder
            tested.append(encoder)
        if "drawtext" in components["filters"]:
            font = {"Windows": Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf",
                    "Linux": Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                    "Darwin": Path("/System/Library/Fonts/Supplemental/Arial.ttf")}[platform.system()]
            shutil.copyfile(font, root / "font.ttf")
            result = run(*raw, "-vf", "drawtext=fontfile=font.ttf:text=Native:fontsize=14:fontcolor=white",
                         "-pix_fmt", "rgb24", "-f", "rawvideo", "-")
            assert len(result) == len(pixels) and result != pixels, "FreeType/HarfBuzz did not render text"
            tested.append("drawtext (FreeType/HarfBuzz)")
    print("External codecs:", ", ".join(tested) if tested else "none selected")
    return 0 if tested else 77


if __name__ == "__main__":
    raise SystemExit(main())
