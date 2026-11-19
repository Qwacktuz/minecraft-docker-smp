# Changelog

## Unreleased — 2026-11-19 (branch `feat/server-lifecycle-devenv`)

### One start/stop command
- `bin/server start local|vps`, `stop`, `status`, `tofu <args>`, run from the laptop.
- There is one world, and it lives in R2 between runs. `stop` takes a backup and
  shuts down only after a snapshot newer than the request is verified. On the
  VPS it then logs out of Tailscale and runs `tofu destroy`, so an idle server
  costs nothing. `start` restores the latest snapshot before any container starts.
- `scripts/deploy.sh`: `RESTORE=latest` (the old world is kept in
  `data/minecraft.previous`), `NEW_WORLD=1` required when R2 has no snapshots,
  and `TS_IP=127.0.0.1` for local runs.
- The world runs in only one place: `start` refuses while it runs elsewhere.
- The Tailscale auth key is ephemeral, so each new VPS gets the `mc-prod` name again.

### CI and tooling
- Removed `.github/workflows/deploy.yml`. Pushing to `main` no longer creates or changes servers.
- `devenv.nix` + `devenv.lock` are the single source of tool versions, on the
  laptop and in CI. CI installs Nix and runs `devenv test`: commit hooks
  (ShellCheck, actionlint, nixfmt, `tofu fmt`) plus `validate` (tests, lint,
  tofu validate, Alloy/Loki config checks).
- `.envrc` now only loads devenv; it no longer exports cloud credentials into every shell.

### Secrets
- Every secret is SOPS/Age-encrypted in `secrets/`:
  - `infra.enc.env` holds the OpenTofu `TF_VAR_*` settings, the state-backend
    keys and the backend bucket/endpoint. These were previously in
    `infra/local.auto.tfvars`, `infra/.env` and `infra/backend.conf`.
  - `app.enc.env` holds the Compose settings (renamed from `secrets.enc.env`).
- Infra secrets are decrypted with `sops exec-env` into each tofu process only.
  GitHub needs no secrets, and the VPS never stores the Age key.

### Housekeeping
- Archived `docs/production-readiness-review.md`, `scripts/backup_and_clean.sh`
  and `.geminiignore` (see `archive/README.md`).
- `.devenv/` is no longer tracked.
