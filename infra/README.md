# Infrastructure

OpenTofu provisions a Hetzner VPS (default `cx33`, `hel1`, Debian 13), firewall,
DNS records, and a Tailscale bootstrap key. Cloud-init installs Docker, SOPS,
Tailscale, UFW, and other host packages.

## Access and bootstrap

- The firewall currently permits TCP 25565/24464 and UDP 25565/24454/25454.
  TCP 24464 is a legacy creative-server allowance; no active Compose service uses it.
- Public SSH is blocked; there is no active CI-runner-IP exception.
- Tailscale manages SSH on the tailnet address (`--ssh`). Your own tailnet identity
  needs an SSH rule allowing it to reach `tag:server` as the deployment user,
  because `bin/server` deploys from your laptop.
- The server receives `tag:server` and its configured hostname (`mc-prod` by default).
- The authentication key is single-use, expires after one hour, and creates an
  ephemeral device. Every `bin/server start vps` creates a fresh key, and
  `bin/server stop` logs the device out before deleting the server, so the next
  VPS gets the `mc-prod` name again. Tailscale removes an ephemeral device that stays
  offline for a while, so a VPS cut off from Tailscale for a long time loses tailnet access.
- Cloud-init advertises an exit node; approve/use that only if intentional.

## Secrets

All secrets are SOPS/Age-encrypted in `secrets/`, and nothing else holds them:

| File | Holds | Read by |
|---|---|---|
| `secrets/infra.enc.env` | `TF_VAR_*` provider settings, `AWS_*` state-backend keys, `TOFU_BACKEND_BUCKET`/`ENDPOINT` | `bin/server`, via `sops exec-env`, only for each tofu process |
| `secrets/app.enc.env` | Compose settings: RCON, Grafana, Arcane, Restic, whitelist | `scripts/deploy.sh`, which writes the private `.env` |

Edit either with `sops secrets/<file>`; to add a secret, add a line there, nothing
else. Plain `NAME=value` dotenv format. GitHub Actions only validates and needs
no secrets. The VPS never stores the Age key: `bin/server` passes it over SSH stdin
for each deploy.

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
