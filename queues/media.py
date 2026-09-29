import asyncio
import json
import logging
import mimetypes
import tempfile
from pathlib import Path

import requests
from vercel.queue import Message, subscribe

from main import MAX_MEDIA_BYTES, download_social_media


logger = logging.getLogger("Sora10Chan.VercelQueue")
DISCORD_API = "https://discord.com/api/v10"


def send_webhook_message(
    application_id: str,
    interaction_token: str,
    paths: list[Path],
) -> None:
    webhook_url = f"{DISCORD_API}/webhooks/{application_id}/{interaction_token}"

    if not paths:
        response = requests.patch(
            f"{webhook_url}/messages/@original",
            json={"content": "I couldn't extract media from that link."},
            timeout=(10, 30),
        )
        response.raise_for_status()
        return

    for batch_start in range(0, len(paths), 10):
        batch = paths[batch_start:batch_start + 10]
        attachments = []
        files = []
        opened_files = []
        try:
            for index, path in enumerate(batch):
                file_handle = path.open("rb")
                opened_files.append(file_handle)
                attachments.append({"id": index, "filename": path.name})
                files.append((
                    f"files[{index}]",
                    (path.name, file_handle, mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
                ))

            payload = {"attachments": attachments}
            if batch_start == 0:
                response = requests.patch(
                    f"{webhook_url}/messages/@original",
                    data={"payload_json": json.dumps(payload)},
                    files=files,
                    timeout=(10, 120),
                )
            else:
                response = requests.post(
                    webhook_url,
                    params={"wait": "true"},
                    data={"payload_json": json.dumps(payload)},
                    files=files,
                    timeout=(10, 120),
                )
            response.raise_for_status()
        finally:
            for file_handle in opened_files:
                file_handle.close()


@subscribe(topic="sora-social-media", max_attempts=1)
async def process_social_media(message: Message[dict[str, str]]) -> None:
    payload = message.payload
    application_id = payload["application_id"]
    interaction_token = payload["interaction_token"]

    try:
        with tempfile.TemporaryDirectory(prefix="sora10chan-media-") as directory:
            paths = await asyncio.to_thread(
                download_social_media,
                payload["url"],
                directory,
            )
            if any(path.stat().st_size > MAX_MEDIA_BYTES for path in paths):
                size_mb = MAX_MEDIA_BYTES / (1024 * 1024)
                response = requests.patch(
                    f"{DISCORD_API}/webhooks/{application_id}/{interaction_token}/messages/@original",
                    json={"content": f"That media is too large to upload. The limit is {size_mb:.0f} MB."},
                    timeout=(10, 30),
                )
                response.raise_for_status()
                return

            await asyncio.to_thread(
                send_webhook_message,
                application_id,
                interaction_token,
                paths,
            )
    except Exception:
        logger.exception("Vercel could not process media for interaction %s", message.message_id)
        try:
            response = requests.patch(
                f"{DISCORD_API}/webhooks/{application_id}/{interaction_token}/messages/@original",
                json={"content": "Something went wrong while downloading or uploading that media."},
                timeout=(10, 30),
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Could not report media failure to Discord")