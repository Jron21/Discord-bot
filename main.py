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
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse, urlunparse
from html.parser import HTMLParser
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import discord
from dotenv import load_dotenv
from discord.ext import commands
from yt_dlp import DownloadError, YoutubeDL

try:
    import instaloader
except ImportError:
    instaloader = None

load_dotenv()


# ============================================================
# Configuration
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
MAX_MEDIA_BYTES = int(os.getenv("MAX_MEDIA_BYTES", 24 * 1024 * 1024))
INSTAGRAM_COOKIE = os.getenv("INSTAGRAM_COOKIE", "").strip()
INSTAGRAM_COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "").strip()
XIAOHONGSHU_COOKIE = os.getenv("XIAOHONGSHU_COOKIE", "").strip()
_INSTAGRAM_COOKIE_TEMP_DIR = None


def get_instagram_cookie_file() -> str | None:
    """Return a Netscape cookie file for yt-dlp, creating one from the env cookie if needed."""
    global _INSTAGRAM_COOKIE_TEMP_DIR

    if INSTAGRAM_COOKIES_FILE:
        cookie_path = Path(INSTAGRAM_COOKIES_FILE).expanduser()
        if cookie_path.is_file():
            return str(cookie_path)
        logger.warning(
            "Configured INSTAGRAM_COOKIES_FILE does not exist: %s",
            cookie_path,
        )

    if not INSTAGRAM_COOKIE:
        return None

    if _INSTAGRAM_COOKIE_TEMP_DIR is None:
        _INSTAGRAM_COOKIE_TEMP_DIR = tempfile.TemporaryDirectory(
            prefix="instagram-cookies-"
        )

    cookie_lines = ["# Netscape HTTP Cookie File"]
    for item in INSTAGRAM_COOKIE.split(";"):
        name, separator, value = item.strip().partition("=")
        if not separator or not name or not value:
            continue
        if any(char in name + value for char in "\r\n\t"):
            continue
        cookie_lines.append(
            f".instagram.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}"
        )

    if len(cookie_lines) == 1:
        return None

    cookie_path = Path(_INSTAGRAM_COOKIE_TEMP_DIR.name) / "cookies.txt"
    cookie_path.write_text("\n".join(cookie_lines) + "\n", encoding="utf-8")
    try:
        cookie_path.chmod(0o600)
    except OSError:
        pass
    return str(cookie_path)


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
XIAOHONGSHU_MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
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
    r"xiaohongshu\.com|rednote\.com|xhslink\.com|"
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


def normalize_xiaohongshu_url(url: str) -> str:
    """Unwrap RedNote share login pages into yt-dlp's Xiaohongshu URL form."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host in {"rednote.com", "www.rednote.com"} and parsed.path.rstrip("/") == "/login":
        redirect_path = parse_qs(parsed.query).get("redirectPath", [None])[0]
        if redirect_path:
            url = redirect_path
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()

    if host in {"rednote.com", "www.rednote.com"}:
        path = re.sub(r"^/discovery/item/", "/explore/", parsed.path)
        if path != parsed.path:
            return urlunparse((
                "https",
                "www.xiaohongshu.com",
                path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))

    return url


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
    headers: dict[str, str] | None = None,
) -> Path | None:
    url_extension = Path(urlparse(image_url).path).suffix.lower()
    if "dst-jpg" in image_url or url_extension == ".heic":
        url_extension = ".jpg"
    extension = url_extension or ".jpg"
    temporary_path = Path(directory) / f"{filename}.download"
    request_headers = {"User-Agent": "Mozilla/5.0"}
    if headers:
        request_headers.update(headers)
    request = Request(image_url, headers=request_headers)

    try:
        with urlopen(request, timeout=30) as response, temporary_path.open("wb") as output:
            content_type = response.headers.get_content_type()
            lower_url = image_url.lower()
            extension = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "image/avif": ".avif",
                "video/mp4": ".mp4",
                "video/webm": ".webm",
                "video/quicktime": ".mov",
                "video/x-matroska": ".mkv",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "audio/ogg": ".ogg",
                "audio/webm": ".webm",
                "application/octet-stream": (
                    ".mp4" if "mp4" in lower_url or "video" in lower_url
                    else ".mp3" if "mp3" in lower_url or "audio" in lower_url
                    else extension
                ),
            }.get(content_type, extension)
            shutil.copyfileobj(response, output)
    except OSError:
        return None

    image_path = Path(directory) / f"{filename}{extension}"
    temporary_path.replace(image_path)
    return image_path


def extract_xiaohongshu_image_urls(page: str) -> list[str]:
    """Extract one best-quality CDN URL per image from page-state arrays."""
    image_urls = []
    for image_list_match in re.finditer(r'"imageList"\s*:\s*\[', page):
        array_start = image_list_match.end() - 1
        depth = 0
        in_string = False
        escaped = False
        array_end = None
        for index in range(array_start, len(page)):
            char = page[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    array_end = index
                    break
        if array_end is None:
            continue

        try:
            image_items = json.loads(page[array_start:array_end + 1])
        except json.JSONDecodeError:
            continue
        if not isinstance(image_items, list):
            continue

        for image_item in image_items:
            if not isinstance(image_item, dict):
                continue
            variants = [
                variant
                for variant in image_item.get("infoList", [])
                if isinstance(variant, dict) and isinstance(variant.get("url"), str)
            ]
            scene_priority = {
                "WB_ORG": 0,
                "H5_DTL": 0,
                "WB_DFT": 1,
                "H5_PRV": 2,
            }
            variants.sort(
                key=lambda variant: scene_priority.get(
                    variant.get("imageScene"), 3
                )
            )
            image_url = (
                variants[0]["url"]
                if variants
                else image_item.get("url")
            )
            if not isinstance(image_url, str):
                continue

            parsed_image_url = urlparse(image_url)
            host = (parsed_image_url.hostname or "").lower()
            if (
                parsed_image_url.scheme in {"http", "https"}
                and (
                    host.endswith(".xhscdn.com")
                    or host == "xhscdn.com"
                    or host.endswith(".rednotecdn.com")
                    or host == "rednotecdn.com"
                )
            ):
                if parsed_image_url.scheme == "http":
                    image_url = parsed_image_url._replace(scheme="https").geturl()
                image_urls.append(image_url)

    return list(dict.fromkeys(image_urls))


def download_xiaohongshu_page_images(
    url: str,
    directory: str,
    post_id: str,
) -> list[Path]:
    """Read image URLs from the page state when yt-dlp misses RedNote's new schema."""
    headers = {
        "User-Agent": XIAOHONGSHU_MOBILE_USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.xiaohongshu.com/",
    }
    if XIAOHONGSHU_COOKIE and not any(
        char in XIAOHONGSHU_COOKIE for char in "\r\n"
    ):
        headers["Cookie"] = XIAOHONGSHU_COOKIE

    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            page = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("Could not read Xiaohongshu page data for %s: %s", post_id, exc)
        return []

    image_urls = extract_xiaohongshu_image_urls(page)
    paths = []
    seen_keys = set()
    for image_index, image_url in enumerate(image_urls):
        parsed_image_url = urlparse(image_url)
        image_key = (parsed_image_url.hostname, parsed_image_url.path)
        if image_key in seen_keys:
            continue
        seen_keys.add(image_key)
        image_path = download_image_url(
            image_url,
            directory,
            f"xiaohongshu-{post_id}-{image_index}",
            headers=headers,
        )
        if image_path is not None:
            paths.append(image_path)

    return paths


def download_instagram_video_url(
    video_url: str,
    directory: str,
    filename: str,
) -> Path | None:
    temporary_path = Path(directory) / f"{filename}.download"
    video_path = Path(directory) / f"{filename}.mp4"
    request = Request(video_url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=30) as response, temporary_path.open("wb") as output:
            shutil.copyfileobj(response, output)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        return None

    temporary_path.replace(video_path)
    return video_path


def sha256_file(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def dedupe_media_paths(paths: list[Path]) -> list[Path]:
    """Return a list of unique files, removing duplicates by content hash."""
    unique_paths: list[Path] = []
    seen_hashes: set[bytes] = set()

    for path in paths:
        if not path.exists() or not path.is_file():
            continue

        digest = sha256_file(path)
        if digest in seen_hashes:
            path.unlink(missing_ok=True)
            continue

        seen_hashes.add(digest)
        unique_paths.append(path)

    return unique_paths


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


def _is_video_tiktok_media_url(media_url: str) -> bool:
    lower_url = media_url.lower()
    query = parse_qs(urlparse(media_url).query)
    mime_type = query.get("mime_type", [""])[0].lower()

    if "audio" in mime_type or "audio" in lower_url or "music" in lower_url:
        return False
    if "video" in mime_type or "video" in lower_url:
        return True
    if re.search(r"(?:\.mp4|\.mov|\.webm)(?:\?|$)", lower_url):
        return True
    return False


def _is_image_tiktok_media_url(media_url: str) -> bool:
    lower_url = media_url.lower()
    if _is_video_tiktok_media_url(media_url):
        return False
    if "audio" in lower_url or "music" in lower_url:
        return False
    if re.search(r"(?:\.jpe?g|\.png|\.webp|\.avif|\.gif|\.heic)(?:\?|$)", lower_url):
        return True
    return False


def _tiktok_media_url_strings(value: object) -> list[str]:
    if isinstance(value, str):
        media_url = unescape(value).replace(r"\/", "/")
        parsed_url = urlparse(media_url)
        if parsed_url.scheme in ("http", "https") and parsed_url.netloc:
            return [media_url]
        return []
    if isinstance(value, list):
        return [
            media_url
            for item in value
            for media_url in _tiktok_media_url_strings(item)
        ]
    if isinstance(value, dict):
        return [
            media_url
            for item in value.values()
            for media_url in _tiktok_media_url_strings(item)
        ]
    return []


def download_tiktok_media(url: str, directory: str) -> list[Path]:
    """Download direct video or image media from a TikTok post or share link."""
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
        return []

    data = payload.get("data") or {}

    live_video_urls: list[str] = []
    video_fallback_images: dict[str, list[str]] = {}
    video_urls: list[str] = []
    image_urls: list[str] = []
    cover_urls: list[str] = []

    live_image_items = data.get("live_images")
    image_items = data.get("images")
    if (
        isinstance(live_image_items, list)
        and isinstance(image_items, list)
        and len(live_image_items) == len(image_items)
    ):
        for live_item, image_item in zip(live_image_items, image_items):
            live_item_urls = _tiktok_media_url_strings(live_item)
            slide_video_urls = [
                media_url
                for media_url in live_item_urls
                if _is_video_tiktok_media_url(media_url)
            ]
            slide_image_urls = [
                media_url
                for media_url in _tiktok_media_url_strings(image_item)
                if not _is_video_tiktok_media_url(media_url)
            ]
            if slide_video_urls:
                live_video_urls.extend(slide_video_urls)
                for media_url in slide_video_urls:
                    video_fallback_images.setdefault(media_url, []).extend(
                        slide_image_urls
                    )
            else:
                image_urls.extend(slide_image_urls)
                image_urls.extend(
                    media_url
                    for media_url in live_item_urls
                    if not _is_video_tiktok_media_url(media_url)
                )
    else:
        for media_url in _tiktok_media_url_strings(live_image_items):
            if _is_video_tiktok_media_url(media_url):
                live_video_urls.append(media_url)
            elif _is_image_tiktok_media_url(media_url):
                image_urls.append(media_url)

        image_urls.extend(
            media_url
            for media_url in _tiktok_media_url_strings(image_items)
            if not _is_video_tiktok_media_url(media_url)
        )

    for key in ("cover", "origin_cover", "ai_dynamic_cover"):
        value = data.get(key)
        if isinstance(value, str) and _is_image_tiktok_media_url(value):
            cover_urls.append(value)

    for key in (
        "play",
        "hdplay",
        "playAddr",
        "play_url",
        "video",
        "video_url",
    ):
        for media_url in _tiktok_media_url_strings(data.get(key)):
            if _is_video_tiktok_media_url(media_url):
                video_urls.append(media_url)
            elif _is_image_tiktok_media_url(media_url):
                image_urls.append(media_url)

    paths: list[Path] = []
    unique_live_video_urls = list(dict.fromkeys(live_video_urls))
    for media_index, media_url in enumerate(unique_live_video_urls, start=1):
        media_path = download_instagram_video_url(
            media_url,
            directory,
            f"tiktok-live-slide-{media_index}",
        )
        if media_path is not None:
            paths.append(media_path)
        else:
            image_urls.extend(video_fallback_images.get(media_url, []))

    if not unique_live_video_urls:
        for media_index, media_url in enumerate(dict.fromkeys(video_urls), start=1):
            if not _is_video_tiktok_media_url(media_url):
                continue
            media_path = download_instagram_video_url(
                media_url,
                directory,
                f"tiktok-media-{media_index}",
            )
            if media_path is not None:
                paths.append(media_path)
                break

    for media_index, media_url in enumerate(dict.fromkeys(image_urls), start=1):
        media_path = download_image_url(
            media_url,
            directory,
            f"tiktok-media-image-{media_index}",
        )
        if media_path is not None:
            paths.append(media_path)

    deduped_paths = dedupe_media_paths(paths)
    if deduped_paths:
        return deduped_paths

    cover_paths = []
    for media_index, media_url in enumerate(dict.fromkeys(cover_urls), start=1):
        media_path = download_image_url(
            media_url,
            directory,
            f"tiktok-cover-{media_index}",
        )
        if media_path is not None:
            cover_paths.append(media_path)

    deduped_paths = dedupe_media_paths(cover_paths)
    if deduped_paths:
        return deduped_paths

    return dedupe_media_paths(download_tiktok_photo(url, directory))


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

    api_images = _tiktok_media_url_strings(
        (payload.get("data") or {}).get("images")
    )
    paths = []
    for image_index, image_url in enumerate(api_images, start=1):
        image_path = download_image_url(
            image_url,
            directory,
            f"tiktok-photo-{image_index}",
        )
        if image_path is not None:
            paths.append(image_path)

    deduped_paths = dedupe_media_paths(paths)
    if deduped_paths:
        return deduped_paths

    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", errors="ignore")
    except (OSError, UnicodeError):
        return []

    image_urls = re.findall(
        r'"(?:imageURL|image_url|display_image|originCover)"\s*:\s*'
        r'(?:"((?:\\.|[^"\\])+)")',
        page,
        re.IGNORECASE,
    )
    image_urls.extend(
        re.findall(
            r'"url[_-]?list"\s*:\s*\[\s*"((?:\\.|[^"\\])+)',
            page,
            re.IGNORECASE,
        )
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

    return dedupe_media_paths(paths)


def extract_balanced_json_container(page: str, start: int) -> str | None:
    """Return one JSON array/object from its opening bracket, respecting strings."""
    if start >= len(page) or page[start] not in "[{":
        return None

    closing_for = {"[": "]", "{": "}"}
    stack = []
    in_string = False
    escaped = False
    for index in range(start, len(page)):
        char = page[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            stack.append(closing_for[char])
        elif char in "]}":
            if not stack or char != stack.pop():
                return None
            if not stack:
                return page[start:index + 1]
    return None


def extract_instagram_image_urls(
    page: str,
    shortcode: str | None = None,
) -> tuple[list[str], list[str]]:
    """Return full image metadata URLs and preview URLs separately."""
    full_urls = re.findall(
        r'display_url\\?"\s*:\s*\\?"(https:[^"]+)',
        page,
        re.IGNORECASE,
    )

    if shortcode:
        target_match = re.search(
            rf'"code"\s*:\s*"{re.escape(shortcode)}"',
            page,
        )
        if target_match:
            target_data = page[target_match.end():]
            media_type_match = re.search(r'"media_type"\s*:\s*(\d+)', target_data[:8000])
            media_type = int(media_type_match.group(1)) if media_type_match else None
            carousel_marker = page.find('"carousel_media"', target_match.end())
            if carousel_marker >= 0 and (media_type is None or media_type == 8):
                array_start = page.find("[", carousel_marker)
                array_text = extract_balanced_json_container(page, array_start)
                try:
                    carousel_media = json.loads(array_text) if array_text else []
                except json.JSONDecodeError:
                    carousel_media = []
                if isinstance(carousel_media, list):
                    for item in carousel_media:
                        if not isinstance(item, dict) or item.get("media_type") == 2:
                            continue
                        candidates = (
                            (item.get("image_versions2") or {}).get("candidates") or []
                        )
                        valid_candidates = [
                            candidate
                            for candidate in candidates
                            if isinstance(candidate, dict)
                            and isinstance(candidate.get("url"), str)
                        ]
                        if valid_candidates:
                            best_candidate = max(
                                valid_candidates,
                                key=lambda candidate: (
                                    (candidate.get("width") or 0)
                                    * (candidate.get("height") or 0)
                                ),
                            )
                            full_urls.append(best_candidate["url"])
            elif media_type != 2:
                image_marker = page.find('"image_versions2"', target_match.end())
                if image_marker >= 0:
                    object_start = page.find("{", image_marker)
                    image_data_text = extract_balanced_json_container(page, object_start)
                    try:
                        image_data = json.loads(image_data_text) if image_data_text else {}
                    except json.JSONDecodeError:
                        image_data = {}
                    candidates = image_data.get("candidates", [])
                    valid_candidates = [
                        candidate
                        for candidate in candidates
                        if isinstance(candidate, dict)
                        and isinstance(candidate.get("url"), str)
                    ]
                    if valid_candidates:
                        best_candidate = max(
                            valid_candidates,
                            key=lambda candidate: (
                                (candidate.get("width") or 0)
                                * (candidate.get("height") or 0)
                            ),
                        )
                        full_urls.append(best_candidate["url"])

    preview_urls = []
    preview_patterns = [
        r'EmbeddedMediaImage[^>]*?src=["\']([^"\']+)',
        r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',
    ]
    for pattern in preview_patterns:
        preview_urls.extend(re.findall(pattern, page, re.IGNORECASE))

    def clean_urls(urls: list[str]) -> list[str]:
        cleaned_urls = []
        for image_url in urls:
            cleaned = (
                unescape(image_url)
                .replace(r"\/", "/")
                .replace(r"\u0026", "&")
                .replace(r"\u00253D", "%3D")
                .replace("&amp;", "&")
                .replace("\\", "")
            )
            parsed_url = urlparse(cleaned)
            hostname = (parsed_url.hostname or "").lower()
            is_instagram_cdn = (
                hostname == "cdninstagram.com"
                or hostname.endswith(".cdninstagram.com")
                or hostname == "fbcdn.net"
                or hostname.endswith(".fbcdn.net")
            )
            if (
                parsed_url.scheme.lower() == "https"
                and is_instagram_cdn
                and re.search(
                    r"\.(?:jpe?g|png|webp|avif)(?:\?|$)",
                    cleaned,
                    re.IGNORECASE,
                )
            ):
                cleaned_urls.append(cleaned)
        return list(dict.fromkeys(cleaned_urls))

    return clean_urls(full_urls), clean_urls(preview_urls)


def download_instagram_html_images(
    url: str,
    shortcode: str,
    directory: str,
) -> list[Path]:
    request_headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if INSTAGRAM_COOKIE:
        request_headers["Cookie"] = INSTAGRAM_COOKIE

    request = Request(
        url,
        headers=request_headers,
    )

    try:
        with urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        logger.warning(
            "Instagram page fallback returned HTTP %s for %s",
            exc.code,
            shortcode,
        )
        return []
    except URLError as exc:
        logger.warning(
            "Instagram page fallback connection failed for %s: %s",
            shortcode,
            exc.reason,
        )
        return []
    except (OSError, UnicodeError) as exc:
        logger.warning(
            "Instagram page fallback failed for %s: %s",
            shortcode,
            exc,
        )
        return []

    full_urls, preview_urls = extract_instagram_image_urls(page, shortcode)
    if not full_urls:
        logger.warning(
            "No full Instagram image metadata found for %s; "
            "skipping %s preview image(s)",
            shortcode,
            len(preview_urls),
        )
        return []

    query = parse_qs(urlparse(url).query)
    requested_index = next(
        (
            int(value)
            for value in query.get("img_index", [])
            if value.isdecimal() and int(value) > 0
        ),
        None,
    )
    has_carousel_metadata = (
        "edge_sidecar_to_children" in page
        or "carousel_media" in page
    )
    if (
        (requested_index is not None and len(full_urls) < requested_index)
        or (has_carousel_metadata and len(full_urls) < 2)
    ):
        logger.warning(
            "Instagram page metadata for %s appears incomplete "
            "(%s full image(s)); refusing a partial carousel",
            shortcode,
            len(full_urls),
        )
        return []

    paths = []
    failed_download = False
    for image_index, image_url in enumerate(full_urls, start=1):
        image_path = download_image_url(
            image_url,
            directory,
            f"instagram-{shortcode}-{image_index}",
        )
        if image_path is None:
            failed_download = True
            logger.warning(
                "Could not download Instagram image %s for %s",
                image_index,
                shortcode,
            )
            continue
        paths.append(image_path)

    if failed_download:
        logger.warning(
            "Instagram HTML fallback for %s was incomplete; "
            "not returning a partial carousel",
            shortcode,
        )
        return []

    result = dedupe_media_paths(paths)
    logger.info(
        "Instagram HTML fallback completed for %s: %s/%s images downloaded",
        shortcode,
        len(result),
        len(full_urls),
    )
    return result


def download_instagram_media(url: str, directory: str) -> list[Path]:
    """Download all available media from a public Instagram post or carousel."""
    match = INSTAGRAM_POST_PATTERN.search(url)
    if match is None:
        logger.warning("Invalid Instagram post URL")
        return []

    shortcode = match.group(1)
    instagram_home = "https://www.instagram.com/"
    graphql_url = "https://www.instagram.com/api/graphql"
    app_id = "936619743392459"
    doc_id = "27128499623469141"
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": instagram_home.rstrip("/"),
        "Referer": instagram_home,
        "X-IG-App-ID": app_id,
        "X-Requested-With": "XMLHttpRequest",
    }
    if INSTAGRAM_COOKIE:
        headers["Cookie"] = INSTAGRAM_COOKIE

    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))

    try:
        home_headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }
        if INSTAGRAM_COOKIE:
            home_headers["Cookie"] = INSTAGRAM_COOKIE
        home_request = Request(instagram_home, headers=home_headers)
        with opener.open(home_request, timeout=30) as response:
            home_page = response.read().decode("utf-8", errors="replace")

        web_api_tokens = {}
        for token_name, token_pattern in (
            ("fb_dtsg", r'"DTSGInitialData",\[\],\{[^{}]*"token":"([^"]+)"'),
            ("lsd", r'"LSD",\[\],\{[^{}]*"token":"([^"]+)"'),
            ("av", r'"IG_USER_EIMU":"?(\d+)'),
        ):
            token_match = re.search(token_pattern, home_page)
            if token_match:
                web_api_tokens[token_name] = token_match.group(1)

        csrf_token = next(
            (
                cookie.value
                for cookie in cookie_jar
                if cookie.name == "csrftoken"
            ),
            None,
        )
        if not csrf_token and INSTAGRAM_COOKIE:
            csrf_token = next(
                (
                    value.strip('"')
                    for item in INSTAGRAM_COOKIE.split(";")
                    for name, separator, value in [item.strip().partition("=")]
                    if separator and name.strip() == "csrftoken"
                ),
                None,
            )
        if not csrf_token:
            logger.warning(
                "Instagram did not provide a CSRF token for %s",
                shortcode,
            )
            return []

        variables = {
            "shortcode": shortcode,
            "__relay_internal__pv__PolarisAIGMMediaWebLabelEnabledrelayprovider": False,
        }
        payload = urlencode({
            "doc_id": doc_id,
            "variables": json.dumps(variables, separators=(",", ":")),
            "server_timestamps": "true",
            **web_api_tokens,
        }).encode("utf-8")
        graphql_request = Request(
            graphql_url,
            data=payload,
            headers={
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": csrf_token,
                **(
                    {"X-FB-LSD": web_api_tokens["lsd"]}
                    if "lsd" in web_api_tokens
                    else {}
                ),
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
            method="POST",
        )

        with opener.open(graphql_request, timeout=30) as response:
            response_data = json.loads(
                response.read().decode("utf-8", errors="replace")
            )
    except HTTPError as exc:
        logger.warning(
            "Instagram GraphQL request returned HTTP %s for %s",
            exc.code,
            shortcode,
        )
        return []
    except URLError as exc:
        logger.warning(
            "Instagram GraphQL connection failed for %s: %s",
            shortcode,
            exc.reason,
        )
        return []
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning(
            "Instagram GraphQL request failed for %s: %s",
            shortcode,
            exc,
        )
        return []

    if not isinstance(response_data, dict):
        logger.warning("Instagram returned an invalid response for %s", shortcode)
        return []

    data = response_data.get("data")
    media_container = (
        data.get("xdt_api__v1__media__shortcode__web_info")
        if isinstance(data, dict)
        else None
    )
    items = (
        media_container.get("items")
        if isinstance(media_container, dict)
        else None
    )
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        logger.warning(
            "Instagram returned no media items for %s. Response keys: %s",
            shortcode,
            list(response_data.keys()),
        )
        return []

    post = items[0]
    carousel_media = post.get("carousel_media")
    media_items = (
        carousel_media
        if isinstance(carousel_media, list) and carousel_media
        else [post]
    )
    logger.info(
        "Instagram extraction started for %s: %s media items",
        shortcode,
        len(media_items),
    )

    def candidate_quality(candidate: dict) -> tuple[int, int, int]:
        width = candidate.get("width")
        height = candidate.get("height")
        candidate_type = candidate.get("type")
        width = width if isinstance(width, int) and width > 0 else 0
        height = height if isinstance(height, int) and height > 0 else 0
        candidate_type = (
            candidate_type
            if isinstance(candidate_type, int) and candidate_type > 0
            else 0
        )
        return width * height, width, candidate_type

    paths: list[Path] = []
    content_hashes: set[bytes] = set()

    for image_index, media_item in enumerate(media_items, start=1):
        if not isinstance(media_item, dict):
            logger.warning(
                "Invalid Instagram media item %s for %s",
                image_index,
                shortcode,
            )
            continue

        is_video = (
            media_item.get("media_type") == 2
            or media_item.get("is_video") is True
        )
        filename = f"instagram-{shortcode}-{image_index}"

        if is_video:
            candidates = media_item.get("video_versions")
        else:
            image_versions = media_item.get("image_versions2")
            candidates = (
                image_versions.get("candidates")
                if isinstance(image_versions, dict)
                else None
            )

        valid_candidates = (
            [candidate for candidate in candidates if isinstance(candidate, dict)]
            if isinstance(candidates, list)
            else []
        )
        if not valid_candidates:
            logger.warning(
                "No %s candidates available for %s item %s",
                "video" if is_video else "image",
                shortcode,
                image_index,
            )
            continue

        best_candidate = max(valid_candidates, key=candidate_quality)
        media_url = best_candidate.get("url")
        if not isinstance(media_url, str) or not media_url:
            logger.warning(
                "Missing media URL for Instagram item %s of %s",
                image_index,
                shortcode,
            )
            continue

        try:
            media_path = (
                download_instagram_video_url(media_url, directory, filename)
                if is_video
                else download_image_url(media_url, directory, filename)
            )
            if media_path is None:
                logger.warning(
                    "Failed to download Instagram item %s for %s",
                    image_index,
                    shortcode,
                )
                continue

            digest = sha256_file(media_path)
            if digest in content_hashes:
                media_path.unlink(missing_ok=True)
                continue

            content_hashes.add(digest)
            paths.append(media_path)
        except OSError as exc:
            logger.warning(
                "Failed to process Instagram item %s for %s: %s",
                image_index,
                shortcode,
                exc,
            )

    result = dedupe_media_paths(paths)
    logger.info(
        "Instagram extraction completed for %s: %s/%s media downloaded",
        shortcode,
        len(result),
        len(media_items),
    )
    return result


def download_instagram_sidecar_media(url: str, directory: str) -> list[Path]:
    """Use Instaloader to fetch all child media from an Instagram carousel."""
    if instaloader is None:
        logger.warning("Instaloader is not installed; skipping Instagram carousel extraction")
        return []

    match = INSTAGRAM_POST_PATTERN.search(url)
    if match is None:
        return []

    shortcode = match.group(1)
    try:
        loader = instaloader.Instaloader()
        cookie_jar = getattr(loader.context, "_session", None)
        cookie_jar = getattr(cookie_jar, "cookies", None)
        if cookie_jar is not None and INSTAGRAM_COOKIE:
            for item in INSTAGRAM_COOKIE.split(";"):
                name, separator, value = item.strip().partition("=")
                if separator and name and value:
                    cookie_jar.set(
                        name,
                        value,
                        domain=".instagram.com",
                        path="/",
                        secure=True,
                    )
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
    except Exception as exc:  # pragma: no cover - defensive fallback.
        logger.warning("Instaloader could not fetch Instagram post %s: %s", shortcode, exc)
        return []

    paths: list[Path] = []
    content_hashes: set[bytes] = set()

    if getattr(post, "typename", None) == "GraphSidecar":
        try:
            nodes = list(post.get_sidecar_nodes())
        except Exception as exc:  # pragma: no cover - defensive fallback.
            logger.warning("Instaloader could not enumerate carousel nodes for %s: %s", shortcode, exc)
            return []
    else:
        nodes = [post]

    for image_index, node in enumerate(nodes, start=1):
        is_video = getattr(node, "is_video", False)
        media_url = (
            getattr(node, "video_url", None)
            if is_video
            else getattr(node, "display_url", None)
        )
        if not media_url:
            continue

        filename = f"instagram-{shortcode}-{image_index}"
        media_path = (
            download_instagram_video_url(media_url, directory, filename)
            if is_video
            else download_image_url(media_url, directory, filename)
        )
        if media_path is None:
            continue

        digest = sha256_file(media_path)
        if digest in content_hashes:
            media_path.unlink(missing_ok=True)
            continue

        content_hashes.add(digest)
        paths.append(media_path)

    return dedupe_media_paths(paths)


def download_instagram_info_media(
    info: dict,
    shortcode: str,
    directory: str,
) -> list[Path]:
    """Download each full image or video candidate returned by yt-dlp."""
    raw_entries = info.get("entries")
    entries = raw_entries if isinstance(raw_entries, list) and raw_entries else [info]
    paths: list[Path] = []

    def candidate_quality(candidate: dict) -> tuple[float, float, float]:
        width = candidate.get("width")
        height = candidate.get("height")
        tbr = candidate.get("tbr")
        width = float(width) if isinstance(width, (int, float)) and width > 0 else 0
        height = float(height) if isinstance(height, (int, float)) and height > 0 else 0
        tbr = float(tbr) if isinstance(tbr, (int, float)) and tbr > 0 else 0
        return width * height, width, tbr

    for media_index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue

        raw_formats = entry.get("formats")
        if isinstance(raw_formats, list) and raw_formats:
            candidates = [
                candidate
                for candidate in raw_formats
                if isinstance(candidate, dict)
                and isinstance(candidate.get("url"), str)
                and candidate["url"]
            ]
            is_video = True
        else:
            raw_thumbnails = entry.get("thumbnails")
            # yt-dlp maps Instagram image_versions2 candidates to this list;
            # the scalar `thumbnail` field is only a preview and is ignored.
            candidates = (
                [
                    candidate
                    for candidate in raw_thumbnails
                    if isinstance(candidate, dict)
                    and isinstance(candidate.get("url"), str)
                    and candidate["url"]
                ]
                if isinstance(raw_thumbnails, list)
                else []
            )
            is_video = False

        if not candidates:
            logger.warning(
                "No full %s candidate available for Instagram item %s of %s",
                "video" if is_video else "image",
                media_index,
                shortcode,
            )
            continue

        best_candidate = max(candidates, key=candidate_quality)
        media_url = best_candidate["url"]
        filename = f"instagram-{shortcode}-{media_index}"
        media_path = (
            download_instagram_video_url(media_url, directory, filename)
            if is_video
            else download_image_url(media_url, directory, filename)
        )
        if media_path is not None:
            paths.append(media_path)

    result = dedupe_media_paths(paths)
    logger.info(
        "Instagram yt-dlp extraction completed for %s: %s/%s media downloaded",
        shortcode,
        len(result),
        len(entries),
    )
    return result


def download_social_media(url: str, directory: str) -> list[Path]:
    """Download videos or images from a supported social-media item."""
    url = normalize_xiaohongshu_url(url)
    parsed_url = urlparse(url)
    if parsed_url.hostname and parsed_url.hostname.lower() in {
        "xhslink.com",
        "www.xhslink.com",
    }:
        # yt-dlp's XiaoHongShu extractor handles the destination URL, while
        # xhslink.com is only a share-link redirector.
        request = Request(
            url,
            headers={"User-Agent": XIAOHONGSHU_MOBILE_USER_AGENT},
        )
        try:
            with urlopen(request, timeout=20) as response:
                resolved_url = response.geturl()
            resolved_host = (urlparse(resolved_url).hostname or "").lower()
            if resolved_host == "xiaohongshu.com" or resolved_host.endswith(
                ".xiaohongshu.com"
            ) or resolved_host in {"rednote.com", "www.rednote.com"}:
                url = normalize_xiaohongshu_url(resolved_url)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            logger.warning("Could not resolve Xiaohongshu short link %s: %s", url, exc)

    is_twitter_status = TWITTER_TWEET_ID_PATTERN.search(url) is not None
    instagram_match = INSTAGRAM_POST_PATTERN.search(url)
    is_instagram_post = instagram_match is not None
    parsed_url = urlparse(url)
    is_tiktok_url = bool(parsed_url.hostname and "tiktok.com" in parsed_url.hostname.lower())
    is_xiaohongshu_url = bool(
        parsed_url.hostname
        and (
            parsed_url.hostname.lower() == "xiaohongshu.com"
            or parsed_url.hostname.lower().endswith(".xiaohongshu.com")
        )
    )

    if is_instagram_post:
        instagram_media = download_instagram_media(url, directory)
        if instagram_media:
            return instagram_media
        instagram_media = download_instagram_sidecar_media(url, directory)
        if instagram_media:
            return instagram_media

    if is_twitter_status:
        twitter_image = download_twitter_image(url, directory)
        if twitter_image is not None:
            return [twitter_image]

    if is_tiktok_url:
        tiktok_media = download_tiktok_media(url, directory)
        if tiktok_media:
            return tiktok_media

    options = {
        "noplaylist": not is_instagram_post,
        "outtmpl": str(Path(directory) / "%(id)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
    }
    if is_xiaohongshu_url:
        # Image-only Xiaohongshu notes have thumbnails but no video formats.
        options["ignore_no_formats_error"] = True
    if is_instagram_post:
        options["http_headers"] = {
            "User-Agent": BROWSER_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
        cookie_path = get_instagram_cookie_file()
        if cookie_path:
            options["cookiefile"] = cookie_path
    elif is_xiaohongshu_url:
        options["http_headers"] = {
            "User-Agent": XIAOHONGSHU_MOBILE_USER_AGENT,
            "Referer": "https://www.xiaohongshu.com/",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if XIAOHONGSHU_COOKIE and not any(
            char in XIAOHONGSHU_COOKIE for char in "\r\n"
        ):
            options["http_headers"]["Cookie"] = XIAOHONGSHU_COOKIE

    with YoutubeDL(options) as downloader:
        try:
            info = downloader.extract_info(url, download=False)
        except DownloadError:
            if instagram_match is not None:
                shortcode = instagram_match.group(1)
                instagram_media = download_instagram_html_images(
                    url,
                    shortcode,
                    directory,
                )
                if instagram_media:
                    return instagram_media
                raise DownloadError(
                    "Instagram did not provide downloadable media; "
                    "no full image metadata was available, so previews were skipped"
                ) from None
            twitter_image = download_twitter_image(url, directory)
            if twitter_image is not None:
                return [twitter_image]
            if is_twitter_status:
                raise DownloadError("No image was found in the Twitter/X post")
            if is_tiktok_url:
                tiktok_media = download_tiktok_media(url, directory)
                if tiktok_media:
                    return tiktok_media
            open_graph_image = download_open_graph_image(url, directory)
            if open_graph_image is not None:
                return [open_graph_image]
            raise

        if instagram_match is not None:
            shortcode = instagram_match.group(1)
            if not isinstance(info, dict):
                raise DownloadError(
                    "Instagram did not return usable media metadata"
                )
            instagram_media = download_instagram_info_media(
                info,
                shortcode,
                directory,
            )
            if instagram_media:
                return instagram_media
            instagram_media = download_instagram_html_images(
                url,
                shortcode,
                directory,
            )
            if instagram_media:
                return instagram_media
            raise DownloadError(
                "Instagram did not provide full media metadata; "
                "no full image metadata was available, so previews were skipped"
            )

        entries = list(info.get("entries") or [info])

        if is_xiaohongshu_url and not any(entry.get("formats") for entry in entries):
            image_paths = []
            seen_image_keys = set()
            thumbnail_count = 0
            for entry_index, entry in enumerate(entries):
                for image_index, thumbnail in enumerate(entry.get("thumbnails") or []):
                    image_url = thumbnail.get("url")
                    if not image_url:
                        continue
                    thumbnail_count += 1
                    image_parts = urlparse(image_url)
                    image_key = (
                        image_parts.hostname,
                        image_parts.path,
                    )
                    if image_key in seen_image_keys:
                        continue
                    seen_image_keys.add(image_key)
                    image_path = download_image_url(
                        image_url,
                        directory,
                        f"{entry.get('id', 'xiaohongshu')}-{entry_index}-{image_index}",
                        headers={
                            "User-Agent": XIAOHONGSHU_MOBILE_USER_AGENT,
                            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                            "Referer": "https://www.xiaohongshu.com/",
                            **(
                                {"Cookie": XIAOHONGSHU_COOKIE}
                                if XIAOHONGSHU_COOKIE
                                and not any(
                                    char in XIAOHONGSHU_COOKIE for char in "\r\n"
                                )
                                else {}
                            ),
                        },
                    )
                    if image_path is not None:
                        image_paths.append(image_path)
            if image_paths:
                return image_paths
            image_paths = download_xiaohongshu_page_images(
                url,
                directory,
                str(info.get("id") or "post"),
            )
            if image_paths:
                return image_paths
            logger.warning(
                "Xiaohongshu image extraction found %s thumbnails but downloaded %s",
                thumbnail_count,
                len(image_paths),
            )
            raise DownloadError(
                "Xiaohongshu returned no downloadable image URLs; the request may "
                "have been blocked or the note's media format may be unsupported."
            )

        video_entry = next(
            (entry for entry in entries if entry.get("formats")),
            None,
        )

        if video_entry is not None:
            downloader.download([url])
        else:
            if is_twitter_status:
                raise DownloadError("No image was found in the Twitter/X post")
            if is_tiktok_url:
                tiktok_media = download_tiktok_media(url, directory)
                if tiktok_media:
                    return tiktok_media
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

    files = dedupe_media_paths([path for path in Path(directory).iterdir() if path.is_file()])
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

        media_paths = dedupe_media_paths(media_paths)

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


# Temporarily disabled: personal-install tracking used by the /server report.


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
                "Use `!sora <Facebook, TikTok, Instagram, Xiaohongshu, Twitter, or X link>.",
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
@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(
    guilds=True,
    dms=True,
    private_channels=True,
)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! WebSocket latency: {round(bot.latency * 1000)}ms"
    )


@bot.tree.command(
    name="test",
    description="Run a quick Sora10Chan test",
)
@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(
    guilds=True,
    dms=True,
    private_channels=True,
)
async def test(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Sora10Chan slash commands are working!"
    )


# Temporarily disabled: the /server command and its database-backed report.


@bot.tree.command(
    name="download",
    description="Download media from Facebook, TikTok, Instagram, Xiaohongshu, or X",
)
@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(
    guilds=True,
    dms=True,
    private_channels=True,
)
async def download(interaction: discord.Interaction, url: str):
    await send_downloaded_media(interaction, url)


@bot.tree.command(
    name="media",
    description="Extract an image, video, or carousel from a social link",
)
@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(
    guilds=True,
    dms=True,
    private_channels=True,
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
            "Use a Facebook, TikTok, Instagram, Xiaohongshu, Twitter, or X link.",
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

        media_paths = dedupe_media_paths(media_paths)

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
        await ctx.send("Use a Facebook, TikTok, Instagram, Xiaohongshu, Twitter, or X link.")
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
