import json
import os
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from api.interactions import SERVER_LIST_TOPIC, app
from queues.servers import fetch_bot_guilds, format_guild_messages


class ServerListFormattingTests(unittest.TestCase):
    def test_formats_all_guilds_and_splits_long_output(self):
        guilds = [
            {
                "id": str(1000 + index),
                "name": f"Server {index} " + ("x" * 80),
                "approximate_member_count": index + 1,
            }
            for index in range(40)
        ]

        messages = format_guild_messages(guilds)
        listed_ids = [
            line.split("`")[1]
            for message in messages
            for line in message.splitlines()
            if " (ID: `" in line
        ]

        self.assertGreater(len(messages), 1)
        self.assertTrue(all(len(message) <= 1800 for message in messages))
        self.assertEqual(listed_ids, [guild["id"] for guild in guilds])

    def test_fetches_all_guild_pages(self):
        first_page = [{"id": str(index)} for index in range(200)]
        second_page = [{"id": "200"}]
        first_response = Mock()
        first_response.json.return_value = first_page
        second_response = Mock()
        second_response.json.return_value = second_page

        with patch(
            "queues.servers.requests.get",
            side_effect=[first_response, second_response],
        ) as get:
            guilds = fetch_bot_guilds("test-token")

        self.assertEqual(len(guilds), 201)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["after"], "199")


class ServerCommandInteractionTests(unittest.TestCase):
    def post_signed_command(self, user_id):
        signing_key = SigningKey.generate()
        timestamp = str(int(time.time()))
        payload = {
            "type": 2,
            "id": "interaction-id",
            "application_id": "application-id",
            "token": "interaction-token",
            "data": {"name": "servers"},
            "member": {"user": {"id": str(user_id)}},
        }
        body = json.dumps(payload).encode()
        signature = signing_key.sign(timestamp.encode() + body).signature.hex()

        with patch.dict(
            os.environ,
            {"DISCORD_PUBLIC_KEY": signing_key.verify_key.encode().hex()},
        ):
            response = TestClient(app).post(
                "/",
                content=body,
                headers={
                    "x-signature-timestamp": timestamp,
                    "x-signature-ed25519": signature,
                },
            )
        return response

    def test_owner_is_acknowledged_privately_and_request_is_queued(self):
        with patch("api.interactions.send", new_callable=AsyncMock) as send:
            response = self.post_signed_command(670920777926705185)

        self.assertEqual(response.json(), {"type": 5, "data": {"flags": 64}})
        send.assert_awaited_once()
        self.assertEqual(send.await_args.args[0], SERVER_LIST_TOPIC)

    def test_non_owner_is_denied_privately_without_queueing(self):
        with patch("api.interactions.send", new_callable=AsyncMock) as send:
            response = self.post_signed_command(123)

        self.assertEqual(response.json()["data"]["flags"], 64)
        self.assertIn("Only the bot owner", response.json()["data"]["content"])
        send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
