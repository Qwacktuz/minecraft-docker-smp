# Discord notifications

With a Discord webhook set, the server posts to a channel:

| When | Message | Sent by |
| --- | --- | --- |
| A start finishes | 🟢 The server is up: `mc.cactuz.dev` (CX33 in hel1) | `bin/server start vps` |
| A stop finishes | 🔴 The server is stopped and the world is backed up | `bin/server stop` |
| A start or stop fails | ⚠️ The server start failed: *the error* ([log](...)) | `bin/server` |
| The idle watchdog stops it | ⏹️ Auto-stop: nobody online for 120 minutes. Backing up, then shutting down the server. | the watchdog Worker |

Starts and stops from the laptop, the GitHub button, the web app and the
watchdog all post, because they all run `bin/server`. A run on GitHub links its
log; one on the laptop says "from the laptop". Mentions are off, so a message
can't ping anyone. A failed post only prints a warning.

A failure is posted once the start or stop has really begun: answering "no" to
a confirmation, or running `stop` with nothing running, posts nothing.

## Setting it up

1. In Discord: the channel's **Edit Channel** → **Integrations** → **Webhooks**
   → **New Webhook** → **Copy Webhook URL**.
2. Add it to the infra secrets as `DISCORD_WEBHOOK_URL` (a plain `KEY=value`
   line). It's a secret: anyone with the URL can post to the channel.

   ```bash
   sops secrets/infra.enc.env
   ```

3. Give the watchdog its copy (for the auto-stop message):

   ```bash
   server watchdog
   ```

`bin/server` reads it from the secrets on every run, on the laptop and on GitHub,
so nothing else needs deploying. Remove the line to turn the posts off; for the
watchdog, also run `wrangler secret delete DISCORD_WEBHOOK_URL` in `watchdog/`.

## Hourly backups

The hourly backups on the VPS already ping healthchecks.io, which alerts when
one is missed or fails. To get those in the same channel, add healthchecks.io's
own Discord integration (healthchecks.io → **Integrations** → **Discord**).
