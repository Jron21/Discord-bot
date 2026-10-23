import asyncio
import logging

import psycopg
from vercel.queue import Message, subscribe

from install_tracking import (
    DatabaseNotConfiguredError,
    record_personal_install_user,
)


logger = logging.getLogger("Sora10Chan.UserInstallTracking")


@subscribe(topic="sora-user-install", max_attempts=3)
async def process_user_install(message: Message[dict[str, str]]) -> None:
    user_id = message.payload.get("user_id")
    if user_id is None:
        logger.error("Personal-install tracking message has no user ID")
        return

    try:
        await asyncio.to_thread(record_personal_install_user, user_id)
    except DatabaseNotConfiguredError:
        logger.error(
            "Could not record personal-install user: DATABASE_URL is not configured"
        )
    except ValueError:
        logger.exception("Could not record invalid personal-install user ID")
    except psycopg.Error:
        logger.exception("Could not persist personal-install user")
        raise
