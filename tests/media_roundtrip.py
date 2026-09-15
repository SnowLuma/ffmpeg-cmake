"""Exercise real codecs, demux/mux, swscale and ffprobe with lossless fixtures."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import wave
import functools
import http.server
import threading


def run(*command):
    result = subprocess.run(list(map(str, command)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command}\n" + result.stderr.decode(errors="replace"))
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    available = json.loads(args.report.read_text())["components"]
    required = {"decoders": {"flac", "pcm_s16le", "rawvideo", "ffv1"},
                "encoders": {"flac", "pcm_s16le", "rawvideo", "ffv1"},
                "demuxers": {"wav", "flac", "rawvideo", "matroska"},
                "muxers": {"flac", "pcm_s16le", "matroska", "rawvideo"}, "protocols": {"file"}}
    missing = {k: sorted(v - set(available[k])) for k, v in required.items() if v - set(available[k])}
    if missing:
        print("Skipped: this trimmed configuration excludes roundtrip test components:", missing)
        return 77
    with tempfile.TemporaryDirectory(prefix="ffmpeg-cmake-test-") as tmp:
        path = Path(tmp)
        samples = b"".join(struct.pack("<h", (i * 317 % 60001) - 30000) for i in range(8000))
        with wave.open(str(path / "source.wav"), "wb") as wav:
            wav.setparams((1, 2, 32000, 0, "NONE", "not compressed"))
            wav.writeframes(samples)
        ff = (args.ffmpeg, "-v", "error", "-nostdin", "-y")
        run(*ff, "-i", path / "source.wav", "-c:a", "flac", path / "audio.flac")
        run(*ff, "-i", path / "audio.flac", "-c:a", "pcm_s16le", "-f", "s16le", path / "audio.pcm")
        if (path / "audio.pcm").read_bytes() != samples:
            raise AssertionError("FLAC -> PCM roundtrip changed audio samples")
        pixels = bytes((x * 37 + y * 11 + frame * 29) % 256 for frame in range(4) for y in range(48) for x in range(64 * 3))
        (path / "source.rgb").write_bytes(pixels)
        run(*ff, "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "64x48", "-framerate", "5", "-i", path / "source.rgb", "-c:v", "ffv1", path / "video.mkv")
        run(*ff, "-i", path / "video.mkv", "-pix_fmt", "rgb24", "-f", "rawvideo", path / "decoded.rgb")
        if (path / "decoded.rgb").read_bytes() != pixels:
            raise AssertionError("FFV1/Matroska -> RGB roundtrip changed video pixels")
        info = json.loads(run(args.ffprobe, "-v", "error", "-show_streams", "-of", "json", path / "video.mkv"))
        stream = info["streams"][0]
        if (stream["codec_name"], stream["width"], stream["height"]) != ("ffv1", 64, 48):
            raise AssertionError("ffprobe reported unexpected video metadata")
        if "http" in available["protocols"]:
            class QuietHandler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *args):
                    pass
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(path)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/video.mkv"
                remote = json.loads(run(args.ffprobe, "-v", "error", "-show_streams", "-of", "json", url))
                if remote["streams"][0]["codec_name"] != "ffv1":
                    raise AssertionError("HTTP media probing failed")
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        if "png" in available["encoders"] and "png" in available["decoders"] and "image2" in available["muxers"]:
            run(*ff, "-i", path / "video.mkv", "-frames:v", "1", "-pix_fmt", "rgb24", path / "frame.png")
            run(*ff, "-i", path / "frame.png", "-pix_fmt", "rgb24", "-f", "rawvideo", path / "frame.rgb")
            if (path / "frame.rgb").read_bytes() != pixels[:64 * 48 * 3]:
                raise AssertionError("PNG roundtrip changed pixels")
    print("Passed: PCM/FLAC audio, RGB/FFV1/Matroska video, ffprobe metadata and available PNG/HTTP checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
