"""Exercise fresh clones, branch switching and exact revisions with real Git."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("source_tool", ROOT / "tools/sources.py")
source_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source_tool)


class SourceTests(unittest.TestCase):
    def test_branch_revision_and_local_changes(self):
        with tempfile.TemporaryDirectory(prefix="ffmpeg-git-test-") as tmp:
            root = Path(tmp)
            upstream, work = root / "upstream", root / "project"
            work.mkdir()
            def git(*args):
                return subprocess.check_output(["git", *map(str, args)], text=True, stderr=subprocess.DEVNULL).strip()
            git("init", "-q", "-b", "master", upstream)
            file = upstream / "configure"
            file.write_text("master revision\n")
            git("-C", upstream, "add", "configure")
            git("-C", upstream, "-c", "user.name=Build Test", "-c", "user.email=build-test@example.invalid", "commit", "-qm", "master")
            master = git("-C", upstream, "rev-parse", "HEAD")
            git("-C", upstream, "checkout", "-qb", "release/test")
            file.write_text("release revision\n")
            git("-C", upstream, "-c", "user.name=Build Test", "-c", "user.email=build-test@example.invalid", "commit", "-qam", "release")
            release = git("-C", upstream, "rev-parse", "HEAD")
            with patch.object(source_tool, "ROOT", work), patch.object(source_tool, "URL", upstream.as_uri()), contextlib.redirect_stdout(io.StringIO()):
                source_tool.fetch("release/test")
                self.assertEqual(git("-C", work / "ffmpeg", "rev-parse", "HEAD"), release)
                source_tool.fetch("master")
                self.assertEqual(git("-C", work / "ffmpeg", "rev-parse", "HEAD"), master)
                source_tool.fetch("release/test", master)
                self.assertEqual(git("-C", work / "ffmpeg", "rev-parse", "HEAD"), master)
                (work / "ffmpeg/configure").write_text("local user edit\n")
                with self.assertRaisesRegex(SystemExit, "local changes"):
                    source_tool.fetch("release/test")
                self.assertEqual((work / "ffmpeg/configure").read_text(), "local user edit\n")


if __name__ == "__main__":
    unittest.main()
