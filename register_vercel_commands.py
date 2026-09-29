import os

import requests
from dotenv import load_dotenv


load_dotenv()

application_id = os.getenv("DISCORD_APPLICATION_ID")
bot_token = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
if not application_id or not bot_token:
    raise SystemExit("Set DISCORD_APPLICATION_ID and DISCORD_TOKEN first.")

commands = [
    {"name": "ping", "description": "Check whether Sora10Chan is responding"},
    {"name": "test", "description": "Run a quick Sora10Chan test"},
    {
        "name": "download",
        "description": "Download media from Facebook, TikTok, Instagram, or X",
        "options": [{
            "type": 3,
            "name": "url",
            "description": "Social media URL",
            "required": True,
        }],
    },
    {
        "name": "media",
        "description": "Extract an image, video, or carousel from a social link",
        "options": [{
            "type": 3,
            "name": "url",
            "description": "Social media URL",
            "required": True,
        }],
    },
]

for command in commands:
    command["integration_types"] = [0, 1]
    command["contexts"] = [0, 1, 2]

response = requests.put(
    f"https://discord.com/api/v10/applications/{application_id}/commands",
    headers={"Authorization": f"Bot {bot_token}"},
    json=commands,
    timeout=30,
)
response.raise_for_status()
print(f"Registered {len(commands)} Vercel slash commands.")