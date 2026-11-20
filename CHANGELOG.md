# Changelog

## Unreleased: fall back to other locations too when Hetzner is sold out (2026-11-20)

- `bin/server start` tries each of `SERVER_TYPES` in every location of
  `SERVER_LOCATIONS` (default `hel1 fsn1 nbg1`) before the next type: `cx33` in
  hel1, fsn1, nbg1, then `cpx32` in the same order. As before, only
  `resource_unavailable` moves on. The VPS holds no state, so any location works;
  players in Finland may see slightly higher latency from Germany.
- `infra/main.tf` also ignores `location` changes, so a running VPS is never
  moved. The start log says which type and location it got.

## Unreleased: anti-xray removed (2026-11-20)

- **Meow Anti-Xray is removed**: it didn't work properly. `REMOVE_OLD_MODS`
  deletes the jar at the next start. `config/meowantixray.yml` is gone from
  Git; the world keeps its copy of the file, which does nothing without the mod.

## Unreleased: fall back to another server type when Hetzner is sold out (2026-11-20)

- Hetzner had no `cx33` left in any location, so `start` failed with
  `resource_unavailable`. `bin/server start` now tries the types in
  `SERVER_TYPES` in order (default `cx33 cpx32`) and moves on only on that
  error; any other OpenTofu error still stops at once.
- `infra/main.tf` ignores `server_type` changes, so a running VPS is never
  resized or replaced because a cheaper type is available again. The next VPS
  gets the cheaper one.

## Unreleased: player names on the web page (2026-11-20)

- The public page lists who's online, with skin heads (mc-heads.net), from the
  server list ping's sample. Players hidden from the server list aren't named.
- `watchdog/src/logic.js` gains `parseStatusDetails` (online, max, names);
  `parseStatus` and the watchdog's behaviour are unchanged.
- `npm run dev` can ping a local copy now (`HOST=localhost` in `web/.dev.vars`,
  which is git-ignored): it uses `node:net` there, since Node has no
  `cloudflare:sockets`.

## Unreleased: a web app (2026-11-20)

- **`web/`: a SvelteKit app on a Cloudflare Worker at smp.cactuz.dev.** The
  public page shows the server's state, players online, the time until the idle
  auto-stop, and the `world.zip` link. `/admin`, behind Cloudflare Access, has
  Start/Stop (the same Server workflow on `main`), the runs with live steps, and
  the backup list. Deploy with `server web`; setup in `docs/web.md`.
- The watchdog's DNS, ping and GitHub code moved to `watchdog/src/minecraft.js`
  so the web app shares it. The watchdog behaves the same.
- `scripts/publish-status.sh` uploads `backups.json` (snapshot IDs, times, tags)
  at every start and stop, when `WEB_BUCKET` is set. `snapshots.py --json` makes it.
- Server workflow runs are titled "Server start" / "Server stop".
- `validate` also type-checks, tests and builds `web/`.

## Unreleased: web map, grief logs, anti-xray, mod configs in Git (2026-11-20)

- **Mod configs in Git** (`config/`): copied over the world's at every start,
  and Git's copy wins (`SYNC_SKIP_NEWER_IN_DESTINATION: false`). Only the files
  in `config/` are managed; every other config stays as the world has it.
- **Web map at https://world.cactuz.dev/map/** (BlueMap). It renders on the
  VPS, and `server stop` publishes it as static files to the public world
  bucket (`scripts/publish-map.sh`), so it stays online while the VPS is off.
  After a restore, `deploy.sh` pulls it back, so only changed chunks are
  rendered again. BlueMap's web server is off and no port is opened. See
  [docs/map.md](docs/map.md).
- **Ledger** grief logs (`/lg`): kept 90 days, in the backups, not in `world.zip`.
- **Meow Anti-Xray**: hides unexposed ores (engine mode 1). DrexHD's AntiXray
  doesn't start alongside Fast Noise (`zfastnoise`).
- **Krypton** (network), and ServerCore's **dynamic distances**: only under load
  (ticks over 35 ms) does simulation distance drop to 6, then view distance to 8.
- Mod list cleanup: Balm removed (nothing used it); the commented
  fabric-permissions-api (bundled by LuckPerms) and Axiom entries removed.
  `pin_mods.py` notes mods that Modrinth marks client-only and nothing requires.
- `scripts/smoke-test.sh` boots the mod list on a fresh, throwaway world and
  fails on mod-loading errors. `lib.sh` gets `r2_rclone`, used by both
  publish scripts and the map pull.

## Unreleased: the idle auto-stop moves to a Cloudflare Worker (2026-11-20)

- GitHub's scheduled workflow ran once in ten hours, so the idle auto-stop
  couldn't be trusted. The **Cloudflare Worker `mc-idle-watchdog`**
  (`watchdog/`) now checks every 5 minutes, with a Cloudflare cron trigger. It
  uses the same rules (2 idle hours, Carpet bots count; 7-day cap) and starts the
  Server workflow with `action=stop`.
- Its only secret is a fine-grained GitHub token that can run workflows in this
  repository. Its state is in Workers KV.
- Deploy it with `server watchdog`. Its logic has Node tests (`node --test`), and
  `validate` also dry-runs the wrangler build.
- The `schedule` trigger and the "Anyone online?" job are gone from
  `.github/workflows/server.yml`.

## Unreleased: pinned pre-prune backups (2026-11-20)

- **Every pre-prune snapshot stays pinned** (`PRUNE_KEEP_SNAPSHOTS=0`) until an
  admin has checked the pruned world in game and runs `server unpin <id>`.
  Before, only the newest 3 kept the tag.

## Unreleased: backup commands, restores, rollback (2026-11-20)

- **Read-only backup commands from the laptop**, no VPS needed (Docker and the
  Age key are enough):
  - `server backups [--vault]` lists the `mc-backup-worker` snapshots with
    their dates and tags.
  - `server check [percent] [--vault]` runs `scripts/test-backup.sh` here,
    without a lock, so it writes nothing and never blocks the VPS's backups.
  - `server drill [id]` restores a read-only local copy from the vault bucket,
    waits for the game's health check, and stops it again.
- **`server restore <id>`** (admins, laptop only; not in the GitHub workflow).
  With the VPS running it asks, takes a verified safety backup tagged
  `pre-restore`, then runs `scripts/restore.sh world <id>` under the deploy
  lock, with the backup container stopped and recreated. With nothing running
  it starts a read-only local copy of `<id>` instead.
- **`server restore <id> --region <overworld|nether|end> <x> <z> [radius]`**
  restores only the region files around a block position (region =
  floor(block / 512); `scripts/regions.py`), with the same safety backup.
- **`server rollback`** restores the newest safety backup. It lives in R2, so
  after the VPS was deleted it starts the VPS from it.
- **Restores only use VPS snapshots, also for explicit IDs.** restic ignores
  `--host` for an explicit snapshot ID, so `restore.sh` and `deploy.sh` now
  resolve IDs against the `mc-backup-worker` list (`snapshots.py --find`) and
  refuse other hosts' snapshots and ambiguous prefixes. `deploy.sh` accepts
  `RESTORE=<snapshot-id>`. `scripts/lib.sh` restic can read the vault
  (`RESTIC_SOURCE=vault`) and works with decrypted credentials instead of
  `.env`.
- **Retention keeps `pre-restore` snapshots** (newest 3 keep the tag).
- **`scripts/pin_mods.py`** pins `MODRINTH_PROJECTS` to Modrinth version IDs,
  run from the laptop. The mods are not pinned yet: this session could not
  reach Modrinth.
- **Renovate:** `dependencyDashboard` uses the object form (Renovate 44 asked
  for the migration).
- Tests: `tests/test_server.py` (new commands), `test_regions.py`,
  `test_pin_mods.py`, plus `test_restore.py`, `test_deploy.py`,
  `test_snapshots.py` for ID resolution and the vault. None of it was run
  against a real server yet.

## Unreleased: start from GitHub, idle auto-stop (2026-11-19)

- **Start and stop from GitHub.** `.github/workflows/server.yml` runs
  `bin/server start vps` or `stop` on a runner ("Run workflow"), for anyone
  with write access. One run at a time. Details: docs/auto-stop.md.
- **Idle auto-stop.** Every 15 minutes `scripts/idle_check.py` reads the
  player count with a server list ping (no secrets). After 2 hours with nobody
  online (Carpet bots count), or 7 days of uptime, the workflow runs
  `bin/server stop`. Tests: `tests/test_idle.py`.
- **A CI-only Age key** is the second recipient in `.sops.yaml`. It lives only
  in the `prod` environment, which only `main` may use, and `main` accepts
  updates from admins only. Tailscale access uses GitHub OIDC, so no Tailscale
  secret is stored.
- **GitHub settings:**
  - Renovate automerges digest and patch updates into `dev` after CI passes.
  - Merged pull-request branches are deleted.
  - Secret scanning with push protection and Dependabot alerts are on.
  - Actions' token is read-only by default.
  - Fork pull requests need approval.
  - `dev` can't be deleted or force-pushed.

## Unreleased: script cleanups (2026-11-19)

No behaviour changes.

- **One way to decrypt.** `bin/server` runs everything that needs secrets
  through one helper, `secrets infra|app|all <hidden command>`, which re-runs
  `bin/server` under `sops exec-env`. It replaces the hand-quoted nested
  `sops exec-env` calls (tofu, tofu init, `_forget-device`, `_vault-copy`,
  `_pause-alerts`).
- **Shared constants once.** `bin/server` sources `scripts/lib.sh`, so
  `WORLD_HOST` (and the pinned images) are defined in one place.
- **Snapshot parsing in Python.** The inline `python3 -c` that orders restic
  snapshots moved to `scripts/snapshots.py`, with unit tests
  (`tests/test_snapshots.py`).
- **One restore script.** `scripts/restore-backup.sh`, `restore-regions.sh` and
  `rollback-backup.sh` are now `scripts/restore.sh world|regions|rollback`, with
  mocked tests (`tests/test_restore.py`).

## Unreleased: backup alerts and Renovate (2026-11-19)

- **Backup alerts.** After every backup, the backup container pings the
  healthchecks.io check in `BACKUP_PING_URL`. The ping carries the exit status
  and the log, so a failure alerts at once. A day without a ping alerts too.
  `server stop` pauses the check through the API (`HEALTHCHECKS_API_KEY`, which
  goes to curl on stdin). Nothing is sent until both are set. The hook was tested
  in the pinned backup image against a local listener.
- **Renovate** (`renovate.json`) opens weekly PRs against `dev` for the pinned
  images (compose.yml and scripts/lib.sh, grouped where they repeat), CI actions,
  devenv and the OpenTofu provider lock. Validated, and a local dry run found
  every dependency.

## Unreleased: hardening (2026-11-19)

- **Least-privilege Cloudflare tokens.** DNS, OpenTofu state, VPS (backups and
  world.zip) and vault each have their own token, and each was tested against
  every bucket. The OpenTofu state moved to its own bucket, with state locking.
- **Vault.** After each VPS stop, the laptop copies the backup repository into
  `cactuz-mc-vault`, whose bucket lock rules refuse deletes for 30 days. The VPS
  has no key for it. Verified: complete copy, restic opens it, delete refused.
- **Integrity check.** `stop` runs `restic check --read-data-subset 2%` before
  deleting the VPS, and aborts if it fails.
- **Pinned versions.** All images are pinned by tag and digest (`compose.yml`,
  `scripts/lib.sh`); so are CI's actions (commit SHAs) and devenv (v2.4.0).
- **Scripts.** All of them share `scripts/lib.sh`, pass secrets by name
  (`-e NAME`), never on the command line, and pass ShellCheck.
- **Cloud-init.** Docker and Tailscale install from their signed apt
  repositories with embedded keys (`infra/keys/`) instead of `curl | sh`, and
  SOPS is checksum-verified for amd64 and arm64.

## Unreleased: public world download (2026-11-19)

- `bin/server stop` on the VPS publishes `world.zip`, without `players/`, to a
  separate public R2 bucket served at `world.cactuz.dev`. It runs after the
  verified final backup, with the game stopped. A failure only warns, and nothing
  is published until `PUBLIC_WORLD_BUCKET` is set.

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
