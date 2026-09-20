import os
import random
import asyncio
import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import parse_qs, quote, urljoin, urlparse
from html.parser import HTMLParser
from urllib.request import Request, urlopen

import discord
import instaloader
from dotenv import load_dotenv
from discord.ext import commands
from yt_dlp import DownloadError, YoutubeDL

load_dotenv()


# ============================================================
# Configuration
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
MAX_MEDIA_BYTES = int(os.getenv("MAX_MEDIA_BYTES", 24 * 1024 * 1024))


def resolve_ffmpeg_path() -> str:
    configured_path = os.getenv("FFMPEG_PATH")
    if configured_path:
        configured_candidate = Path(configured_path).expanduser()
        if configured_candidate.is_file():
            return str(configured_candidate)
        configured_command = shutil.which(configured_path)
        if configured_command:
            return configured_command

    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    windows_winget_ffmpeg = (
        Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet"
        / "Links" / "ffmpeg.exe"
    )
    if windows_winget_ffmpeg.is_file():
        return str(windows_winget_ffmpeg)

    return "ffmpeg"


FFMPEG_PATH = resolve_ffmpeg_path()
MAX_SPOTIFY_PLAYLIST_TRACKS = 100
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE")
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("Sora10Chan")

SOCIAL_MEDIA_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:"
    r"facebook\.com|fb\.watch|"
    r"tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com|"
    r"instagram\.com|"
    r"twitter\.com|x\.com"
    r")[^\s<>]+",
    re.IGNORECASE,
)

TWITTER_TWEET_ID_PATTERN = re.compile(
    r"(?:twitter\.com|x\.com)/[^/]+/status(?:es)?/(\d+)",
    re.IGNORECASE,
)

INSTAGRAM_POST_PATTERN = re.compile(
    r"instagram\.com/p/([^/?#]+)",
    re.IGNORECASE,
)


# ============================================================
# Existing bot data
# ============================================================

ASUKA_IMAGES = [
    'https://i.pinimg.com/originals/e4/66/6a/e4666af369f09d81cdebf7111bc428f6.gif',
    'https://i.pinimg.com/originals/5d/81/34/5d81345ab238484837d263bb47eb681d.gif',
    'https://i.pinimg.com/originals/14/37/a4/1437a4af80a3d551b38dc929d31a569e.gif',
    'https://i.pinimg.com/originals/76/f6/ab/76f6abc1f0684bd222500bfd8e0f0a4a.gif',
    'https://i.pinimg.com/originals/e1/24/b6/e124b632cd2d9cc00b8aa7e2c6d0dfa1.gif',
    'https://i.pinimg.com/originals/0b/e2/ec/0be2ec18244adef461b269c25c5b1a15.gif',
]

DOOR_IMAGES = [
    'https://media.discordapp.net/attachments/794492424713797642/955809260342759485/IMG_20220322_203535.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955808883836862484/IMG_20220322_203725.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809260137226270/IMG_20220322_203635.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809260544098344/IMG_20220322_203412.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809260783165510/IMG_20220322_203350.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809261001273394/IMG_20220322_203301.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809261206773831/IMG_20220322_203230.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955809261437468712/IMG_20220322_203118.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955810094258483230/unknown-1.png',
    'https://media.discordapp.net/attachments/794492424713797642/955810094615003226/Screenshot_2022-02-28-01-11-57-81_572064f74bd5f9fa804b05334aa4f912.png',
    'https://media.discordapp.net/attachments/794492424713797642/955811133988667424/IMG_20220318_231533.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955811853026590740/Screenshot_2022-03-15-13-48-40-29_be80aec1db9a2b53c9d399db0c602181.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955811853248917514/IMG_20220307_195827.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955812010564673656/IMG_20220225_160006.jpg',
    'https://media.discordapp.net/attachments/794492424713797642/955812789463703562/IMG_20220205_214056.jpg',
]

RESPONSES = {
    'nice': 'https://media.discordapp.net/attachments/950636380902535178/954749647748988978/ikuchan_thumbs_up_2.gif',
    'wtf': 'https://media.discordapp.net/attachments/950636380902535178/954720092711686194/AmusedLittleDamselfly-size_restricted_1.gif',
    'night': 'https://media.discordapp.net/attachments/950636380902535178/954720173573672991/tumblr_m7u7pn8lnr1rol1m7o5_250_1.gif',
    'sorry': 'https://tenor.com/view/idol-sakamichi-nogizaka46-gomen-gomennasai-gif-15222467',
    'morning': 'https://tenor.com/view/kaki-haruka-kakki-nogizaka46-gif-22485470',
    'see': 'https://giant.gfycat.com/DaringEveryIsabellinewheatear.mp4',
}

SEMBATSU_ENTRIES = [
    {
        'number': 1,
        'title': 'Guruguru Curtain',
        'announced': '2012-01-08',
        'onSale': '2012-02-22',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956072832595550298/1.jpg',
    },
    {
        'number': 2,
        'title': 'Oide Shampoo',
        'announced': '2012-03-18',
        'onSale': '2012-05-22',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956073027068624906/2.jpg',
    },
    {
        'number': 3,
        'title': 'Hashire! Bicycle',
        'announced': '2012-06-17',
        'onSale': '2012-08-22',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956073151375233034/3.jpg',
    },
    {
        'number': 4,
        'title': 'Seifuku No Mannequin',
        'announced': '2012-10-07',
        'onSale': '2012-12-19',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956073425930162176/4.jpg',
    },
    {
        'number': 5,
        'title': 'Kimi No Na Wa Kibou',
        'announced': '2013-01-06',
        'onSale': '2013-03-13',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956073508838985778/5.jpg',
    },
    {
        'number': 6,
        'title': "Girl's Rule",
        'announced': 'at 5th Single National Handshake Event, 2013-04-20',
        'onSale': '2013-07-03',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115367158235156/6.jpg',
    },
    {
        'number': 7,
        'title': 'Barette',
        'announced': '2013-10-06',
        'onSale': '2013-11-27',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115441296736266/7.jpg',
    },
    {
        'number': 8,
        'title': 'Kizuitara Kataomoi',
        'announced': '2014-01-26',
        'onSale': '2014-04-02',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115555117563914/8.jpg',
    },
    {
        'number': 9,
        'title': 'Natsu No Free & Easy',
        'announced': '2014-05-11',
        'onSale': '2014-07-09',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115655327883274/9.jpg',
    },
    {
        'number': 10,
        'title': 'Nandome No Aozora Ka?',
        'announced': '2014-08-03',
        'onSale': '2014-10-08',
        'image': 'https://media.discordapp.net/attachments/794492424713797642/956115727788691506/10.jpg',
    },
    {
        'number': 11,
        'title': 'Inochi Wa Utsukushii',
        'announced': '2015-01-18',
        'onSale': '2015-03-18',
    },
    {
        'number': 12,
        'title': 'Taiyou Knock',
        'announced': '2015-05-10',
        'onSale': '2015-07-22',
    },
    {
        'number': 13,
        'title': 'Ima, Hanashitai Dareka Ga Iru',
        'announced': '2015-08-30',
        'onSale': '2015-10-28',
    },
    {
        'number': 14,
        'title': 'Harujion Ga Sakukoro',
        'announced': '2016-01-31',
        'onSale': '2016-03-23',
    },
    {
        'number': 15,
        'title': 'Hadashi De Summer',
        'announced': '2016-06-05',
        'onSale': '2016-07-27',
    },
    {
        'number': 16,
        'title': 'Sayonara No Imi',
        'announced': '2016-10-16',
        'onSale': '2016-11-09',
    },
    {
        'number': 17,
        'title': 'Influencer',
        'announced': '2017-01-29',
        'onSale': '2017-03-22',
    },
    {
        'number': 18,
        'title': 'Nigemizu',
        'announced': '2017-07-09',
        'onSale': '2017-08-09',
    },
    {
        'number': 19,
        'title': 'Ituka Dekiru Nara Kyou Dekiru',
        'announced': '2017-09-03',
        'onSale': '2017-10-11',
    },
    {
        'number': 20,
        'title': 'Synchronicity',
        'announced': '2018-03-11',
        'onSale': '2018-04-25',
    },
    {
        'number': 21,
        'title': 'Single 21',
        'announced': 'Not provided in the original source',
        'onSale': 'Not provided in the original source',
    },
    {
        'number': 22,
        'title': 'Single 22',
        'announced': 'Not provided in the original source',
        'onSale': 'Not provided in the original source',
    },
]

# ============================================================
# Discord setup
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# guild_id -> voice channel_id
target_voice_channels: dict[int, int] = {}

# guild_id -> asyncio.Task
voice_reconnect_tasks: dict[int, asyncio.Task] = {}

# Guilds currently inside a disconnect/connect recovery transition.
voice_reconnect_in_progress: set[int] = set()

# Active reminder tasks.
reminder_tasks: set[asyncio.Task] = set()


@dataclass
class MusicTrack:
    requested_url: str
    title: str
    stream_url: str


# guild_id -> queued tracks and currently playing track
music_queues: dict[int, deque[MusicTrack]] = {}
music_current: dict[int, MusicTrack] = {}
music_text_channels: dict[int, discord.abc.Messageable] = {}
music_loop_modes: dict[int, str] = {}


def random_item(items):
    return random.choice(items)


async def send_message(message: discord.Message, content: str) -> None:
    await message.channel.send(content)


async def send_single_keyword_image(
    message: discord.Message,
    image_url: str,
) -> None:
    """Send a keyword image as one attachment, without an extra embed."""
    with tempfile.TemporaryDirectory(prefix="sora10chan-response-") as directory:
        image_path = await asyncio.to_thread(
            download_image_url,
            image_url,
            directory,
            "keyword-response",
        )
        if image_path is None:
            await send_message(message, image_url)
            return

        await message.channel.send(file=discord.File(str(image_path)))


class OpenGraphImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag != "meta" or self.image_url is not None:
            return

        attributes = dict(attrs)
        property_name = attributes.get("property") or attributes.get("name")
        if property_name in ("og:image", "twitter:image"):
            self.image_url = attributes.get("content")


def download_image_url(
    image_url: str,
    directory: str,
    filename: str,
) -> Path | None:
    url_extension = Path(urlparse(image_url).path).suffix.lower()
    if "dst-jpg" in image_url or url_extension == ".heic":
        url_extension = ".jpg"
    extension = url_extension or ".jpg"
    temporary_path = Path(directory) / f"{filename}.download"
    request = Request(image_url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=30) as response, temporary_path.open("wb") as output:
            content_type = response.headers.get_content_type()
            extension = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
            }.get(content_type, extension)
            shutil.copyfileobj(response, output)
    except OSError:
        return None

    image_path = Path(directory) / f"{filename}{extension}"
    temporary_path.replace(image_path)
    return image_path


def download_open_graph_image(url: str, directory: str) -> Path | None:
    """Download an image exposed in a supported page's metadata."""
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    parser = OpenGraphImageParser()

    try:
        with urlopen(request, timeout=30) as response:
            parser.feed(response.read().decode("utf-8", errors="ignore"))
    except (OSError, UnicodeError):
        return None

    if not parser.image_url:
        return None

    image_url = urljoin(url, parser.image_url)
    return download_image_url(image_url, directory, "open-graph-image")


def download_tiktok_photo(url: str, directory: str) -> list[Path]:
    """Download images from a TikTok photo post page."""
    api_url = f"https://www.tikwm.com/api/?url={quote(url, safe='')}"
    api_request = Request(
        api_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )

    try:
        with urlopen(api_request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}

    api_images = (payload.get("data") or {}).get("images") or []
    paths = []
    for image_index, image_url in enumerate(api_images, start=1):
        image_path = download_image_url(
            image_url,
            directory,
            f"tiktok-photo-{image_index}",
        )
        if image_path is not None:
            paths.append(image_path)

    if paths:
        return paths

    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", errors="ignore")
    except (OSError, UnicodeError):
        return []

    image_urls = re.findall(
        r'"(?:imageURL|image_url|display_image|originCover)"\s*:\s*'
        r'"((?:\\.|[^"\\])+)',
        page,
        re.IGNORECASE,
    )
    image_urls.extend(
        re.findall(
            r'https?:\\?/\\?/[^"\'\s]+(?:\.jpe?g|\.png|\.webp|\.avif)'
            r'(?:[^"\'\s]*)',
            page,
            re.IGNORECASE,
        )
    )
    image_urls.extend(
        re.findall(
            r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)'
            r'["\'][^>]+content=["\']([^"\']+)',
            page,
            re.IGNORECASE,
        )
    )

    paths = []
    for image_index, image_url in enumerate(dict.fromkeys(image_urls), start=1):
        image_url = unescape(image_url).replace(r"\/", "/")
        image_path = download_image_url(
            image_url,
            directory,
            f"tiktok-photo-{image_index}",
        )
        if image_path is not None:
            paths.append(image_path)

    return paths


def download_instagram_images(url: str, directory: str) -> list[Path]:
    """Download all images exposed by an Instagram post or carousel."""
    match = INSTAGRAM_POST_PATTERN.search(url)
    if match is None:
        return []

    shortcode = match.group(1)
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    img_index_values = []
    for key in ("img_index", "index"):
        values = query_params.get(key, [])
        for value in values:
            try:
                img_index_values.append(int(value))
            except ValueError:
                continue

    extra_page_urls: list[str] = []
    if img_index_values:
        for index in range(1, max(img_index_values) + 2):
            extra_page_urls.append(f"https://www.instagram.com/p/{shortcode}/?img_index={index}&stkn={query_params.get('stkn', [''])[0]}")

    page_urls = [
        f"https://www.instagram.com/p/{shortcode}/",
        f"https://www.instagram.com/p/{shortcode}/embed/captioned/",
        *extra_page_urls,
    ]
    pages = []
    for page_url in dict.fromkeys(page_urls):
        request = Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=30) as response:
                pages.append(response.read().decode("utf-8", errors="ignore"))
        except OSError:
            continue

    if not pages:
        return []

    sidecar_paths = download_instagram_sidecar_images(url, directory)
    if sidecar_paths:
        return sidecar_paths

    image_urls = []
    for page in pages:
        embedded_image_urls = re.findall(
            r'EmbeddedMediaImage[^>]*?src=["\']([^"\']+)',
            page,
            re.IGNORECASE,
        )
        escaped_image_urls = []
        search_position = 0
        while True:
            marker_position = page.lower().find("display_url", search_position)
            if marker_position < 0:
                break

            url_start = page.find("https:", marker_position)
            next_field = page.find("display_resources", url_start)
            next_display = page.lower().find("display_url", url_start)
            field_positions = [position for position in (next_field, next_display) if position >= 0]
            next_field = min(field_positions) if field_positions else len(page)
            if url_start >= 0:
                escaped_image_urls.append(page[url_start:next_field].rstrip('\\",'))
            search_position = marker_position + len("display_url")

        meta_image_urls = re.findall(
            r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',
            page,
            re.IGNORECASE,
        )

        image_urls.extend(embedded_image_urls)
        image_urls.extend(escaped_image_urls)
        image_urls.extend(meta_image_urls)

    cleaned_urls = []
    for image_url in image_urls:
        cleaned = (
            unescape(image_url)
            .replace(r"\/", "/")
            .replace(r"\u0026", "&")
            .replace(r"\u00253D", "%3D")
            .replace("&amp;", "&")
            .replace("\\", "")
        )
        if re.search(r"\.(?:jpe?g|png|webp|avif)(?:\?|$)", cleaned, re.IGNORECASE) and (
            "cdninstagram" in cleaned or "scontent" in cleaned or "fbcdn" in cleaned
        ):
            cleaned_urls.append(cleaned)

    unique_urls = list(dict.fromkeys(cleaned_urls))
    paths = []
    content_hashes: set[bytes] = set()
    for image_index, image_url in enumerate(unique_urls, start=1):
        image_path = download_image_url(
            image_url,
            directory,
            f"instagram-{shortcode}-{image_index}",
        )
        if image_path is None:
            continue

        digest = hashlib.sha256(image_path.read_bytes()).digest()
        if digest in content_hashes:
            image_path.unlink(missing_ok=True)
            continue

        content_hashes.add(digest)
        paths.append(image_path)

    if paths:
        return paths

    og_image = download_open_graph_image(url, directory)
    if og_image is not None:
        return [og_image]

    public_page_image = download_open_graph_image(f"https://www.instagram.com/p/{shortcode}/", directory)
    if public_page_image is not None:
        return [public_page_image]

    return []


def download_instagram_sidecar_images(url: str, directory: str) -> list[Path]:
    """Use Instaloader to fetch the actual child images from an Instagram carousel."""
    match = INSTAGRAM_POST_PATTERN.search(url)
    if match is None:
        return []

    shortcode = match.group(1)
    try:
        loader = instaloader.Instaloader()
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
    except Exception as exc:  # pragma: no cover - defensive fallback.
        logger.warning("Instaloader could not fetch Instagram post %s: %s", shortcode, exc)
        return []

    paths: list[Path] = []
    content_hashes: set[bytes] = set()

    try:
        nodes = list(post.get_sidecar_nodes())
    except Exception as exc:  # pragma: no cover - defensive fallback.
        logger.warning("Instaloader could not enumerate carousel nodes for %s: %s", shortcode, exc)
        return []

    for image_index, node in enumerate(nodes, start=1):
        image_url = getattr(node, "display_url", None)
        if not image_url:
            continue

        image_path = download_image_url(
            image_url,
            directory,
            f"instagram-{shortcode}-{image_index}",
        )
        if image_path is None:
            continue

        digest = hashlib.sha256(image_path.read_bytes()).digest()
        if digest in content_hashes:
            image_path.unlink(missing_ok=True)
            continue

        content_hashes.add(digest)
        paths.append(image_path)

    return paths


def download_social_media(url: str, directory: str) -> list[Path]:
    """Download videos or images from a supported social-media item."""
    is_twitter_status = TWITTER_TWEET_ID_PATTERN.search(url) is not None
    is_instagram_post = INSTAGRAM_POST_PATTERN.search(url) is not None

    if is_twitter_status:
        twitter_image = download_twitter_image(url, directory)
        if twitter_image is not None:
            return [twitter_image]

    options = {
        "noplaylist": not is_instagram_post,
        "outtmpl": str(Path(directory) / "%(id)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
    }

    with YoutubeDL(options) as downloader:
        try:
            info = downloader.extract_info(url, download=False)
        except DownloadError:
            twitter_image = download_twitter_image(url, directory)
            if twitter_image is not None:
                return [twitter_image]
            if is_twitter_status:
                raise DownloadError("No image was found in the Twitter/X post")
            instagram_images = download_instagram_images(url, directory)
            if instagram_images:
                return instagram_images
            tiktok_photos = download_tiktok_photo(url, directory)
            if tiktok_photos:
                return tiktok_photos
            open_graph_image = download_open_graph_image(url, directory)
            if open_graph_image is not None:
                return [open_graph_image]
            raise

        entries = list(info.get("entries") or [info])

        video_entry = next(
            (entry for entry in entries if entry.get("formats")),
            None,
        )

        if video_entry is not None:
            downloader.download([url])
        else:
            if is_twitter_status:
                raise DownloadError("No image was found in the Twitter/X post")
            instagram_images = download_instagram_images(url, directory)
            if instagram_images:
                return instagram_images
            image_entry = next(
                (
                    entry for entry in entries
                    if entry.get("thumbnail") or entry.get("url")
                ),
                None,
            )
            if image_entry is None:
                twitter_image = download_twitter_image(url, directory)
                if twitter_image is not None:
                    return [twitter_image]
                open_graph_image = download_open_graph_image(url, directory)
                if open_graph_image is not None:
                    return [open_graph_image]
                raise DownloadError("No video or image was found")

            image_url = image_entry.get("thumbnail") or image_entry.get("url")
            image_path = download_image_url(
                image_url,
                directory,
                str(image_entry.get("id", "image")),
            )
            if image_path is None:
                raise DownloadError("The image could not be downloaded")

    files = [path for path in Path(directory).iterdir() if path.is_file()]
    if not files:
        raise DownloadError("No media file was downloaded")

    if is_instagram_post:
        return sorted(files, key=lambda path: path.stat().st_mtime)

    return [max(files, key=lambda path: path.stat().st_mtime)]


def download_twitter_image(url: str, directory: str) -> Path | None:
    """Download the first public image exposed by a Twitter/X post."""
    match = TWITTER_TWEET_ID_PATTERN.search(url)
    if match is None:
        return None

    tweet_id = match.group(1)
    syndication_token = f"{int(tweet_id) / 1e15:.15g}"
    endpoint = (
        "https://cdn.syndication.twimg.com/tweet-result?"
        f"id={tweet_id}&lang=en&token={syndication_token}"
    )
    request = Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=30) as response:
            tweet_data = json.load(response)
    except (OSError, json.JSONDecodeError):
        return None

    media = next(
        (
            item for item in tweet_data.get("mediaDetails", [])
            if item.get("type") == "photo" and item.get("media_url_https")
        ),
        None,
    )
    if media is None:
        return None

    return download_image_url(
        media["media_url_https"],
        directory,
        f"twitter-{tweet_id}",
    )


async def extract_social_media(message: discord.Message, url: str) -> None:
    """Download and send a supported social-media link."""
    with tempfile.TemporaryDirectory(prefix="sora10chan-media-") as directory:
        try:
            async with message.channel.typing():
                media_paths = await asyncio.to_thread(
                    download_social_media,
                    url,
                    directory,
                )
        except DownloadError:
            await message.reply(
                "I couldn't extract media from that link. It may be private, "
                "unsupported, or require a login.",
                mention_author=False,
            )
            return
        except Exception:
            logger.exception("Social-media extraction failed for %s", url)
            await message.reply(
                "Something went wrong while downloading that media.",
                mention_author=False,
            )
            return

        if any(path.stat().st_size > MAX_MEDIA_BYTES for path in media_paths):
            size_mb = MAX_MEDIA_BYTES / (1024 * 1024)
            await message.reply(
                f"That media is too large for me to upload. The limit is "
                f"{size_mb:.0f} MB.",
                mention_author=False,
            )
            return

        try:
            if len(media_paths) == 1:
                await message.reply(
                    file=discord.File(str(media_paths[0])),
                    mention_author=False,
                )
            else:
                for batch_start in range(0, len(media_paths), 10):
                    batch = media_paths[batch_start:batch_start + 10]
                    files = [discord.File(str(path)) for path in batch]
                    if batch_start == 0:
                        await message.reply(files=files, mention_author=False)
                    else:
                        await message.channel.send(files=files)
        except discord.HTTPException:
            logger.exception("Discord rejected extracted media for %s", url)
            await message.reply(
                "Discord could not upload that media file.",
                mention_author=False,
            )


async def find_social_media_url(message: discord.Message) -> str | None:
    """Find a supported URL in a message or the message it replies to."""
    match = SOCIAL_MEDIA_URL_PATTERN.search(message.content)
    if match:
        return match.group(0)

    reference = message.reference
    if reference is None or reference.message_id is None:
        return None

    referenced_message = reference.resolved
    if not isinstance(referenced_message, discord.Message):
        if not hasattr(message.channel, "fetch_message"):
            return None
        try:
            referenced_message = await message.channel.fetch_message(
                reference.message_id
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    match = SOCIAL_MEDIA_URL_PATTERN.search(referenced_message.content)
    return match.group(0) if match else None


# ============================================================
# Voice connection handling
# ============================================================

def schedule_voice_reconnect(guild_id: int, channel_id: int) -> None:
    """Schedule one reconnect attempt after five seconds."""
    if target_voice_channels.get(guild_id) != channel_id:
        return
    if guild_id in voice_reconnect_in_progress:
        return

    existing = voice_reconnect_tasks.get(guild_id)
    if existing is not None and not existing.done():
        return

    async def retry() -> None:
        try:
            await asyncio.sleep(5)
            voice_reconnect_in_progress.add(guild_id)
            await reconnect_voice(guild_id, channel_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning(
                "Sora10Chan voice reconnect attempt encountered an error: %s",
                error,
            )
        finally:
            voice_reconnect_in_progress.discard(guild_id)
            voice_reconnect_tasks.pop(guild_id, None)

        guild = bot.get_guild(guild_id)
        connection = guild.voice_client if guild is not None else None
        if target_voice_channels.get(guild_id) == channel_id and (
            connection is None or not connection.is_connected()
        ):
            schedule_voice_reconnect(guild_id, channel_id)

    voice_reconnect_tasks[guild_id] = asyncio.create_task(retry())


async def reconnect_voice(guild_id: int, channel_id: int) -> None:
    if target_voice_channels.get(guild_id) != channel_id:
        return

    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    channel = guild.get_channel(channel_id)

    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except discord.DiscordException:
            target_voice_channels.pop(guild_id, None)
            logger.warning(
                "Sora10Chan stopped voice recovery because the target "
                "channel no longer exists: guild=%s channel=%s",
                guild_id,
                channel_id,
            )
            return

    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        target_voice_channels.pop(guild_id, None)
        logger.warning(
            "Sora10Chan stopped voice recovery because the target "
            "channel is no longer a voice channel: guild=%s channel=%s",
            guild_id,
            channel_id,
        )
        return

    existing = guild.voice_client

    if existing is not None:
        if existing.is_connected():
            return
        try:
            await existing.disconnect(force=True)
        except discord.DiscordException:
            pass

    try:
        await channel.connect(self_deaf=True)
        logger.info(
            "Sora10Chan is connected to the voice channel: guild=%s channel=%s",
            guild_id,
            channel_id,
        )
    except Exception as error:
        logger.warning(
            "Sora10Chan voice recovery attempt failed: guild=%s channel=%s error=%s",
            guild_id,
            channel_id,
            error,
        )


MUSIC_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com|youtu\.be|open\.spotify\.com)/",
    re.IGNORECASE,
)


def _spotify_track_title(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
        page = response.read().decode("utf-8", errors="replace")

    def meta_content(property_name: str) -> str | None:
        tag_match = re.search(
            rf"<meta\b(?=[^>]*\bproperty=[\"']{property_name}[\"'])"
            rf"(?=[^>]*\bcontent=[\"']([^\"']+))[^>]*>",
            page,
            re.IGNORECASE,
        )
        return unescape(tag_match.group(1)).strip() if tag_match else None

    title = meta_content("og:title")
    description = meta_content("og:description")
    if title is None:
        raise ValueError("Spotify did not provide track metadata")
    return f"{title} {description or ''}".strip()


def _spotify_playlist_queries(url: str) -> list[str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
        page = response.read().decode("utf-8", errors="replace")

    row_pattern = re.compile(
        r'href="/track/[A-Za-z0-9]+"><p[^>]*data-encore-id="listRowTitle"'
        r'[^>]*>.*?<span[^>]*>(.*?)</span></p></a>.*?'
        r'data-testid="internal-artist-link".*?<a[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    queries = []
    for title, artist in row_pattern.findall(page):
        title = re.sub(r"<[^>]+>", "", unescape(title)).strip()
        artist = re.sub(r"<[^>]+>", "", unescape(artist)).strip()
        if title:
            queries.append(f"{title} {artist}".strip())

    if not queries:
        raise ValueError("Spotify did not provide any tracks for that playlist")
    return queries[:MAX_SPOTIFY_PLAYLIST_TRACKS]


def resolve_music_requests(url: str) -> list[str]:
    url = url.strip()
    if MUSIC_URL_PATTERN.match(url) is None:
        if not url:
            raise ValueError("Enter a song title or a YouTube/Spotify link")
        return [f"ytsearch1:{url}"]

    parsed_url = urlparse(url)
    hostname = (parsed_url.hostname or "").lower()
    if hostname == "open.spotify.com":
        path = parsed_url.path.lower()
        if path.startswith("/track/"):
            return [f"ytsearch1:{_spotify_track_title(url)}"]
        if path.startswith("/playlist/"):
            return [f"ytsearch1:{query}" for query in _spotify_playlist_queries(url)]
        raise ValueError("Use a Spotify track or playlist link")
    return [url]


def resolve_music_track(url: str) -> MusicTrack:
    url = url.strip()
    if not url.startswith("ytsearch1:") and MUSIC_URL_PATTERN.match(url) is None:
        raise ValueError("Only YouTube and Spotify links are supported")

    lookup = url

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
        "file_access_retries": 3,
        "http_headers": {
            "User-Agent": BROWSER_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    if YOUTUBE_COOKIES_FILE:
        cookie_path = Path(YOUTUBE_COOKIES_FILE).expanduser()
        if cookie_path.is_file():
            options["cookiefile"] = str(cookie_path)
        else:
            logger.warning("Configured YOUTUBE_COOKIES_FILE does not exist: %s", cookie_path)
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(lookup, download=False)

    if info is None:
        raise ValueError("No playable result was found")
    if "entries" in info:
        info = next((entry for entry in info["entries"] if entry), None)
    if info is None or not info.get("url"):
        raise ValueError("No playable audio stream was found")

    return MusicTrack(
        requested_url=url,
        title=format_music_title(info, url),
        stream_url=info["url"],
    )


async def ensure_music_voice(
    guild: discord.Guild,
    member: discord.Member,
) -> discord.VoiceClient:
    if member.voice is None or member.voice.channel is None:
        raise ValueError("Join a voice channel first")

    channel = member.voice.channel
    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        raise ValueError("That is not a voice channel")

    connection = guild.voice_client
    target_voice_channels[guild.id] = channel.id
    if connection is None:
        connection = await channel.connect(self_deaf=True)
    elif connection.channel is None or connection.channel.id != channel.id:
        await connection.move_to(channel)
    return connection


async def start_next_music_track(guild_id: int) -> None:
    if guild_id in music_current:
        return

    queue = music_queues.get(guild_id)
    guild = bot.get_guild(guild_id)
    connection = guild.voice_client if guild is not None else None
    if not queue or guild is None or connection is None or not connection.is_connected():
        if queue is not None and not queue:
            music_queues.pop(guild_id, None)
        return

    track = queue.popleft()
    music_current[guild_id] = track
    try:
        track = await asyncio.to_thread(resolve_music_track, track.requested_url)
        music_current[guild_id] = track
        source = discord.FFmpegPCMAudio(
            track.stream_url,
            executable=FFMPEG_PATH,
            before_options=(
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
                f'-headers "User-Agent: {BROWSER_USER_AGENT}\\r\\n"'
            ),
            options="-vn",
        )

        def after_playback(error: Exception | None) -> None:
            if error:
                logger.warning("Music playback failed in guild %s: %s", guild_id, error)
            bot.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(finish_music_track(guild_id))
            )

        connection.play(source, after=after_playback)
        channel = music_text_channels.get(guild_id)
        if channel is not None:
            await channel.send(embed=music_now_playing_embed(track))
    except Exception as error:
        music_current.pop(guild_id, None)
        logger.warning("Could not start music in guild %s: %s", guild_id, error)
        channel = music_text_channels.get(guild_id)
        if channel is not None:
            clean_error = re.sub(r"\x1b\[[0-9;]*m", "", str(error)).strip()
            await channel.send(f"I couldn't play that link: {clean_error}")
        await start_next_music_track(guild_id)


async def finish_music_track(guild_id: int) -> None:
    track = music_current.pop(guild_id, None)
    loop_mode = music_loop_modes.get(guild_id)
    if track is not None and loop_mode == "track":
        music_queues.setdefault(guild_id, deque()).appendleft(
            MusicTrack(
                requested_url=track.requested_url,
                title=track.title,
                stream_url="",
            )
        )
    elif track is not None and loop_mode == "queue":
        music_queues.setdefault(guild_id, deque()).append(track)
    await start_next_music_track(guild_id)


async def queue_music_track(
    guild: discord.Guild,
    member: discord.Member,
    channel: discord.abc.Messageable,
    url: str,
) -> str:
    await ensure_music_voice(guild, member)
    music_text_channels[guild.id] = channel
    requests = await asyncio.to_thread(resolve_music_requests, url)
    queue = music_queues.setdefault(guild.id, deque())
    start_position = len(queue) + (1 if guild.id in music_current else 0) + 1
    queue.extend(
        MusicTrack(requested_url=request, title=request, stream_url="")
        for request in requests
    )
    await start_next_music_track(guild.id)
    if len(requests) == 1:
        return f"Queued at position {start_position}."
    return f"Queued {len(requests)} tracks starting at position {start_position}."

def music_track_label(track: MusicTrack) -> str:
    """Return a user-facing title without the internal search prefix."""
    return re.sub(r"^ytsearch1:\s*", "", track.title).strip()


def format_music_title(info: dict, fallback: str) -> str:
    title = (info.get("title") or fallback).strip()
    artist = info.get("artist") or info.get("uploader") or info.get("channel")
    if isinstance(artist, str):
        artist = artist.strip()
    if artist and artist.casefold() not in title.casefold():
        return f"{title} - {artist}"
    return title


def shuffle_music_queue(guild_id: int) -> int:
    queue = music_queues.get(guild_id)
    if not queue:
        return 0
    tracks = list(queue)
    random.shuffle(tracks)
    queue.clear()
    queue.extend(tracks)
    return len(tracks)


def clear_music_queue(guild_id: int) -> int:
    queue = music_queues.pop(guild_id, None)
    return len(queue) if queue else 0


def music_now_playing_embed(track: MusicTrack) -> discord.Embed:
    return discord.Embed(
        title="Now playing",
        description=f"**{music_track_label(track)}**",
        color=discord.Color.green(),
    )


def music_queue_embed(guild_id: int) -> discord.Embed:
    embed = discord.Embed(title="Music queue", color=discord.Color.blurple())
    current = music_current.get(guild_id)
    queued = music_queues.get(guild_id, deque())
    if current:
        embed.add_field(
            name="Now playing",
            value=music_track_label(current),
            inline=False,
        )
    queued_tracks = list(queued)
    for chunk_start in range(0, len(queued_tracks), 15):
        chunk = queued_tracks[chunk_start:chunk_start + 15]
        embed.add_field(
            name="Up next" if chunk_start == 0 else "Up next (continued)",
            value="\n".join(
                f"`{chunk_start + index}` {music_track_label(track)}"
                for index, track in enumerate(chunk, 1)
            ),
            inline=False,
        )
    if not current and not queued_tracks:
        embed.description = "The queue is empty."
    return embed


def music_queue_lines(guild_id: int) -> list[str]:
    current = music_current.get(guild_id)
    queued = music_queues.get(guild_id, deque())
    lines = [f"Now playing: **{music_track_label(current)}**"] if current else []
    lines.extend(
        f"{index}. {music_track_label(track)}"
        for index, track in enumerate(queued, 1)
    )
    return lines


def parse_duration(value: str) -> int | None:
    """Convert values like '3days 2hours 1minute' to seconds."""
    pattern = re.compile(
        r"(?P<amount>\d+)\s*(?P<unit>d(?:ays?)?|h(?:ours?)?|m(?:in(?:ute)?s?)?)",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(value))

    if not matches or "".join(match.group(0) for match in matches).replace(" ", "") != value.replace(" ", ""):
        return None

    total_seconds = 0
    for match in matches:
        amount = int(match.group("amount"))
        unit = match.group("unit").lower()
        if unit.startswith("d"):
            total_seconds += amount * 86400
        elif unit.startswith("h"):
            total_seconds += amount * 3600
        else:
            total_seconds += amount * 60

    return total_seconds if total_seconds > 0 else None


# ============================================================
# Bot events
# ============================================================

@bot.event
async def on_ready():
    logger.info(
        "Sora10Chan is online as %s in %d guild(s)",
        bot.user,
        len(bot.guilds),
    )

    try:
        synced = await bot.tree.sync()
        logger.info(
            "Registered %d slash command(s): %s",
            len(synced),
            ", ".join(command.name for command in synced),
        )
    except Exception:
        logger.exception("Discord slash command registration failed")


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    # Only react to changes involving the bot itself.
    if bot.user is None or member.id != bot.user.id:
        return

    guild_id = member.guild.id
    channel_id = target_voice_channels.get(guild_id)

    if channel_id is None:
        return

    if after.channel is None or after.channel.id != channel_id:
        schedule_voice_reconnect(guild_id, channel_id)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()
    command = content.lower()
    username = message.author.name

    if command == "!s" or command.startswith("!s "):
        await bot.process_commands(message)
        return

    sora_match = re.fullmatch(r"!sora(?:\s+(.+))?", content, re.IGNORECASE)
    if sora_match:
        url = sora_match.group(1)
        url_match = SOCIAL_MEDIA_URL_PATTERN.search(url or "")
        if url_match is None:
            await message.reply(
                "Use `!sora <Facebook, TikTok, Instagram, Twitter, or X link>.",
                mention_author=False,
            )
            return

        await extract_social_media(message, url_match.group(0))
        return

    if command == "*ashu":
        await send_message(message, random_item(ASUKA_IMAGES))
        return

    if command == "door":
        await send_message(message, random_item(DOOR_IMAGES))
        return

    direct_responses = {
        "nice": RESPONSES["nice"],
        "wtf": RESPONSES["wtf"],
        "sorry": RESPONSES["sorry"],
        "gomen": RESPONSES["sorry"],
        "i see": RESPONSES["see"],
    }

    direct_response = direct_responses.get(command)
    if direct_response:
        if command in ("nice", "wtf"):
            await send_single_keyword_image(message, direct_response)
        else:
            await send_message(message, direct_response)
        return

    if command in ("good morning", "ohayou"):
        await send_message(message, "おはよう！")
        await send_message(message, RESPONSES["morning"])
        return

    if command in ("good night", "oyasumi"):
        await send_message(message, "おやすみ！")
        await send_message(message, RESPONSES["night"])
        return

    if command == "sad":
        await send_message(message, "sad link")
        return

    sembatsu_match = re.fullmatch(r"\*sembatsu\s+(\d{1,2})", command)

    if sembatsu_match:
        number = int(sembatsu_match.group(1))
        entry = next(
            (item for item in SEMBATSU_ENTRIES if item["number"] == number),
            None,
        )

        if entry is None:
            await send_message(
                message,
                "Sembatsu entries are available from 1 through 22.",
            )
            return

        await send_message(
            message,
            f'{entry["number"]}th Single: {entry["title"]}, '
            f'Sembatsu Announced {entry["announced"]}, '
            f'On Sale {entry["onSale"]}',
        )

        if entry.get("image"):
            await send_message(message, entry["image"])
        elif entry["number"] >= 21:
            await send_message(message, "LOL")
            await send_message(
                message,
                "The original source did not include an image link for this entry.",
            )
        else:
            await send_message(
                message,
                "The original source did not include an image link for this entry.",
            )
        return

    # Preserve the original behavior: hello/bye only work in #bot.
    if isinstance(message.channel, discord.TextChannel):
        if message.channel.name == "bot" and command == "hello":
            await send_message(message, f"hello {username}")
        elif message.channel.name == "bot" and command == "bye":
            await send_message(message, f"bye {username}")


# ============================================================
# Slash commands
# ============================================================

@bot.tree.command(
    name="ping",
    description="Check whether Sora10Chan is responding",
)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! WebSocket latency: {round(bot.latency * 1000)}ms"
    )


@bot.tree.command(
    name="test",
    description="Run a quick Sora10Chan test",
)
async def test(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Sora10Chan slash commands are working!"
    )


@bot.tree.command(
    name="download",
    description="Download media from Facebook, TikTok, Instagram, or X",
)
async def download(interaction: discord.Interaction, url: str):
    await send_downloaded_media(interaction, url)


@bot.tree.command(
    name="media",
    description="Extract an image, video, or carousel from a social link",
)
async def media(interaction: discord.Interaction, url: str):
    await send_downloaded_media(interaction, url)


async def send_downloaded_media(
    interaction: discord.Interaction,
    url: str,
) -> None:
    url = url.strip()
    if SOCIAL_MEDIA_URL_PATTERN.fullmatch(url) is None:
        await interaction.response.send_message(
            "Use a Facebook, TikTok, Instagram, Twitter, or X link.",
            ephemeral=True,
        )
        return

    await interaction.response.defer()

    with tempfile.TemporaryDirectory(prefix="sora10chan-media-") as directory:
        try:
            media_paths = await asyncio.to_thread(
                download_social_media,
                url,
                directory,
            )
        except DownloadError:
            await interaction.followup.send(
                "I couldn't extract media from that link. It may be private, "
                "unsupported, or require a login."
            )
            return
        except Exception:
            logger.exception("Slash-command media extraction failed for %s", url)
            await interaction.followup.send(
                "Something went wrong while downloading that media."
            )
            return

        if any(path.stat().st_size > MAX_MEDIA_BYTES for path in media_paths):
            size_mb = MAX_MEDIA_BYTES / (1024 * 1024)
            await interaction.followup.send(
                f"That media is too large for me to upload. The limit is "
                f"{size_mb:.0f} MB."
            )
            return

        try:
            if len(media_paths) == 1:
                await interaction.followup.send(
                    file=discord.File(str(media_paths[0]))
                )
            else:
                for batch_start in range(0, len(media_paths), 10):
                    batch = media_paths[batch_start:batch_start + 10]
                    files = [discord.File(str(path)) for path in batch]
                    await interaction.followup.send(files=files)
        except discord.HTTPException:
            logger.exception("Discord rejected slash-command media for %s", url)
            await interaction.followup.send(
                "Discord could not upload that media file."
            )


@bot.tree.command(
    name="reminder",
    description="Remind you after a duration, such as 3d 2h 1m",
)
async def reminder(
    interaction: discord.Interaction,
    duration: str,
    text: str,
):
    seconds = parse_duration(duration)
    if seconds is None:
        await interaction.response.send_message(
            "Use a duration like `3d 2h 1m`, `3days 2hours 1minute`, "
            "or `30m`.",
            ephemeral=True,
        )
        return

    if interaction.channel is None:
        await interaction.response.send_message(
            "I couldn't find the channel for this reminder.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"Reminder set for <t:{int(time.time()) + seconds}:R>.",
        ephemeral=True,
    )

    channel = interaction.channel
    user = interaction.user

    async def deliver_reminder() -> None:
        try:
            await asyncio.sleep(seconds)
            await channel.send(f"{user.mention} Reminder: {text}")
        except discord.DiscordException:
            logger.exception("Could not deliver reminder for user %s", user.id)
        finally:
            reminder_tasks.discard(asyncio.current_task())

    task = asyncio.create_task(deliver_reminder())
    reminder_tasks.add(task)


@bot.tree.command(
    name="join",
    description="Join your current voice channel",
)
async def join(interaction: discord.Interaction):
    await interaction.response.defer()

    if interaction.guild is None:
        await interaction.followup.send(
            "This command can only be used inside a server."
        )
        return

    member = interaction.guild.get_member(interaction.user.id)

    if member is None:
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except discord.DiscordException:
            await interaction.followup.send(
                "I couldn't find your member information."
            )
            return

    if member.voice is None or member.voice.channel is None:
        await interaction.followup.send(
            "Join a voice channel first, then use `/join` again."
        )
        return

    voice_channel = member.voice.channel

    if not isinstance(
        voice_channel,
        (discord.VoiceChannel, discord.StageChannel),
    ):
        await interaction.followup.send(
            "I couldn't connect to that voice channel."
        )
        return

    guild_id = interaction.guild.id
    channel_id = voice_channel.id

    target_voice_channels[guild_id] = channel_id

    existing = interaction.guild.voice_client

    try:
        if existing is not None:
            if existing.channel and existing.channel.id == channel_id:
                await interaction.followup.send(
                    f"Already in <#{channel_id}>."
                )
                return

            await existing.move_to(voice_channel)
        else:
            await voice_channel.connect(self_deaf=True)

        logger.info(
            "Sora10Chan joined voice channel: guild=%s channel=%s",
            guild_id,
            channel_id,
        )

        await interaction.followup.send(f"Joined <#{channel_id}>.")

    except Exception as error:
        target_voice_channels.pop(guild_id, None)
        logger.warning(
            "Sora10Chan could not join the requested voice channel: %s",
            error,
        )

        await interaction.followup.send(
            "I couldn't connect to that voice channel. "
            "Please check that I have the Connect permission "
            "and that the channel is not full."
        )


@bot.tree.command(
    name="leave",
    description="Leave the current voice channel",
)
async def leave(interaction: discord.Interaction):
    await interaction.response.defer()

    if interaction.guild is None:
        await interaction.followup.send(
            "This command can only be used inside a server."
        )
        return

    guild_id = interaction.guild.id

    target_voice_channels.pop(guild_id, None)
    music_queues.pop(guild_id, None)
    music_current.pop(guild_id, None)
    music_text_channels.pop(guild_id, None)
    music_loop_modes.pop(guild_id, None)

    task = voice_reconnect_tasks.pop(guild_id, None)
    if task is not None and not task.done():
        task.cancel()

    connection = interaction.guild.voice_client

    if connection is None:
        await interaction.followup.send(
            "I am not currently in a voice channel."
        )
        return

    if connection.is_playing() or connection.is_paused():
        connection.stop()
    await connection.disconnect()
    await interaction.followup.send("Left the voice channel.")


@bot.tree.command(
    name="play",
    description="Play or queue a song title, YouTube link, or Spotify track/playlist",
)
async def play(interaction: discord.Interaction, url: str):
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "This command can only be used inside a server.", ephemeral=True
        )
        return
    await interaction.response.defer()
    try:
        message = await queue_music_track(
            interaction.guild,
            interaction.user,
            interaction.channel or interaction.guild,
            url,
        )
    except (ValueError, discord.DiscordException) as error:
        await interaction.followup.send(str(error))
        return
    await interaction.followup.send(message)


@bot.tree.command(name="skip", description="Skip the current track")
async def skip(interaction: discord.Interaction):
    if interaction.guild is None or interaction.guild.voice_client is None:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return
    connection = interaction.guild.voice_client
    if not connection.is_playing() and not connection.is_paused():
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return
    await interaction.response.send_message("Skipped.")
    connection.stop()


@bot.tree.command(name="next", description="Move to the next track")
async def next_track(interaction: discord.Interaction):
    await skip(interaction)


@bot.tree.command(name="shuffle", description="Shuffle the queued tracks")
async def shuffle(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.", ephemeral=True
        )
        return
    count = shuffle_music_queue(interaction.guild.id)
    if count == 0:
        await interaction.response.send_message("The queue is empty.", ephemeral=True)
        return
    await interaction.response.send_message(f"Shuffled {count} queued tracks.")


@bot.tree.command(
    name="loop",
    description="Loop the current track, the queue, or turn looping off",
)
async def loop(interaction: discord.Interaction, mode: str):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.", ephemeral=True
        )
        return

    mode = mode.lower().strip()
    if mode not in ("track", "queue", "off"):
        await interaction.response.send_message(
            "Choose `track`, `queue`, or `off`.", ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    if mode == "off":
        music_loop_modes.pop(guild_id, None)
        await interaction.response.send_message("Looping disabled.")
        return

    if (
        interaction.guild.voice_client is None
        or guild_id not in music_current
        and not music_queues.get(guild_id)
    ):
        await interaction.response.send_message(
            "There is no track or playlist to loop.", ephemeral=True
        )
        return

    music_loop_modes[guild_id] = mode
    label = "current track" if mode == "track" else "queue"
    await interaction.response.send_message(f"Looping {label}.")


@bot.tree.command(name="pause", description="Pause the current track")
async def pause(interaction: discord.Interaction):
    connection = interaction.guild.voice_client if interaction.guild else None
    if connection is None or not connection.is_playing():
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return
    connection.pause()
    await interaction.response.send_message("Paused.")


@bot.tree.command(name="resume", description="Resume the paused track")
async def resume(interaction: discord.Interaction):
    connection = interaction.guild.voice_client if interaction.guild else None
    if connection is None or not connection.is_paused():
        await interaction.response.send_message("Nothing is paused.", ephemeral=True)
        return
    connection.resume()
    await interaction.response.send_message("Resumed.")


@bot.tree.command(name="queue", description="Show the current music queue")
async def queue(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return
    await interaction.response.send_message(embed=music_queue_embed(interaction.guild.id))


@bot.tree.command(name="clear", description="Clear queued tracks without stopping the current song")
async def clear(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.", ephemeral=True
        )
        return
    count = clear_music_queue(interaction.guild.id)
    await interaction.response.send_message(
        f"Cleared {count} queued track{'s' if count != 1 else ''}."
    )


@bot.tree.command(name="stop", description="Stop music and clear the queue")
async def stop(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    music_queues.pop(guild_id, None)
    music_current.pop(guild_id, None)
    music_loop_modes.pop(guild_id, None)
    connection = interaction.guild.voice_client
    if connection is not None and (connection.is_playing() or connection.is_paused()):
        connection.stop()
    await interaction.response.send_message("Stopped and cleared the queue.")


@bot.group(name="s", invoke_without_command=True)
async def local_s(ctx: commands.Context):
    """Run a slash command locally with the !s prefix."""
    await ctx.send(
        "Use `!s ping`, `!s test`, `!s play <song title or url>`, `!s skip`, `!s pause`, "
        "`!s next`, `!s shuffle`, `!s resume`, `!s queue`, `!s clear`, "
        "`!s loop <track|queue|off>`, `!s stop`, "
        "`!s join`, or `!s leave`."
    )


@local_s.command(name="ping")
async def local_ping(ctx: commands.Context):
    await ctx.send(f"Pong! WebSocket latency: {round(bot.latency * 1000)}ms")


@local_s.command(name="test")
async def local_test(ctx: commands.Context):
    await ctx.send("Sora10Chan local commands are working!")


async def send_local_media(ctx: commands.Context, url: str) -> None:
    url_match = SOCIAL_MEDIA_URL_PATTERN.fullmatch(url.strip())
    if url_match is None:
        await ctx.send("Use a Facebook, TikTok, Instagram, Twitter, or X link.")
        return
    await extract_social_media(ctx.message, url_match.group(0))


@local_s.command(name="download")
async def local_download(ctx: commands.Context, url: str):
    await send_local_media(ctx, url)


@local_s.command(name="media")
async def local_media(ctx: commands.Context, url: str):
    await send_local_media(ctx, url)


@local_s.command(name="reminder")
async def local_reminder(ctx: commands.Context, duration: str, *, text: str):
    seconds = parse_duration(duration)
    if seconds is None:
        await ctx.send(
            "Use a duration like `3d 2h 1m`, `3days 2hours 1minute`, or `30m`."
        )
        return

    await ctx.send(f"Reminder set for <t:{int(time.time()) + seconds}:R>.")

    async def deliver_local_reminder() -> None:
        try:
            await asyncio.sleep(seconds)
            await ctx.send(f"{ctx.author.mention} Reminder: {text}")
        except discord.DiscordException:
            logger.exception("Could not deliver local reminder for user %s", ctx.author.id)
        finally:
            reminder_tasks.discard(asyncio.current_task())

    task = asyncio.create_task(deliver_local_reminder())
    reminder_tasks.add(task)


@local_s.command(name="play")
async def local_play(ctx: commands.Context, *, url: str):
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send("This command can only be used inside a server.")
        return
    try:
        message = await queue_music_track(ctx.guild, ctx.author, ctx.channel, url)
    except (ValueError, discord.DiscordException) as error:
        await ctx.send(str(error))
        return
    await ctx.send(message)


@local_s.command(name="skip")
async def local_skip(ctx: commands.Context):
    connection = ctx.guild.voice_client if ctx.guild else None
    if connection is None or not connection.is_playing() and not connection.is_paused():
        await ctx.send("Nothing is playing.")
        return
    connection.stop()
    await ctx.send("Skipped.")


@local_s.command(name="next")
async def local_next(ctx: commands.Context):
    connection = ctx.guild.voice_client if ctx.guild else None
    if connection is None or not connection.is_playing() and not connection.is_paused():
        await ctx.send("Nothing is playing.")
        return
    connection.stop()
    await ctx.send("Skipped.")


@local_s.command(name="shuffle")
async def local_shuffle(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return
    count = shuffle_music_queue(ctx.guild.id)
    if count == 0:
        await ctx.send("The queue is empty.")
        return
    await ctx.send(f"Shuffled {count} queued tracks.")


@local_s.command(name="loop")
async def local_loop(ctx: commands.Context, mode: str):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return

    mode = mode.lower().strip()
    if mode not in ("track", "queue", "off"):
        await ctx.send("Choose `track`, `queue`, or `off`.")
        return

    guild_id = ctx.guild.id
    if mode == "off":
        music_loop_modes.pop(guild_id, None)
        await ctx.send("Looping disabled.")
        return

    if (
        ctx.guild.voice_client is None
        or guild_id not in music_current
        and not music_queues.get(guild_id)
    ):
        await ctx.send("There is no track or playlist to loop.")
        return

    music_loop_modes[guild_id] = mode
    label = "current track" if mode == "track" else "queue"
    await ctx.send(f"Looping {label}.")


@local_s.command(name="pause")
async def local_pause(ctx: commands.Context):
    connection = ctx.guild.voice_client if ctx.guild else None
    if connection is None or not connection.is_playing():
        await ctx.send("Nothing is playing.")
        return
    connection.pause()
    await ctx.send("Paused.")


@local_s.command(name="resume")
async def local_resume(ctx: commands.Context):
    connection = ctx.guild.voice_client if ctx.guild else None
    if connection is None or not connection.is_paused():
        await ctx.send("Nothing is paused.")
        return
    connection.resume()
    await ctx.send("Resumed.")


@local_s.command(name="queue")
async def local_queue(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return
    await ctx.send(embed=music_queue_embed(ctx.guild.id))


@local_s.command(name="clear")
async def local_clear(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return
    count = clear_music_queue(ctx.guild.id)
    await ctx.send(f"Cleared {count} queued track{'s' if count != 1 else ''}.")


@local_s.command(name="nowplaying")
async def local_nowplaying(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return
    current = music_current.get(ctx.guild.id)
    if current is None:
        await ctx.send("Nothing is playing.")
        return
    await ctx.send(embed=music_now_playing_embed(current))


@local_s.command(name="stop")
async def local_stop(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return
    guild_id = ctx.guild.id
    music_queues.pop(guild_id, None)
    music_current.pop(guild_id, None)
    music_loop_modes.pop(guild_id, None)
    connection = ctx.guild.voice_client
    if connection is not None and (connection.is_playing() or connection.is_paused()):
        connection.stop()
    await ctx.send("Stopped and cleared the queue.")


@local_s.command(name="join")
async def local_join(ctx: commands.Context):
    if ctx.guild is None or ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("Join a voice channel first, then use `!s join` again.")
        return

    voice_channel = ctx.author.voice.channel
    if not isinstance(voice_channel, (discord.VoiceChannel, discord.StageChannel)):
        await ctx.send("I couldn't connect to that voice channel.")
        return

    existing = ctx.guild.voice_client
    target_voice_channels[ctx.guild.id] = voice_channel.id
    try:
        if existing is not None:
            await existing.move_to(voice_channel)
        else:
            await voice_channel.connect(self_deaf=True)
        await ctx.send(f"Joined <#{voice_channel.id}>.")
    except Exception:
        target_voice_channels.pop(ctx.guild.id, None)
        logger.exception("Could not join voice channel from local command")
        await ctx.send("I couldn't connect to that voice channel.")


@local_s.command(name="leave")
async def local_leave(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return

    target_voice_channels.pop(ctx.guild.id, None)
    music_queues.pop(ctx.guild.id, None)
    music_current.pop(ctx.guild.id, None)
    music_text_channels.pop(ctx.guild.id, None)
    music_loop_modes.pop(ctx.guild.id, None)
    task = voice_reconnect_tasks.pop(ctx.guild.id, None)
    if task is not None and not task.done():
        task.cancel()

    connection = ctx.guild.voice_client
    if connection is None:
        await ctx.send("I am not currently in a voice channel.")
        return

    if connection.is_playing() or connection.is_paused():
        connection.stop()
    await connection.disconnect()
    await ctx.send("Left the voice channel.")


# ============================================================
# Start
# ============================================================

if __name__ == "__main__":
    if not TOKEN:
        logger.warning(
            "DISCORD_TOKEN is not configured; Discord bot is disabled"
        )
    else:
        try:
            bot.run(TOKEN)
        except Exception:
            logger.exception("Sora10Chan could not connect to Discord")
