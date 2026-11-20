# Infrastructure

OpenTofu provisions a Hetzner VPS (Debian 13; a `cx33` in `hel1`, or when
Hetzner has none, the next free pair of `SERVER_TYPES` and `SERVER_LOCATIONS`
in `bin/server`: `cx33` in `fsn1`, `nbg1`, then `cpx32`), firewall,
DNS records, and a Tailscale bootstrap key. Cloud-init installs Docker, SOPS,
Tailscale, UFW, and other host packages.

## Access and bootstrap

- The Hetzner firewall and UFW allow only the game (25565/tcp), voice chat
  (24454/udp) and the webcam mod (25454/udp). Public SSH is blocked.
- Tailscale manages SSH on the tailnet address (`--ssh`). Your own tailnet identity
  needs an SSH rule allowing it to reach `tag:server` as the deployment user,
  because `bin/server` deploys from your laptop.
- The server receives `tag:server` and its configured hostname (`mc-prod` by default).
- The authentication key is single-use, expires after one hour, and creates an
  ephemeral device. Every `bin/server start vps` creates a fresh key. After
  deleting the server, `bin/server stop` removes the device through the Tailscale
  API, using the OAuth client from `infra.enc.env`, so the next VPS gets the
  `mc-prod` name again. Tailscale removes an ephemeral device that stays offline
  for a while, so a VPS cut off from Tailscale for a long time loses tailnet access.

## Secrets

All secrets are SOPS/Age-encrypted in `secrets/`, and nothing else holds them:

| File | Holds | Read by |
|---|---|---|
| `secrets/infra.enc.env` | `TF_VAR_*` provider settings, `AWS_*` state-bucket keys, `TOFU_BACKEND_BUCKET`/`ENDPOINT`, `VAULT_*` vault keys, `HEALTHCHECKS_API_KEY` (pauses the alert check), `WATCHDOG_CLOUDFLARE_TOKEN` (deploys both Workers), `WATCHDOG_GITHUB_TOKEN` and `WEB_GITHUB_TOKEN` (the Workers' GitHub tokens) | the laptop and the GitHub `Server` workflow: `bin/server`, via `sops exec-env`, per command |
| `secrets/app.enc.env` | Compose settings: RCON, whitelist/ops, Restic and its R2 keys, `PUBLIC_WORLD_BUCKET` (the world download and map), `WEB_BUCKET` (the web app's backup list), `BACKUP_PING_URL` (backup alerts) | `scripts/deploy.sh` on the VPS (or a local copy), which writes the private `.env` |

Edit either with `sops secrets/<file>`, in plain `NAME=value` dotenv format, with
no spaces around `=`. To add a secret, add a line there, nothing else. The
validate workflow needs no secrets; the Server workflow decrypts them with a
CI-only Age key ([docs/auto-stop.md](../docs/auto-stop.md)). The VPS never stores the Age key:
`bin/server` passes it over SSH stdin for each deploy.

### Cloudflare tokens and buckets

Each token reaches only what it needs. The VPS can never touch the state or the
vault.

| Token | Can access | Stored as |
|---|---|---|
| DNS (account API token) | Zone Read + DNS Edit on cactuz.dev | `TF_VAR_cloudflare_api_token` (infra) |
| R2 state | `cactuz-mc-tofu-state` | `AWS_*` (infra) |
| R2 VPS | `cactuz-mc-backups`, `cactuz-mc-world`, `mc-smp-web` | `R2_*` (app) |
| Workers deploy | Workers Scripts, KV, R2 and Routes (see [docs/auto-stop.md](../docs/auto-stop.md), [docs/web.md](../docs/web.md)) | `WATCHDOG_CLOUDFLARE_TOKEN` (infra) |
| R2 vault | `cactuz-mc-vault` | `VAULT_*` (infra) |

- **`cactuz-mc-backups`**: the Restic repository.
- **`cactuz-mc-world`**: public, at `world.cactuz.dev`: `world.zip` and `map/`.
- **`mc-smp-web`**: private, read by the web app: `backups.json`.
- **`cactuz-mc-tofu-state`**: the OpenTofu state, locked during runs (`use_lockfile`).
- **`cactuz-mc-vault`**: a copy of the backups. R2 bucket lock rules keep
  `data/`, `index/`, `keys/` and `snapshots/` for 30 days, so not even a stolen VPS
  key can delete them.

The R2 tokens are object read & write and expire after a year; renew them before
then. A renewed R2 token comes with a new key ID and secret, which go into the
same variables.

## Local validation and administration

Backend-free validation needs no cloud credentials:

```bash
tofu init -backend=false -lockfile=readonly
tofu fmt -check
tofu validate
```

Run OpenTofu by hand with the encrypted credentials through `bin/server tofu`
(it initializes the R2 backend first), e.g. `bin/server tofu plan`. Review a plan
before applying changes outside `bin/server start`/`stop`.

`prevent_destroy` is false because `bin/server stop` deletes the VPS on purpose,
after a verified backup. The state is locked while OpenTofu runs
(`use_lockfile` in `backend.tf`), so a manual command waits for, or fails
against, a running `bin/server`.

`ignore_changes = [user_data]` means editing cloud-init does not patch a running
host; the change applies to the next VPS (every `start vps` makes a new one).
Cloud-init installs the SOPS binary for amd64 or arm64.

See [backup and restore](../docs/backup.md) before any replacement.
