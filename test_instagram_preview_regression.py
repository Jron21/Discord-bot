import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import main


class InstagramPreviewFallbackTests(unittest.TestCase):
    def test_html_fallback_stops_on_risky_contactpoint_redirect(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.geturl.return_value = (
            "https://www.instagram.com/accounts/update_risky_contactpoint/"
        )
        response.read.return_value = b"Instagram challenge"

        with patch.object(main, "urlopen", return_value=response):
            with self.assertLogs(main.logger, level="WARNING") as captured:
                media = main.download_instagram_html_images(
                    "https://www.instagram.com/p/Dfzrs4OHSuQ/",
                    "Dfzrs4OHSuQ",
                    ".",
                )

        self.assertEqual(media, [])
        self.assertIn("login/challenge page", "\n".join(captured.output))

    def test_extracts_transcoded_heic_carousel_candidates(self):
        shortcode = "Dfzrs4OHSuQ"
        image_urls = [
            "https://scontent.cdninstagram.com/full-one.heic?stp=dst-jpg_e35",
            "https://scontent.cdninstagram.com/full-two.heic?stp=dst-jpg_e35",
        ]
        page = json.dumps({
            "code": shortcode,
            "media_type": 8,
            "carousel_media": [
                {
                    "media_type": 1,
                    "image_versions2": {
                        "candidates": [{
                            "url": image_url,
                            "width": 1440,
                            "height": 1920,
                        }],
                    },
                }
                for image_url in image_urls
            ],
        })

        full_urls, preview_urls = main.extract_instagram_image_urls(
            page,
            shortcode,
        )

        self.assertEqual(full_urls, image_urls)
        self.assertEqual(preview_urls, [])

    def test_thumbnail_only_metadata_is_rejected(self):
        downloader = MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.__exit__.return_value = False
        downloader.extract_info.return_value = {
            "entries": [{
                "thumbnail": "https://cdninstagram.com/cropped-preview.jpg",
                "url": "https://cdninstagram.com/cropped-preview.jpg",
            }],
        }

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(main, "download_instagram_media", return_value=[]),
                patch.object(main, "YoutubeDL", return_value=downloader),
                patch.object(
                    main,
                    "urlopen",
                    return_value=io.BytesIO(
                        b'<meta property="og:image" '
                        b'content="https://cdninstagram.com/cropped-preview.jpg">'
                    ),
                ),
                patch.object(main, "download_open_graph_image") as open_graph,
                patch.object(main, "download_image_url") as download_image,
                self.assertRaisesRegex(
                    main.DownloadError,
                    "full media metadata was unavailable",
                ),
            ):
                main.download_social_media(
                    "https://www.instagram.com/p/DfjAPIEnfOJ/",
                    directory,
                )

        open_graph.assert_not_called()
        download_image.assert_not_called()

    def test_yt_dlp_failure_does_not_fall_back_to_open_graph_preview(self):
        downloader = MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.__exit__.return_value = False
        downloader.extract_info.side_effect = main.DownloadError(
            "No video formats found"
        )

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(main, "download_instagram_media", return_value=[]),
                patch.object(main, "YoutubeDL", return_value=downloader),
                patch.object(
                    main,
                    "urlopen",
                    return_value=io.BytesIO(
                        b'<meta property="og:image" '
                        b'content="https://cdninstagram.com/cropped-preview.jpg">'
                    ),
                ),
                patch.object(main, "download_open_graph_image") as open_graph,
                self.assertRaisesRegex(
                    main.DownloadError,
                    "full media metadata was unavailable",
                ),
            ):
                main.download_social_media(
                    "https://www.instagram.com/p/DfjAPIEnfOJ/",
                    directory,
                )

        open_graph.assert_not_called()

    def test_graphql_and_yt_dlp_failure_can_fall_back_to_all_full_html_images(self):
        image_urls = [
            "https://cdninstagram.com/full-image-1.jpg",
            "https://cdninstagram.com/full-image-2.jpg",
        ]
        page = json.dumps({
            "edge_sidecar_to_children": {
                "edges": [
                    {"node": {"display_url": image_url}}
                    for image_url in image_urls
                ],
            },
        }) + (
            '<meta property="og:image" '
            'content="https://cdninstagram.com/cropped-preview.jpg">'
        )
        downloader = MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.__exit__.return_value = False
        downloader.extract_info.side_effect = main.DownloadError(
            "No video formats found"
        )
        selected_urls = []

        with tempfile.TemporaryDirectory() as directory:
            def save_image(media_url, target_directory, filename):
                selected_urls.append(media_url)
                path = Path(target_directory) / f"{filename}.jpg"
                path.write_bytes(media_url.encode())
                return path

            with (
                patch.object(main, "download_instagram_media", return_value=[]),
                patch.object(main, "YoutubeDL", return_value=downloader),
                patch.object(
                    main,
                    "urlopen",
                    return_value=io.BytesIO(page.encode()),
                ),
                patch.object(main, "download_image_url", side_effect=save_image),
            ):
                media = main.download_social_media(
                    "https://www.instagram.com/p/DfjAPIEnfOJ/",
                    directory,
                )

        self.assertEqual(len(media), len(image_urls))
        self.assertEqual(selected_urls, image_urls)

    def test_all_full_carousel_items_are_downloaded_from_ytdlp_metadata(self):
        image_one = "https://cdninstagram.com/full-image-1.jpg"
        image_two = "https://cdninstagram.com/full-image-2.jpg"
        video_url = "https://cdninstagram.com/carousel-video.mp4"
        downloader = MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.__exit__.return_value = False
        downloader.extract_info.return_value = {
            "entries": [
                {
                    "thumbnail": "https://cdninstagram.com/cropped-preview.jpg",
                    "thumbnails": [
                        {"url": "https://cdninstagram.com/low-image-1.jpg", "width": 100, "height": 100},
                        {"url": image_one, "width": 1000, "height": 1000},
                    ],
                },
                {
                    "thumbnails": [
                        {"url": image_two, "width": 1200, "height": 800},
                    ],
                },
                {
                    "formats": [
                        {"url": video_url, "width": 1280, "height": 720},
                    ],
                },
            ],
        }
        selected_urls = []

        with tempfile.TemporaryDirectory() as directory:
            def save_media(media_url, target_directory, filename):
                selected_urls.append(media_url)
                extension = ".mp4" if media_url.endswith(".mp4") else ".jpg"
                path = Path(target_directory) / f"{filename}{extension}"
                path.write_bytes(media_url.encode())
                return path

            with (
                patch.object(main, "download_instagram_media", return_value=[]),
                patch.object(main, "YoutubeDL", return_value=downloader),
                patch.object(main, "download_image_url", side_effect=save_media),
                patch.object(main, "download_instagram_video_url", side_effect=save_media),
            ):
                media = main.download_social_media(
                    "https://www.instagram.com/p/DfjAPIEnfOJ/",
                    directory,
                )

        self.assertEqual(len(media), 3)
        self.assertEqual(selected_urls, [image_one, image_two, video_url])

    def test_real_video_formats_remain_downloadable(self):
        downloader = MagicMock()
        downloader.__enter__.return_value = downloader
        downloader.__exit__.return_value = False
        downloader.extract_info.return_value = {
            "id": "DfjAPIEnfOJ",
            "formats": [{
                "format_id": "video",
                "url": "https://cdninstagram.com/video.mp4",
                "width": 1280,
                "height": 720,
            }],
        }

        with tempfile.TemporaryDirectory() as directory:
            video_url = "https://cdninstagram.com/video.mp4"

            def save_video(media_url, target_directory, filename):
                self.assertEqual(media_url, video_url)
                video_path = Path(target_directory) / f"{filename}.mp4"
                video_path.write_bytes(b"video")
                return video_path

            with (
                patch.object(main, "download_instagram_media", return_value=[]),
                patch.object(main, "YoutubeDL", return_value=downloader),
                patch.object(
                    main,
                    "download_instagram_video_url",
                    side_effect=save_video,
                ),
            ):
                media = main.download_social_media(
                    "https://www.instagram.com/p/DfjAPIEnfOJ/",
                    directory,
                )

        self.assertEqual(len(media), 1)
        self.assertEqual(media[0].suffix, ".mp4")
