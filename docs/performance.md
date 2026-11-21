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
| Staging target | bin/server, infra/ | unit tests, `tofu test`, 5 staging runs |
| Tailscale checked every 2 s instead of 10 s (same 10-minute limit) | bin/server | unit tests; staging |
| Health check `start_interval: 5s` while starting (start_period and retries unchanged) | compose.yml | compose test; real local start |
| `fix_owner` changes only files not owned by 1000:1000 | scripts/lib.sh | a real Docker volume; real local start |
| restic restore and map pull side by side | deploy.sh | unit tests; real local start |
| Stop: check and publishing side by side after `down` | bin/server | unit tests; **not on a real VPS** (a staging stop doesn't back up) |

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

**Rebuilding is automatic**: `.github/workflows/image.yml` runs
`bin/server image --if-played` every Monday. It looks at the newest VPS
backup (the VPS backs up every hour and at each stop):

| Last play | Image | What happens | Cost |
|---|---|---|---|
| in the last 7 days | missing, or 6+ days old | rebuild | one cx33 hour, ~€0.015 |
| in the last 7 days | newer | keep | €0 |
| 7–29 days ago | any | nothing | storage only, ~€0.03 a month |
| 30+ days ago | exists | delete it | €0 from then on |

So a quiet month costs nothing, and a playing week gets a fresh image (with
that week's Debian updates and pinned images). "Run workflow" with *force*
builds one now, for example before a busy weekend; so does `bin/server image`
from the laptop. After a Renovate image bump nothing needs doing: compose
pulls the new image anyway, just a few seconds slower until the next build.

Built and tested on 2026-11-21 (see "The pre-built image on Hetzner" below).
`tofu test` checks both cloud-inits.

## Read-only findings

- **The vault copy streams through the laptop.** `vault_copy` runs
  `rclone copy backups:… vault:…` between two remotes with different keys.
  rclone can only copy server side within one remote (one set of
  credentials), so every new file is downloaded to the laptop (or the GitHub
  runner) and uploaded again. It's incremental (`--ignore-existing`), so a
  normal stop moves only that day's new packs. Copying inside R2 would need
  one key with access to both buckets, which the separate vault key exists
  to avoid. No change suggested.

## Staging runs on Hetzner (2026-11-21, cx33 in hel1)

Five `start staging` runs of this branch, four with timings (cycles 2–5;
the first was started by hand and its output was lost). Each restored the
newest backup (2974 files, 1.99 GiB) and the 1.7 GiB map file by file (there
is no published archive yet: only a real stop publishes one).

| Phase (seconds) | c2 | c3 | c4 | c5 | Median |
|---|---|---|---|---|---|
| tofu-apply | 19 | 15 | 19 | 14 | 17 |
| tailnet (includes cloud-init's installs) | 78 | 155 | 78 | 156 | 117 |
| cloud-init (left to wait for) | 1 | 1 | 2 | 0 | 1 |
| deploy, in all | 128 | 119 | 117 | 118 | 118 |
| · clone | 1 | 1 | 2 | 1 | 1 |
| · image-pull | 9 | 10 | 8 | 9 | 9 |
| · restic-restore | 11 | 10 | 11 | 11 | 11 |
| · map-pull (side by side with the restore) | 52 | 51 | 51 | 52 | 51.5 |
| · chown | 1 | 0 | 1 | 0 | 0.5 |
| · compose-up (to healthy) | 56 | 47 | 46 | 47 | 47 |
| **Whole start** | 228 | 293 | 218 | 292 | **260** |
| Staging stop (down, destroy) | 23 | 23 | 40 | 20 | 23 |

What this says:

- **The biggest cost is cloud-init**: the "tailnet" phase is the wait until
  the VPS answers over Tailscale, and cloud-init only joins the tailnet after
  the apt upgrade and the Docker, Tailscale and SOPS installs. It is either
  about 78 s or about 155 s (Debian's mirror on the day). The pre-built image
  removes most of it.
- **Then the map**: 51 s file by file, while the world restore takes 11 s
  next to it. Measured on the same VPS (cycle 5), the map as one archive took
  **17 s** (download 13 s, unpack 4 s). Building and uploading it at a stop
  took 45 s (tar 12 s, upload 33 s), side by side with the integrity check.
  So once a real stop has published the archive, a start should be about
  35 s faster.
- The game itself (compose-up) takes 47 s, of which the container's init
  (Modrinth checks of 154 mods) is most; Fabric and the world load take a
  few seconds ("Done (1.000s)").
- On the base commit the restore and the map pull ran one after the other,
  so the same start would take about 11 s longer (the restore's time), plus
  up to 20 s waiting for the next health check, and the tailnet wait polled
  every 10 s instead of 2 s. No base-commit run on Hetzner was made: the old
  code has no staging target.

## The pre-built image on Hetzner (2026-11-21)

`bin/server image` built snapshot 459190063 in 289 s, then 459192202 in 187 s
(the second build deleted the first one, so one is kept). Size: **2.17 GB**,
about €0.03 a month in storage. A weekly rebuild adds about €0.065 a month
(one cx33 hour each), so about €0.10 a month in all.

| Phase (seconds) | debian-13 (median of 4) | Pre-built image (c8) |
|---|---|---|
| tofu-apply | 17 | 22 (creating from a snapshot is a little slower) |
| tailnet | 117 (78 or 155) | **29** |
| cloud-init | 1 | 7 |
| **Before the deploy** | **135** | **58** |
| image-pull | 9 | 2 |
| deploy, in all | 118 | 129 (compose-up 68, the game's own start) |
| **Whole start** | 260 | **191** |

Two problems found on the first try, both fixed:

- cloud-init ended "degraded" (exit 2) for "Skipping creation of existing
  group 'docker'", and the start treated that as a failure. Now a baked
  cloud-init skips the group, and exit 2 only warns.
- The image had `tailscaled` disabled, so a reboot would have left the
  tailnet. The image now only stops it, and cloud-init enables it.

Also found: the VPS joined the tailnet at 15:23:24, but the laptop's first
SSH by name got through at 15:24:15. `tailnet_wait` now asks the local
Tailscale for the VPS's address and connects to that (with the name as a
fallback). c8 was the first run with that change, so its 29 s include it.

The fallback (`MC_BASE_IMAGE=none`, cycle 12) started from debian-13 and got
as far as the deploy (image pull 11 s, no cache), but the laptop went to
sleep during cycles 9–12, so their times are not usable. Keep-awake only
stops idle sleep; a closed lid still sleeps.

## Cost ledger

| Time (UTC) | Action | Type | €/h (incl. IPv4) | Hours billed | € |
|---|---|---|---|---|---|
| 00:10, 00:16 | 2 × `start staging`: tofu apply failed (the firewall), nothing created | | | 0 | 0.00 |
| 10:48 | c1, started by hand, stopped 10:52 | cx33 | 0.0152 | 1 | 0.015 |
| 10:53 | c2, stopped 10:57 | cx33 | 0.0152 | 1 | 0.015 |
| 10:57 | c3, stopped 11:02 | cx33 | 0.0152 | 1 | 0.015 |
| 11:02 | c4, stopped 11:06 | cx33 | 0.0152 | 1 | 0.015 |
| 11:08 | c5 (with the archive test), stopped 11:14 | cx33 | 0.0152 | 1 | 0.015 |
| 15:14 | `image` build 1 | cx33 | 0.0152 | 1 | 0.015 |
| 15:19, 15:22 | c6, c7 (first snapshot starts, cloud-init "degraded") | cx33 | 0.0152 | 2 | 0.030 |
| 15:27 | `image` build 2 | cx33 | 0.0152 | 1 | 0.015 |
| 15:31 | c8 (snapshot) | cx33 | 0.0152 | 1 | 0.015 |
| 15:34–20:28 | c9–c12, stretched by laptop sleep | cx33 | 0.0152 | 7 | 0.106 |
| | Snapshot storage, 2.17 GB, from now on | | | | ~0.03 a month |
| | **Total** (budget €0.50) | | | | **≈ 0.26** |

Prices: `web/wrangler.toml` (cx33 €0.0144/h) plus about €0.0008/h for the
primary IPv4. Hetzner bills each started hour. A final sweep found nothing
labelled `purpose=perf-staging` (servers, firewalls, SSH keys, images).

## The laptop's firewall

The first two tries (00:10 and 00:16) failed in `tofu apply` with
`dial tcp …:443: i/o timeout` to Hetzner and Tailscale, while `curl` worked.
The cause was **LuLu** blocking this worktree's own copies of the OpenTofu
providers (`infra/.terraform/providers/`). After the user allowed them,
everything worked. A new checkout or worktree needs the same.

## State of every item

| Item | State | Note |
|---|---|---|
| Phase timings | passed (laptop and staging) | |
| Staging target | passed | 5 starts and stops; DNS untouched; sweep clean |
| Tailscale every 2 s | passed (staging) | |
| Health check `start_interval` | passed (laptop and staging) | |
| `fix_owner` | passed | chown 0–1 s on the VPS |
| Restore and map pull side by side | passed (laptop and staging) | |
| Map archive | download path measured on a VPS (17 s vs 51 s); publish path unit-tested | the first real stop publishes it |
| Pre-built image | passed (one clean start, c8) | start 260 s → 191 s; the fallback reached the deploy, but without clean times |
| Faster stop | untested on a VPS | a staging stop doesn't back up; unit tests only. The first real stop is its test |
| Server type benchmark | skipped | budget €0.50 |
| Vault copy | read-only finding | streams through the laptop; no change |
| `tofu plan` on the real VPS shows no changes | untested | `tofu test` with mocked providers only. Run `bin/server tofu plan` once before merging |

Also seen: the real VPS was running around 00:00 UTC on 2026-11-21 and was
gone by 10:40 (none at Hetzner). Nothing here touched it.
