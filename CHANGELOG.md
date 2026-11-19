# Changelog

## Unreleased: read-only local copies and chunk pruning (2026-11-19)

- Only the VPS writes to R2. The backup service is in the Compose profile
  `backup`, which `deploy.sh` enables only with `BACKUPS=1` (set by `start vps`).
  A local `stop` takes no backup. Restores read R2 with `--no-lock` and only
  consider snapshots from the restic host `mc-backup-worker` (now set explicitly
  with `RESTIC_HOST`).
- New `server prune [--dry-run]`. It backs up, tags the snapshot `pre-prune`,
  stops the game, deletes unused chunks with MCA Selector 2.9 (headless,
  checksummed) and restarts the game. The keep rules are time spent, recent
  saves, player and respawn positions, `prune/protect.txt` and a buffer ring.
  There is a refusal guard, and every dimension is planned before any is changed.
- Optional automatic pruning on `stop` every `AUTO_PRUNE_DAYS` days (off by default).
- `scripts/restore-regions.sh` restores single region files, to undo a prune in
  one area. Retention keeps `pre-prune` snapshots; the newest 3 keep the tag.
- The End's main island (from the original seed) and the void around it are
  protected: pruned chunks would regenerate from the current seed.
- Only chunks MCA Selector read and matched as failing every rule are deleted;
  unreadable chunks are kept.
- Verified on a local copy of the real world: start local restored with no
  backup container; a dry run; a real prune (region files went from 3.1 GB to
  0.45 GB); a healthy restart; stop. R2 was unchanged afterwards (same latest
  snapshot, no locks). On a fresh VPS: the backup service ran, a dry run
  gave the same counts, and stop verified its backup and deleted the VPS. The real
  VPS prune (tagging, stop, prune, restart) is covered by mocked tests only, so it
  doesn't change the real world before you have reviewed it.
- `bin/server` waits up to 2 minutes for restic locks, and shows "unknown"
  instead of a traceback when restic fails.

## Unreleased: fresh-host fixes, ARM64 and verified round trips (2026-11-19)

- Fresh VPS: cloud-init installs Docker before Tailscale. Tailscale SSH sessions
  only get the groups that existed when tailscaled started.
- `start vps` waits for cloud-init in its own session. It restores whenever the
  VPS has no world, and `deploy.sh` refuses to start without a world unless
  `NEW_WORLD=1`.
- ARM64 hosts (Apple Silicon under OrbStack) use Aikar's JVM flags. MeowIce's
  flags crash Temurin 25's C2 compiler there.
- Ported the `asynclogger` mod from the old `main`. CI actions bumped
  (checkout v7, cachix-action v17).
- Deleted the unused GitHub `mc-prod` environment and all of its secrets and
  variables. GitHub now holds no secrets for this repo.
- Verified live: VPS stop → fresh VPS restore, and VPS stop → local
  (OrbStack) restore → local stop. Each stop saved a backup to R2 and verified it.

## Unreleased: simplified to the game and its backups (2026-11-19)

- Removed the monitoring stack (Grafana, Prometheus, Loki, Alloy), Arcane,
  the `bin/smp` local-core experiment, `archive/`, `.env.example` and the
  Loki migration guard. All of them are in Git history.
- Compose runs only `minecraft-service` and `backup`. With no management
  ports left, deploys no longer need the Tailscale IP.
- Infra: the firewall and UFW allow only the game, voice and webcam ports;
  no exit node; fewer host packages; the unused `http` provider is gone.
- `bin/server stop` also deletes the old Tailscale device, so the next VPS
  keeps the `mc-prod` name.
- Rotated the Cloudflare token and the R2 secret derived from it.

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
  and `.geminiignore` (later removed with `archive/`).
- `.devenv/` is no longer tracked.
