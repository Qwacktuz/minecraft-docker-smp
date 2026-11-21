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
pull, and from `start_interval`. The map pull was then the longest phase:
20,854 small files pulled one by one.

### The map as one archive

`publish-map.sh` now also uploads the same files as one `map-state.tar` (not
compressed again: the tiles are .gz already). `deploy.sh` downloads and
unpacks it, and falls back to the file-by-file pull when there is none or it
doesn't unpack. If a stop can't replace the archive, it deletes the old one,
so a start never unpacks an older map than `map/`.

Timed from the laptop with the same 1.7 GiB map, uploaded under `perf-test/`
in the public bucket and deleted afterwards:

| | File by file | Archive |
|---|---|---|
| Start: pull | 99 s | **36 s** (download 32 s with 8 streams, unpack 4 s) |
| Stop: extra work | | tar 7 s, upload 54 s (the laptop's uplink) |

The stop's extra minute runs side by side with the integrity check, so it
mostly hides behind it. On a VPS, both directions should be faster.

From the game's log in the same run: the container's init (Modrinth
resolution of the 154 pinned mods, file checks) takes about 22 s; Fabric,
mod loading and the world load about 6 s ("Done (0.442s)"); BlueMap loads
after that.

A laptop is not a VPS: different disk, network and CPU. The VPS numbers need
staging runs.

## The pre-built image

`bin/server image` builds an `mc-base` Hetzner snapshot on a temporary
staging VPS: the normal cloud-init install, every pinned image pulled
(compose.yml and lib.sh's), then cloud-init, the machine ID, the SSH host
keys and Tailscale's state wiped, a power-off, the snapshot (labels
`mc-base=1`, `built=<date>`), and the VPS deleted. Older mc-base snapshots
are deleted, so one is kept (about €0.01 per GB per month).

A new VPS uses the newest one if it is younger than 14 days
(`BASE_MAX_DAYS`); cloud-init then skips the apt upgrade, the installs and
SOPS, but still writes the user, SSH hardening, Tailscale and ufw. Otherwise,
or with `MC_BASE_IMAGE=none`, it starts from `debian-13` as before.
`image` is in `ignore_changes`, so a newer snapshot never replaces a running
VPS.

Rebuild it weekly, and after a Renovate image bump (the old images on it are
only a cache: compose pulls the pinned ones anyway). Running it from CI is a
follow-up.

Untested on Hetzner (see below). `tofu test` checks both cloud-inits.

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
| 00:10, 00:16 | 2 × `start staging`: tofu apply failed before any server was created | cx33 | 0.0144 | 0 | 0.00 |
| | **Total** | | | | **0.00** |

## Why staging never ran: the laptop's firewall

Both `start staging` tries failed in `tofu apply` with
`dial tcp 213.239.246.78:443: i/o timeout` (Hetzner) and the same for
Tailscale's API. `curl` to the same address worked at the same time, and
OpenTofu itself reached R2 (the state). The difference: the providers are
separate programs, and this worktree downloaded its own copies into
`/Users/kaktus/dev/mc-perf/infra/.terraform/providers/`. **LuLu** runs on the laptop, and it
blocks new programs until someone allows them. That is very likely the cause.
Nothing was created at Hetzner (checked with the API).

To unblock: allow the hcloud, tailscale and cloudflare providers under that
path in LuLu (or run staging from a checkout whose providers are already
allowed), then `bin/server start staging`. Changing firewall rules is the
user's call, so it was left alone.

## State of every item

| Item | State | Note |
|---|---|---|
| Phase timings | passed (laptop) | unit tests, real `start local` |
| Staging target | untested on Hetzner | blocked by the firewall; unit tests and `tofu test` pass |
| Baseline, 3 staging cycles | untested | same |
| Tailscale every 2 s | untested on a VPS | unit tests |
| Health check `start_interval` | passed (laptop) | |
| `fix_owner` | passed | a real Docker volume, real `start local` |
| Restore and map pull side by side | passed (laptop) | 196 s → 136 s |
| Map archive | passed (laptop round trip) | 99 s → 36 s; deploy.sh's path is unit-tested only |
| Pre-built image | untested | code, unit tests and `tofu test` only |
| Faster stop | untested on a VPS | unit tests |
| Server type benchmark | skipped | needs staging; and the budget was €0.50 |
| Vault copy | read-only finding | streams through the laptop; no change |
| Modrinth and Fabric start | measured (laptop) | init about 22 s, Fabric and world about 6 s |
| `tofu plan` on the real VPS shows no changes | untested | `tofu test` with mocked providers only |

Also seen: **the real VPS was running** around 00:00 UTC on 2026-11-21
(`start local` said "The VPS keeps running"). Nothing here touched it.
