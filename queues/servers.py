import asyncio
import logging
import os

import requests
import psycopg
from vercel.queue import Message, subscribe

from install_tracking import (
    DatabaseNotConfiguredError,
    list_personal_install_users,
)


logger = logging.getLogger("Sora10Chan.ServerList")
DISCORD_API = "https://discord.com/api/v10"
SERVER_LIST_TOPIC = "sora-server-list"
MESSAGE_LIMIT = 1800


def fetch_bot_guilds(bot_token: str) -> list[dict]:
    headers = {"Authorization": f"Bot {bot_token}"}
    guilds = []
    after = None

    while True:
        params = {"limit": 200, "with_counts": "true"}
        if after is not None:
            params["after"] = after
        response = requests.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers=headers,
            params=params,
            timeout=(5, 15),
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError("Discord returned an invalid guild list")
        if not page:
            return guilds
        if any(not isinstance(guild, dict) or "id" not in guild for guild in page):
            raise ValueError("Discord returned an invalid guild entry")

        guilds.extend(page)
        if len(page) < 200:
            return guilds
        next_after = str(page[-1]["id"])
        if next_after == after:
            raise ValueError("Discord returned a repeated guild page")
        after = next_after


def format_guild_messages(guilds: list[dict]) -> list[str]:
    if not guilds:
        return ["Sora10Chan is not currently in any servers."]

    messages = []
    lines = [f"Sora10Chan is in {len(guilds)} server(s):"]
    for guild in guilds:
        name = str(guild.get("name", "Unknown server"))
        name = name.replace("\r", " ").replace("\n", " ").replace("`", "'")
        member_count = guild.get("approximate_member_count")
        count_text = (
            f" | Approx. members: {member_count}"
            if isinstance(member_count, int)
            else ""
        )
        line = f"• {name} (ID: `{guild['id']}`{count_text})"
        if len("\n".join(lines)) + len(line) + 1 > MESSAGE_LIMIT:
            messages.append("\n".join(lines))
            lines = ["More servers:"]
        lines.append(line)
    if lines:
        messages.append("\n".join(lines))
    return messages


def format_personal_install_messages(user_ids: list[str]) -> list[str]:
    if not user_ids:
        return [
            "No users have been seen using a personal install yet. "
            "Tracking starts when they use a command after setup."
        ]

    messages = []
    lines = [f"Users seen using a personal install ({len(user_ids)}):"]
    for user_id in user_ids:
        line = f"<@{user_id}> (`{user_id}`)"
        if len("\n".join(lines)) + len(line) + 1 > MESSAGE_LIMIT:
            messages.append("\n".join(lines))
            lines = ["More personal-install users:"]
        lines.append(line)
    if lines:
        messages.append("\n".join(lines))
    return messages


def send_followup(application_id: str, interaction_token: str, content: str) -> None:
    response = requests.post(
        f"{DISCORD_API}/webhooks/{application_id}/{interaction_token}",
        json={
            "content": content,
            "flags": 64,
            "allowed_mentions": {"parse": []},
        },
        timeout=(5, 15),
    )
    response.raise_for_status()


@subscribe(topic=SERVER_LIST_TOPIC, max_attempts=1)
async def process_server_list(message: Message[dict[str, str]]) -> None:
    payload = message.payload
    application_id = payload["application_id"]
    interaction_token = payload["interaction_token"]
    bot_token = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")

    if not bot_token:
        await asyncio.to_thread(
            send_followup,
            application_id,
            interaction_token,
            "The server list is unavailable because the bot token is not configured.",
        )
        return

    try:
        guilds = await asyncio.to_thread(fetch_bot_guilds, bot_token)
    except requests.RequestException:
        logger.exception("Could not fetch the bot's server list from Discord")
        await asyncio.to_thread(
            send_followup,
            application_id,
            interaction_token,
            "I couldn't fetch the server list from Discord.",
        )
        return
    except (KeyError, TypeError, ValueError):
        logger.exception("Discord returned an invalid server list")
        await asyncio.to_thread(
            send_followup,
            application_id,
            interaction_token,
            "Discord returned an invalid server list.",
        )
        return

    messages = format_guild_messages(guilds)
    try:
        user_ids = await asyncio.to_thread(list_personal_install_users)
    except DatabaseNotConfiguredError:
        messages.append(
            "Personal-install tracking is not configured. Add DATABASE_URL "
            "to the Vercel Production environment and redeploy."
        )
    except psycopg.Error:
        logger.exception("Could not load personal-install users from the database")
        messages.append("I couldn't load personal-install users; check the Vercel logs.")
    else:
        messages.extend(format_personal_install_messages(user_ids))

    try:
        for content in messages:
            await asyncio.to_thread(
                send_followup,
                application_id,
                interaction_token,
                content,
            )
    except requests.RequestException:
        logger.exception("Could not send the server list to Discord")
