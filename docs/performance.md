# Start and stop performance

Where the time goes in `server start vps` and `server stop`, what was changed
to make them faster, and how each change was checked. Branch
`claude/affectionate-ritchie-ijvg7f` (2026-11-21).

## Measuring

Every start and stop now prints one line per phase:

```
--- tofu-apply 41s
--- restic-restore 63s
```

Set `PHASE_LOG=<file>` to also append `<phase> <seconds>` to a file. In GitHub
Actions the phases go into the run's step summary as a table. On the VPS,
`scripts/deploy.sh` prints its own phases; `bin/server` collects them from the
SSH output.

| Start phase | What runs |
|---|---|
| tofu-apply | OpenTofu creates the VPS, firewall, key and DNS |
| tailnet | waiting until the VPS answers over Tailscale SSH (checked every 2 s) |
| cloud-init | `cloud-init status --wait`: apt upgrade, Docker, Tailscale, SOPS, ufw |
| deploy | everything below, as one phase seen from the laptop |
| clone | `git clone` and checkout of the commit |
| decrypt | SOPS decrypts `secrets/app.enc.env` |
| image-pull | `docker compose pull` |
| restic-restore | the world from R2 (side by side with map-pull) |
| map-pull | BlueMap's tiles and render state from the public bucket |
| chown | giving files to uid 1000 |
| compose-up | `docker compose up --wait`: Fabric, mods, world load, health check |
| publish-status | backups.json and vps.json for the web app |

| Stop phase | What runs |
|---|---|
| backup | final `backup now`, checked in R2 |
| down | `docker compose down` |
| check, world-zip, publish-status, map | side by side (see below) |
| destroy | Tailscale logout and `tofu destroy` |

## Staging

`bin/server start staging` creates a second VPS, `mc-staging`, and restores
the newest backup on it; `bin/server stop staging` deletes it. It exists to
measure changes without touching the real world:

- its own OpenTofu state (`staging/terraform.tfstate`). bin/server always
  passes the state key to `tofu init`, and refuses to run OpenTofu when
  `infra/.terraform/` was initialised with the other mode's state.
  `STAGING=1 bin/server tofu …` runs OpenTofu by hand against staging.
- no DNS records (`count = 0`), its own firewall (`mc-staging-firewall`) and
  its own Hetzner SSH key (Hetzner refuses a duplicate of the real VPS's key;
  bin/server makes one in `~/.cache/mc-staging/`).
- every Hetzner resource is labelled `purpose=perf-staging`.
- read-only toward R2: `BACKUPS=''`, so no backup container, and the restore
  uses `restic --no-lock`, like `start local`.
- no world.zip, map, backups.json, vault copy, alert pause, tailnet forget or
  Discord post; no question about commits that aren't on main. The commit
  must still be pushed (the VPS clones it from GitHub).

`infra/tests/staging.tftest.hcl` (`tofu test`, in `validate`) plans both
modes with mocked providers: the real VPS keeps its DNS records, firewall
name, key and no labels; staging gets no DNS and carries the label. The DNS
records gained a `count`; `moved {}` blocks keep the real VPS's records in its
state.

## Changes

| Change | Where | Checked |
|---|---|---|
| Phase timings | bin/server, scripts/lib.sh, deploy.sh | unit tests; real local start |
| Staging target | bin/server, infra/ | unit tests, `tofu test`; **not run on Hetzner** |
| Tailscale checked every 2 s instead of 10 s (same 10-minute limit) | bin/server | unit tests; **not on a real VPS** |
| Health check `start_interval: 5s` while starting (start_period and retries unchanged) | compose.yml | compose test; real local start |
| `fix_owner` changes only files not owned by 1000:1000 | scripts/lib.sh | a real Docker volume; real local start |
| restic restore and map pull side by side | deploy.sh | unit tests; real local start |
| Stop: check and publishing side by side after `down` | bin/server | unit tests; **not on a real VPS** |

### Faster stop

Before: backup → 2% check → down → world.zip → backups.json → map → destroy,
one after another. Now: backup → down → (check ‖ world.zip ‖ backups.json ‖
map) → destroy. The check runs through `scripts/lib.sh`'s restic, because the
backup container is gone after `down`. The VPS is deleted only if the check
passed; a failed publish still only warns.

One behaviour changes: when the check fails, the game is already stopped.
The VPS and its disk are kept, as before; `bin/server start vps` starts the
game again without a restore.

## Numbers so far (laptop only, 2026-11-21)

No Hetzner server was created yet (see "Not done yet"). These are two
`server start local` runs on the laptop (OrbStack, Apple Silicon) from the
same snapshot (7623a439: 2974 files, 1.99 GiB) and the published map. Images
were already pulled. Read-only, like every local copy.

| | Base (20b43ca) | This branch |
|---|---|---|
| Whole `start local` | 196 s | **136 s** |
| restic-restore | 25 s (restic's own count) | 30 s, side by side with the map |
| map-pull | not timed | 99 s |
| chown | not timed | 1 s |
| compose-up (to healthy) | not timed | 30 s |

The 60 s saved come mostly from the restore no longer waiting for the map
pull, and from `start_interval`. The map pull is now the longest phase: tens
of thousands of small tile files pulled one by one. That is why the map
archive (one `map-state.tar.zst`) is the next thing to try.

From the game's log in the same run: the container's init (Modrinth
resolution of the 154 pinned mods, file checks) takes about 22 s; Fabric,
mod loading and the world load about 6 s ("Done (0.442s)"); BlueMap loads
after that.

A laptop is not a VPS: different disk, network and CPU. The VPS numbers need
staging runs.

## Read-only findings

- **The vault copy streams through the laptop.** `vault_copy` runs
  `rclone copy backups:… vault:…` between two remotes with different keys.
  rclone can only copy server side within one remote (one set of
  credentials), so every new file is downloaded to the laptop (or the GitHub
  runner) and uploaded again. It's incremental (`--ignore-existing`), so a
  normal stop moves only that day's new packs. Copying inside R2 would need
  one key with access to both buckets, which the separate vault key exists
  to avoid. No change suggested.

## Cost ledger

| Time (UTC) | Action | Type | €/h | Hours billed | € |
|---|---|---|---|---|---|
| | nothing created | | | | 0.00 |

## Not done yet

Each needs the user's go-ahead, because it spends money on Hetzner or
publishes the branch. The handover message from the other session said the
user approved this, but that approval wasn't given in this session, so these
waited.

| Item | State | Why |
|---|---|---|
| Push the branch, draft PR | skipped | needs the user's OK in this session |
| Staging baseline (3 cycles on cx33) | untested | needs a pushed branch and Hetzner spending |
| Quick wins on a real VPS | untested | same |
| Faster stop on a real VPS | untested | same; needs a staging variant with a local restic repo |
| Pre-built Hetzner snapshot (`bin/server image`) | not built | biggest expected gain (cloud-init's apt upgrade and installs, the image pulls); only worth building with staging runs to prove it and the fallback |
| Map as one archive | not built | the map pull (99 s) makes it worth it, but a test needs a write under `perf-test/` in the public bucket |
| Server type benchmark (spark) | untested | needs staging servers |
| `tofu plan` on the real VPS shows no changes | untested | `tofu test` with mocked providers checks the plan's shape; a real plan was not run |

Also seen: **the real VPS was running** at 2026-11-21 ~00:00 local time
(`start local` said "The VPS keeps running"). Nothing here touched it.

Only `start staging` itself, labels, DNS-less records and the staging key are
new Hetzner-side behaviour; until a staging run passes, treat the staging
code as untested.
