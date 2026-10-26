import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class TikTokMediaExtractionTests(unittest.TestCase):
    def test_download_tiktok_media_keeps_each_animated_photo_slide(self):
        payload = {
            "data": {
                "live_images": [
                    f"https://cdn.tiktok.com/slide-{index}?mime_type=video_mp4"
                    for index in range(5)
                ],
                "images": [
                    f"https://cdn.tiktok.com/slide-{index}.jpeg"
                    for index in range(5)
                ],
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            def save_video(_url, target_directory, filename):
                path = Path(target_directory) / f"{filename}.mp4"
                path.write_bytes(filename.encode())
                return path

            with (
                patch.object(
                    main,
                    "urlopen",
                    return_value=io.BytesIO(json.dumps(payload).encode()),
                ),
                patch.object(
                    main,
                    "download_instagram_video_url",
                    side_effect=save_video,
                ) as download_video,
                patch.object(
                    main,
                    "download_image_url",
                ) as download_image,
            ):
                media = main.download_tiktok_media(
                    "https://vt.tiktok.com/ZSgXT5Vt4/",
                    directory,
                )

        self.assertEqual(len(media), 5)
        self.assertTrue(all(path.suffix == ".mp4" for path in media))
        self.assertEqual(download_video.call_count, 5)
        download_image.assert_not_called()

    def test_download_tiktok_media_keeps_images_with_video_slides(self):
        payload = {
            "data": {
                "live_images": [
                    "https://cdn.tiktok.com/slide-video.mp4?mime_type=video_mp4",
                ],
                "images": [
                    {
                        "imageURL": {
                            "urlList": [
                                "https://cdn.tiktok.com/photo-1.jpeg",
                            ],
                        },
                    },
                    "https://cdn.tiktok.com/photo-2?image_type=photo",
                ],
                "cover": "https://cdn.tiktok.com/cover.webp",
                "origin_cover": "https://cdn.tiktok.com/cover.webp",
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            def save_media(target_directory, filename, content):
                path = Path(target_directory) / filename
                path.write_bytes(content)
                return path

            video_download = lambda _url, target_directory, filename: save_media(
                target_directory,
                f"{filename}.mp4",
                b"video",
            )
            image_download = lambda _url, target_directory, filename: save_media(
                target_directory,
                f"{filename}.jpeg",
                filename.encode(),
            )

            with (
                patch.object(
                    main,
                    "urlopen",
                    return_value=io.BytesIO(json.dumps(payload).encode()),
                ),
                patch.object(
                    main,
                    "download_instagram_video_url",
                    side_effect=video_download,
                ) as download_video,
                patch.object(
                    main,
                    "download_image_url",
                    side_effect=image_download,
                ) as download_image,
            ):
                media = main.download_tiktok_media(
                    "https://www.tiktok.com/@example/photo/123",
                    directory,
                )

        self.assertEqual(len(media), 3)
        self.assertEqual(sum(path.suffix == ".mp4" for path in media), 1)
        self.assertEqual(sum(path.suffix == ".jpeg" for path in media), 2)
        self.assertEqual(download_video.call_count, 1)
        self.assertEqual(download_image.call_count, 2)
        self.assertFalse(any("cover" in path.name for path in media))

    def test_download_tiktok_media_keeps_only_first_unwatermarked_video(self):
        payload = {
            "data": {
                "play": "https://cdn.tiktok.com/without-watermark.mp4",
                "hdplay": "https://cdn.tiktok.com/another-clean-copy.mp4",
                "wmplay": "https://cdn.tiktok.com/with-watermark.mp4",
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            def save_video(_url, target_directory, filename):
                path = Path(target_directory) / f"{filename}.mp4"
                path.write_bytes(b"video")
                return path

            with (
                patch.object(
                    main,
                    "urlopen",
                    return_value=io.BytesIO(json.dumps(payload).encode()),
                ),
                patch.object(
                    main,
                    "download_instagram_video_url",
                    side_effect=save_video,
                ) as download_video,
            ):
                media = main.download_tiktok_media(
                    "https://www.tiktok.com/@example/video/123",
                    directory,
                )

        self.assertEqual(len(media), 1)
        self.assertEqual(media[0].suffix, ".mp4")
        download_video.assert_called_once_with(
            "https://cdn.tiktok.com/without-watermark.mp4",
            directory,
            "tiktok-media-1",
        )


if __name__ == "__main__":
    unittest.main()
