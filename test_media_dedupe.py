import os
import tempfile
import unittest
from pathlib import Path

import main


class MediaDeduplicationTests(unittest.TestCase):
    def test_dedupe_paths_by_content_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)

            file_a = directory_path / "video-a.mp4"
            file_a.write_bytes(b"same-bytes")

            file_b = directory_path / "video-b.mp4"
            file_b.write_bytes(b"same-bytes")

            file_c = directory_path / "video-c.mp4"
            file_c.write_bytes(b"different-bytes")

            deduped = main.dedupe_media_paths([file_a, file_b, file_c])

            self.assertEqual(len(deduped), 2)
            self.assertIn(file_a, deduped)
            self.assertIn(file_c, deduped)


if __name__ == "__main__":
    unittest.main()
