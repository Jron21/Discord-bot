import json
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from vercel.queue import send

from main import SOCIAL_MEDIA_URL_PATTERN


app = FastAPI()
MEDIA_TOPIC = "sora-social-media"
PING = {"type": 1}


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