# Starting from GitHub, and the idle auto-stop

`.github/workflows/server.yml` runs `bin/server` on a GitHub runner, so the
server can be started and stopped without the laptop. The same file holds the
idle auto-stop.

## Start or stop (anyone with write access)

1. Go to **Actions** → **Server** → **Run workflow**.
2. Pick branch `main` and choose `start` or `stop`.
3. A start takes about 10 minutes. Then connect to `mc.cactuz.dev`.

It does exactly what `server start vps` and `server stop` do on the laptop: the
same restore, the same verified final backup, and the same vault copy. Only one
start or stop runs at a time; a second one waits in the queue.

`server stop` on the laptop still works at any time. Don't run it while a GitHub
start or stop is still running; check the Actions tab first.

To let a friend start the server, add them under **Settings** → **Collaborators**
with the **Write** role.

## Idle auto-stop

A Cloudflare Worker (`watchdog/`, named `mc-idle-watchdog`) runs every 5 minutes
on a Cloudflare cron trigger. It looks up `mc.cactuz.dev` and asks the game for
its player count, the way the in-game server list does. When one of these holds,
it starts the **Server** workflow with `action=stop`, the same as pressing the
button:

- **nobody has been online for 2 hours** (`IDLE_MINUTES`), or
- **the VPS has been up for 14 days** (`MAX_DAYS`), even with players online.
  That's a safety cap in case a bot is forgotten.

The stop backs up, verifies the backup and deletes the VPS (`bin/server stop`).

**Carpet bots count as players.** They are real players to the server and show
up in the player count, so a bot left running overnight keeps the server up.
"Idle" means zero players and zero bots.

Details:
- A game that doesn't answer (still starting, or crashed) counts as idle. A new
  VPS (new IP address) gets 2 hours from the moment the Worker first sees it.
- The Worker requests a stop at most every 30 minutes, and never while a Server
  run is queued or running. If a stop fails (for example the backup fails), the
  VPS keeps running, as on the laptop; the Worker tries again 30 minutes later,
  and each failed run shows in the Actions tab.
- It keeps its state (when the VPS was first seen, when someone was last
  online, the last stop request) in a Workers KV namespace.
- See what it last decided: open its `workers.dev` URL (printed by
  `server watchdog`), or the Worker's logs in the Cloudflare dashboard.
- The limits are `[vars]` in `watchdog/wrangler.toml`. Change them, then run
  `server watchdog` to redeploy.
- Free plan: cron triggers, outbound TCP and KV are all included. It writes to KV
  only when something changes.

GitHub's own scheduled workflows did this job at first, but GitHub skipped most of
the runs (one run in ten hours), so they aren't used any more.

### Setting up the Worker (once)

1. **A Cloudflare API token** for deploying it. Go to Cloudflare dashboard → My
   Profile → API Tokens → Create Token → Custom token, with these permissions:
   - Account → **Workers Scripts** → Edit
   - Account → **Workers KV Storage** → Edit
2. **A GitHub token** for the Worker. Go to GitHub → Settings → Developer settings
   → Fine-grained tokens → Generate new token:
   - Repository access: **Only select repositories** → `minecraft-docker-smp`.
   - Permissions: **Actions** → **Read and write**. Metadata (read) is added
     automatically.
   - Expiration: up to a year. Note the date.

   It can only start, cancel and read workflow runs in this repository.
3. Add both to the infra secrets as `WATCHDOG_CLOUDFLARE_TOKEN` and
   `WATCHDOG_GITHUB_TOKEN` (plain `KEY=value` lines):

   ```bash
   sops secrets/infra.enc.env
   ```

4. Deploy:

   ```bash
   server watchdog
   ```

   The first time, it creates the KV namespace and writes its ID into
   `watchdog/wrangler.toml`; commit that. The GitHub token goes to the Worker as
   its only secret, passed to wrangler on stdin.

When the GitHub token expires, make a new one, replace it in `infra.enc.env`, and
run `server watchdog` again.

## How the runner gets its access

| What | How | Where it's set |
| --- | --- | --- |
| Secrets (`secrets/*.enc.env`) | A CI-only Age key. It is the second recipient in `.sops.yaml`. | Secret `SOPS_AGE_KEY` in the `prod` environment |
| Tailscale (SSH to the VPS) | GitHub's OIDC token, exchanged for an ephemeral `tag:ci` device. No Tailscale secret is stored. | Variables `TS_CLIENT_ID` and `TS_AUDIENCE` in `prod`, plus a Tailscale trust credential for subject `repo:Qwacktuz/minecraft-docker-smp:environment:prod` |

What protects the key:
- **Only `main` can use `prod`.** That's the environment's deployment branch rule.
- **Only admins can update `main`.** That's the ruleset "protect main".
  Collaborators can push to `dev` and other branches, but those never see the key.
- **Fork pull requests get no secrets.**
- **The Tailscale policy** lets `tag:ci` reach only `tag:server` on port 22, as
  `deployer`.

If the key ever leaks:
1. Remove its line from `.sops.yaml`.
2. Run `sops updatekeys -y secrets/*.enc.env`.
3. Rotate the tokens in the secret files.
4. Delete the `SOPS_AGE_KEY` secret.

Even then the vault is safe: its bucket lock refuses deletes for 30 days.
