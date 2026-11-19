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

Every 15 minutes the **Anyone online?** job asks `mc.cactuz.dev` for its player
count, the way the in-game server list does (`scripts/idle_check.py`). This job
needs no secrets. It runs `bin/server stop` when:

- **nobody has been online for 2 hours** (`IDLE_MINUTES`), or
- **the VPS has been up for 7 days** (`MAX_DAYS`), even with players online.
  That's a safety cap in case a bot is forgotten.

**Carpet bots count as players.** They are real players to the server and show
up in the player count, so a bot left running overnight keeps the server up.
"Idle" means zero players and zero bots.

Details:
- A game that doesn't answer (still starting, or crashed) counts as idle. A new
  VPS gets 2 hours from the moment the check first sees it.
- If the stop fails, for example because the backup fails, the VPS keeps running,
  as on the laptop. The next check tries again, and each failed run shows in the
  Actions tab.
- The check remembers its state (when the VPS was first seen, when someone was
  last online) in the Actions cache, and keeps only the newest copy.
- Both limits are the `env:` at the top of `server.yml`.
- GitHub pauses scheduled workflows in public repositories after 60 days
  without activity. If that happens, the Actions tab shows a banner. Re-enable
  the workflow there.

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
