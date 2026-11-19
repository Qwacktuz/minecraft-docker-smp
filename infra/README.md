# Infrastructure

OpenTofu provisions a Hetzner VPS (default `cx33`, `hel1`, Debian 13), firewall,
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
| `secrets/infra.enc.env` | `TF_VAR_*` provider settings, `AWS_*` state-bucket keys, `TOFU_BACKEND_BUCKET`/`ENDPOINT`, `VAULT_*` vault keys | the laptop only: `bin/server`, via `sops exec-env`, per command |
| `secrets/app.enc.env` | Compose settings: RCON, whitelist/ops, Restic and its R2 keys, `PUBLIC_WORLD_BUCKET` (the world download) | `scripts/deploy.sh` on the VPS (or a local copy), which writes the private `.env` |

Edit either with `sops secrets/<file>`, in plain `NAME=value` dotenv format, with
no spaces around `=`. To add a secret, add a line there, nothing else. GitHub
Actions only validates and needs no secrets. The VPS never stores the Age key:
`bin/server` passes it over SSH stdin for each deploy.

### Cloudflare tokens and buckets

Each token reaches only what it needs. The VPS can never touch the state or the
vault.

| Token | Can access | Stored as |
|---|---|---|
| DNS (account API token) | Zone Read + DNS Edit on cactuz.dev | `TF_VAR_cloudflare_api_token` (infra) |
| R2 state | `cactuz-mc-tofu-state` | `AWS_*` (infra) |
| R2 VPS | `cactuz-mc-backups`, `cactuz-mc-world` | `R2_*` (app) |
| R2 vault | `cactuz-mc-vault` | `VAULT_*` (infra) |

- **`cactuz-mc-backups`**: the Restic repository.
- **`cactuz-mc-world`**: public, at `world.cactuz.dev`.
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
after a verified backup. Backend locking is not yet configured, so don't run
manual OpenTofu commands while `bin/server` is running.

`ignore_changes = [user_data]` means editing cloud-init does not patch an existing
host. Bootstrap currently downloads an AMD64 SOPS binary. ARM support and ongoing
OS configuration require additional work.

See [backup and restore](../docs/how2backuprestore.md) before any replacement.
