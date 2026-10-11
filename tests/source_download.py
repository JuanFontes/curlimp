"""Focused checks for verified source-cache reuse, with no network access."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fetch-verified.sh"


class SourceDownloads(unittest.TestCase):
    def run_download(self, path, digest):
        return subprocess.run(["sh", str(SCRIPT), "https://unreachable.invalid/source.tar.gz",
                               digest, str(path)], capture_output=True, timeout=5)

    def test_verified_cached_archive_does_not_require_network(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "source.tar.gz"
            content = b"exact source archive bytes"
            archive.write_bytes(content)
            result = self.run_download(archive, hashlib.sha256(content).hexdigest())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(archive.read_bytes(), content)

    def test_corrupt_cached_archive_is_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "source.tar.gz"
            archive.write_bytes(b"corrupt archive")
            result = self.run_download(archive, hashlib.sha256(b"expected source").hexdigest())
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"SHA-256 mismatch", result.stderr)
            self.assertEqual(archive.read_bytes(), b"corrupt archive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
