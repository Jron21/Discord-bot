import json
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from vercel.queue import send

from main import BOT_OWNER_ID, SOCIAL_MEDIA_URL_PATTERN


app = FastAPI()
MEDIA_TOPIC = "sora-social-media"
SERVER_LIST_TOPIC = "sora-server-list"
PING = {"type": 1}
logger = logging.getLogger("Sora10Chan.VercelInteractions")


def interaction_response(content: str, response_type: int = 4) -> JSONResponse:
    return JSONResponse({"type": response_type, "data": {"content": content}})


def verify_discord_request(timestamp: str, signature: str, body: bytes) -> bool:
    public_key = os.getenv("DISCORD_PUBLIC_KEY")
    if not public_key:
        raise RuntimeError("DISCORD_PUBLIC_KEY is not configured")

    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
        VerifyKey(bytes.fromhex(public_key)).verify(
            timestamp.encode("ascii") + body,
            bytes.fromhex(signature),
        )
    except (ValueError, BadSignatureError):
        return False

    return True


def find_option(options: list[dict], name: str) -> str | None:
    return next(
        (option.get("value") for option in options if option.get("name") == name),
        None,
    )


@app.post("/")
async def interactions(request: Request) -> JSONResponse:
    body = await request.body()
    timestamp = request.headers.get("x-signature-timestamp", "")
    signature = request.headers.get("x-signature-ed25519", "")

    try:
        is_valid = verify_discord_request(timestamp, signature, body)
    except RuntimeError:
        return JSONResponse({"error": "Interaction endpoint is not configured"}, status_code=503)

    if not is_valid:
        return JSONResponse({"error": "Invalid request signature"}, status_code=401)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if payload.get("type") == 1:
        return JSONResponse(PING)

    if payload.get("type") != 2:
        return interaction_response("This interaction type is not supported.")

    data = payload.get("data") or {}
    command = data.get("name")
    if command == "ping":
        return interaction_response("Pong! Sora10Chan is online.")
    if command == "test":
        return interaction_response("Sora10Chan slash commands are working!")
    if command == "servers":
        member = payload.get("member") or {}
        user = member.get("user") or payload.get("user") or {}
        if user.get("id") != str(BOT_OWNER_ID):
            return JSONResponse({
                "type": 4,
                "data": {
                    "content": "Only the bot owner can use this command.",
                    "flags": 64,
                },
            })

        try:
            await send(
                SERVER_LIST_TOPIC,
                {
                    "application_id": payload["application_id"],
                    "interaction_token": payload["token"],
                },
                delay=2,
                idempotency_key=payload["id"],
            )
        except Exception:
            logger.exception("Could not queue the server-list request")
            return JSONResponse({
                "type": 4,
                "data": {
                    "content": "I couldn't start the server-list request. Please try again.",
                    "flags": 64,
                },
            })
        return JSONResponse({"type": 5, "data": {"flags": 64}})
    if command not in {"download", "media"}:
        return interaction_response("That command is not available on Vercel.")

    url = find_option(data.get("options") or [], "url")
    if not isinstance(url, str) or SOCIAL_MEDIA_URL_PATTERN.fullmatch(url.strip()) is None:
        return interaction_response(
            "Use a Facebook, TikTok, Instagram, Twitter, or X link."
        )

    try:
        await send(
            MEDIA_TOPIC,
            {
                "application_id": payload["application_id"],
                "interaction_token": payload["token"],
                "url": url.strip(),
            },
            delay=2,
            idempotency_key=payload["id"],
        )
    except Exception:
        return interaction_response("I could not queue that media request. Please try again.")

    return JSONResponse({"type": 5})