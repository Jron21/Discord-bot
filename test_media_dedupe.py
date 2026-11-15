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


class InstagramMediaExtractionTests(unittest.TestCase):
    def test_extract_instagram_urls_separates_full_images_from_previews(self):
        full_url = "https://scontent.cdninstagram.com/full-image.jpg"
        preview_url = "https://scontent.cdninstagram.com/preview.jpg"
        page = (
            json.dumps({"display_url": full_url})
            + f'<meta property="og:image" content="{preview_url}">'
        )

        full_urls, preview_urls = main.extract_instagram_image_urls(page)

        self.assertEqual(full_urls, [full_url])
        self.assertEqual(preview_urls, [preview_url])

    def test_indexed_carousel_does_not_download_preview_only_metadata(self):
        preview_url = "https://scontent.cdninstagram.com/preview.jpg"
        page = f'<meta property="og:image" content="{preview_url}">'

        with self.assertLogs(main.logger, level="WARNING") as captured:
            with (
                patch.object(
                    main,
                    "urlopen",
                    side_effect=lambda *_args, **_kwargs: io.BytesIO(page.encode()),
                ),
                patch.object(main, "download_instagram_sidecar_media", return_value=[]),
                patch.object(main, "download_image_url") as download_image,
            ):
                media = main.download_instagram_media(
                    "https://www.instagram.com/p/example/?img_index=2",
                    ".",
                )

        self.assertEqual(media, [])
        download_image.assert_not_called()
        self.assertIn(
            "Skipping preview fallback",
            "\n".join(captured.output),
        )

    def test_indexed_carousel_downloads_all_display_urls(self):
        image_urls = [
            f"https://scontent.cdninstagram.com/full-{index}.jpg"
            for index in range(1, 4)
        ]
        page = json.dumps({
            "items": [{"display_url": image_url} for image_url in image_urls],
        }) + " login"

        with self.assertLogs(main.logger, level="INFO") as captured:
            with tempfile.TemporaryDirectory() as directory:
                def save_image(image_url, target_directory, filename):
                    path = Path(target_directory) / f"{filename}.jpg"
                    path.write_bytes(image_url.encode())
                    return path

                with (
                    patch.object(
                        main,
                        "urlopen",
                        side_effect=lambda *_args, **_kwargs: io.BytesIO(page.encode()),
                    ),
                    patch.object(main, "download_instagram_sidecar_media", return_value=[]),
                    patch.object(main, "download_image_url", side_effect=save_image),
                ):
                    media = main.download_instagram_media(
                        "https://www.instagram.com/p/example/?img_index=3",
                        directory,
                    )
                media_contents = [path.read_bytes().decode() for path in media]

        self.assertEqual(len(media), len(image_urls))
        self.assertEqual(media_contents, image_urls)
        self.assertIn(
            "login_and_signup_page=False",
            "\n".join(captured.output),
        )
        self.assertIn("carousel_metadata=False", "\n".join(captured.output))

    def test_instagram_http_errors_are_logged_without_query_tokens(self):
        error = main.HTTPError(
            "https://www.instagram.com/p/example/",
            401,
            "Unauthorized",
            None,
            None,
        )

        with (
            patch.object(main, "urlopen", side_effect=error),
            self.assertLogs(main.logger, level="WARNING") as captured,
        ):
            media = main.download_instagram_media(
                "https://www.instagram.com/p/example/?img_index=2&stkn=secret-token",
                ".",
            )

        self.assertEqual(media, [])
        self.assertIn("Instagram HTTP error 401", "\n".join(captured.output))
        self.assertNotIn("secret-token", "\n".join(captured.output))


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
