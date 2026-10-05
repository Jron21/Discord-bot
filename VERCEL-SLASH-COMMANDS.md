# Fixing slash commands on Vercel

This project handles Discord interactions through Vercel, not through the
always-on `discord.py` bot in `main.py`. The Vercel HTTP handler is
[`api/interactions.py`](./api/interactions.py). It verifies Discord's request
signature using `DISCORD_PUBLIC_KEY` before responding.

## 1. Check the Discord interactions endpoint

1. Open the Discord Developer Portal and select the bot's application.
2. Under **General Information**, find **Interactions Endpoint URL**.
3. Set it to the deployed Vercel URL:

   ```text
   https://<your-deployment-domain>
   ```

   This project configures `api.interactions:app` as its Vercel entrypoint in
   `pyproject.toml`, and the FastAPI app handles POST `/`. For the current
   deployment, the root URL reaches that handler; `/api/interactions` returns
   404. Do not add `/api/interactions` to this deployment URL.
4. Save the URL. Discord validates it by sending a signed PING request. This
   handler should respond with HTTP 200 and `{"type": 1}`.

If Discord rejects the URL, check that the production deployment is ready and
that you used its deployment domain.

## 2. Configure the public key in Vercel

1. In the Developer Portal, open the application's **General Information**
   page and copy its **Public Key**.
2. In Vercel, open the project and go to **Settings > Environment Variables**.
3. Add this variable for the **Production** environment:

   ```text
   DISCORD_PUBLIC_KEY=<the application's Public Key>
   ```

   Paste the key as shown: do not add quotes or spaces. It is not the bot token
   or the application ID.
4. Redeploy the production deployment so the function receives the new
   environment variable.

The handler returns HTTP 503 with `Interaction endpoint is not configured`
when `DISCORD_PUBLIC_KEY` is unavailable to the deployed function. It returns
HTTP 401 with `Invalid request signature` if verification fails. Check the
Vercel function logs after saving the endpoint or trying `/ping`.

## 3. Test a simple command

After the endpoint saves successfully, use `/ping` in a server where the
application is installed. The handler should reply:

```text
Pong! Sora10Chan is online.
```

`/test` is another simple check. These commands are handled directly by the
Vercel endpoint and do not require the `main.py` bot process to be running.

## 4. Diagnose by symptom

| Symptom or log result | What to check |
| --- | --- |
| Discord will not save the endpoint URL | Confirm the production deployment is ready, use its deployed domain as the endpoint URL, and check Vercel's function logs. |
| HTTP 404 | The domain or route is wrong. This project uses the root URL; do not append `/api/interactions`. |
| HTTP 503, `Interaction endpoint is not configured` | Add `DISCORD_PUBLIC_KEY` to Vercel's Production environment and redeploy. |
| HTTP 401, `Invalid request signature` | Confirm the key is the Public Key for this exact Discord application, with no quotes or whitespace, and that the endpoint targets the intended deployment. |
| HTTP 500 or function initialization error | Read the Vercel function log for the traceback; check deployment dependencies and function configuration. |
| `/ping` works but `/download` or `/media` does not complete | Check the Vercel Queues setup and subscriber logs; see the media section below. |
| Commands are missing from Discord's menu | Check the command-registration section below. |

In Vercel, open the deployment's **Logs** (or **Runtime Logs**) and filter for
the `api/interactions` function. Try `/ping` again while watching the logs. A
request that never reaches this function points to the endpoint URL or
deployment routing; a request that reaches it should have a corresponding
function log if the handler raises an error.

## 5. If only media commands fail

The `/download` and `/media` handlers enqueue work on the `sora-social-media`
topic. The `queues.media` subscriber in `pyproject.toml` processes that work
and sends the result back to Discord. If `/ping` succeeds but media commands
do not:

1. Check that Vercel Queues is enabled and configured for this project.
2. Check the Vercel logs for the `queues.media` subscriber and errors involving
   the `sora-social-media` topic.
3. Confirm that the subscriber was included in the deployed build; it is
   declared in `pyproject.toml` as `queues.media`.
4. Try a supported, publicly accessible media URL and check whether it exceeds
   the configured upload-size limit.

The handler acknowledges queued media work with a deferred interaction only
after enqueueing succeeds. If enqueueing fails, it should return an explicit
error response instead.

## 6. If commands are missing or stale

The project includes `register_vercel_commands.py` to register the four Vercel
slash commands (`ping`, `test`, `download`, and `media`). Run it from a trusted
local environment after setting `DISCORD_APPLICATION_ID` and
`DISCORD_TOKEN` (or `DISCORD_BOT_TOKEN`):

```text
python register_vercel_commands.py
```

The script replaces the application's global command list with those four
commands. Do not run it just to fix an endpoint response when the commands
already appear. The `bot.tree.sync()` call in `main.py` belongs to the
always-on bot deployment and is separate from this Vercel registration flow.
