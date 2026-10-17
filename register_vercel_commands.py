import os

import requests
from dotenv import load_dotenv


load_dotenv()

application_id = os.getenv("DISCORD_APPLICATION_ID")
bot_token = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
if not bot_token:
    raise SystemExit("Set DISCORD_TOKEN or DISCORD_BOT_TOKEN first.")

headers = {"Authorization": f"Bot {bot_token}"}
if not application_id:
    response = requests.get(
        "https://discord.com/api/v10/users/@me",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    application_id = response.json()["id"]

commands_url = (
    f"https://discord.com/api/v10/applications/{application_id}/commands"
)
command = {
    "name": "server",
    "description": "Show the servers Sora10Chan is in (owner only)",
    "integration_types": [0, 1],
    "contexts": [0, 1, 2],
}

response = requests.get(commands_url, headers=headers, timeout=30)
response.raise_for_status()
existing_commands = response.json()
existing_command = next(
    (
        registered
        for registered in existing_commands
        if registered.get("name") == command["name"]
    ),
    None,
)
if existing_command:
    response = requests.patch(
        f"{commands_url}/{existing_command['id']}",
        headers=headers,
        json=command,
        timeout=30,
    )
    action = "Updated"
else:
    response = requests.post(
        commands_url,
        headers=headers,
        json=command,
        timeout=30,
    )
    action = "Registered"

response.raise_for_status()
print(f"{action} the /server slash command.")