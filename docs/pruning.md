# Chunk pruning

Exploration generates far more chunks than anyone uses. Pruning deletes the chunks
nobody spent time in, and Minecraft generates them fresh the next time someone goes
there. On this world's first dry run (2026-11-19) the defaults would have deleted
81% of the overworld, 88% of the Nether and 93% of the End. A test prune of a local
copy shrank the region files from 3.1 GB to 0.45 GB, and the server started cleanly.

Pruning uses [MCA Selector](https://github.com/Querz/mcaselector) in headless
mode (version pinned and checksummed in `scripts/prune.sh`; 2.9 supports Minecraft
26.3). It runs in a Java container on the host that holds the world.

## What is kept

A chunk is deleted only when it fails **every** rule below. The numbers are set in
[`prune/settings.env`](../prune/settings.env).

| Rule | Setting | Default |
|---|---|---|
| Players spent at least this long in it in total (`InhabitedTime`) | `PRUNE_MIN_INHABITED` | 10 minutes |
| The game saved it recently, i.e. someone was nearby | `PRUNE_UNTOUCHED_DAYS` | 60 days |
| Near a player's last position or respawn point (bed, respawn anchor), from `players/data` | `PRUNE_PLAYER_RADIUS` | 12 chunks |
| Inside an area in [`prune/protect.txt`](../prune/protect.txt) | per line | the inner End (1024 blocks) |
| Next to any chunk kept by the rules above, so builds never border a seam | `PRUNE_BUFFER` | 4 chunks |

To protect an area players don't visit often (a farm, a monument, a portal hub),
add a line to `prune/protect.txt` in block coordinates and commit it:

```
overworld 1200 -340 128   # Alex's sky farm
```

**A guard against mistakes:** if a dimension would lose more than `PRUNE_MAX_PERCENT`
(98%) of its chunks, or the keep rules select nothing, the whole prune is refused and
nothing is deleted anywhere. Every dimension is planned before any is changed.

Pruned chunks regenerate from the **current** seed. The main End island is from
the world's original seed, so `protect.txt` keeps the whole inner End. Protect any
other area kept from the old seed the same way.

Regenerated chunks also get fresh structures: outer-End cities have new loot and elytras,
and pruned villages and temples come back. That's usually wanted. Protect any area
where it isn't.

## Commands

```bash
server prune --dry-run   # report what would be deleted, wherever the world runs
server prune             # back up, prune and restart the game on the VPS
```

A dry run works on a local copy too (`server start local`, then
`server prune --dry-run`). It writes the selections to `.cache/prune/<dimension>-delete.csv`.
To see them on a map, open the local copy (`data/minecraft/world/dimensions/minecraft/<dimension>`)
in the MCA Selector app and use **Selection → Import selection**.

A dry run while the game runs can miss chunks the game is writing at that moment.
That makes its count slightly low, never unsafe: a chunk MCA Selector can't read is
never deleted. A real prune always runs with the game stopped.

A real prune only runs on the VPS, because the local copy is read-only and is never
backed up. `server prune` on the VPS does the following:

1. Takes a backup and checks that it reached R2.
2. Tags that snapshot `pre-prune`. Retention never deletes it, and only the newest
   `PRUNE_KEEP_SNAPSHOTS` (3) keep the tag.
3. Stops the game, runs `scripts/prune.sh`, and starts the game again. If the prune
   fails, it still restarts the game, and it prints the pre-prune snapshot ID.

The hourly backup saves the pruned world from there on.

## Automatic pruning

When `AUTO_PRUNE_DAYS` is greater than 0, `server stop` on the VPS prunes first if
the newest `pre-prune` snapshot is older than that many days (or there is none).
It then takes the usual final backup and deletes the VPS. If anything fails, the
stop is aborted and the VPS keeps running.

It ships turned **off** (`AUTO_PRUNE_DAYS=0`). Look at a dry run first, adjust
`settings.env` and `protect.txt`, then set it to `30` for a monthly prune and commit.

## Undoing a prune

Chunks are deleted from region files, so a rollback restores those files from the
pre-prune snapshot. On the VPS, from `~/app`:

```bash
docker compose exec backup restic snapshots --tag pre-prune   # pick the ID
```

- **Everything:** restore that snapshot with the steps in
  [how2backuprestore.md](how2backuprestore.md). Anything built since then is lost.
- **One area:** restore just that area's region files. A region file covers
  512×512 blocks: `r.<floor(x/512)>.<floor(z/512)>.mca`. The script stops the game,
  restores each file with its `entities/` and `poi/` partners, and starts the game again:

  ```bash
  bash scripts/restore-regions.sh <pre-prune-id> \
    world/dimensions/minecraft/overworld/region/r.2.-1.mca
  ```

  Changes made in those regions since the prune are lost. The rest of the world is
  untouched.
