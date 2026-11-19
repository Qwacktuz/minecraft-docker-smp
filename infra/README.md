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

## Credentials

`bin/server` runs OpenTofu from your laptop. Provider credentials come from
`infra/local.auto.tfvars` and `infra/.env`; the R2 state backend from
`infra/backend.conf` plus the `AWS_*` keys in `infra/.env`. None of these files
are committed. GitHub Actions only validates and needs no secrets.

Runtime application settings are separately encrypted in `secrets/secrets.enc.env`.
The R2 credentials there need not be the same as the infrastructure-backend credentials.
Use the least privilege each role requires and retain recovery keys independently.

## Local validation and administration

Backend-free validation needs no cloud credentials:

```bash
tofu init -backend=false -lockfile=readonly
tofu fmt -check
tofu validate
```

For actual administration, provide the required `TF_VAR_*` variables from
`variables.tf` and initialize the R2 backend using your private backend configuration.
Keep credential files out of Git. Review `tofu plan` before applying changes.

The deployment workflow still auto-applies infrastructure. `prevent_destroy` is
currently false, world data lives on the VPS disk, and backend locking is not yet
configured. GitHub concurrency reduces overlapping workflow runs; it does not lock
out manual OpenTofu runs. Do not use destroy/apply as a routine migration procedure.

`ignore_changes = [user_data]` means editing cloud-init does not patch an existing
host. Bootstrap currently downloads an AMD64 SOPS binary. Host replacement,
ARM support, and ongoing OS configuration require additional work.

See [backup and restore](../docs/how2backuprestore.md) before any replacement.
