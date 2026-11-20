# The web map (BlueMap)

**https://world.cactuz.dev/map/** shows a 3D map of the Overworld, Nether and
End, made by [BlueMap](https://bluemap.bluecolored.de/). It stays online while
the VPS is off: it is a set of static files in the public world bucket, like
`world.zip`. It is updated at each `server stop`, so it shows the world as it
was then. It has no live player positions.

## How it works

1. While the VPS runs, BlueMap renders changed chunks in the background
   (1 render thread, `config/bluemap/core.conf`) into
   `data/minecraft/bluemap/web/`. Its own web server is off
   (`webserver.conf`), and no port is published.
2. `server stop`, after the final backup and `world.zip`, runs
   `scripts/publish-map.sh` on the VPS. It copies that folder to
   `<PUBLIC_WORLD_BUCKET>/map/` with rclone: the web app, the tiles and
   BlueMap's render state (`maps/*/rstate`). It uses `copy`, never `sync`, so
   it never deletes anything published. A failure only warns.
3. `server start vps` restores the world from restic, then `scripts/deploy.sh`
   pulls `map/` back into `data/minecraft/bluemap/web/`. With the render state
   back, BlueMap only renders what changed since. A failed pull only warns;
   BlueMap then renders the whole world again (hours on a big world, at low
   priority). A local copy (`server start local`) pulls it too, read-only.

The map is not in the restic backups (`EXCLUDES` in `compose.yml`): the bucket
is its storage, and it can always be rendered again from the world.

The tiles are stored gzipped (`*.prbm.gz`, `textures.json.gz`) and served as
they are, without a `Content-Encoding` header. The web app downloads the `.gz`
files and decompresses them itself (`client-decompression: true` in
`config/bluemap/webapp.conf`), which is what makes plain R2 hosting work. Tiles
that were never rendered return 404; the web app ignores that.

## Settings

The managed files are in `config/bluemap/` (copied over the world's at every
start; see `config/README.md`):

| File | Set here |
|---|---|
| `core.conf` | `accept-download: true` (BlueMap downloads the Minecraft client jar for textures; this accepts Mojang's EULA), 1 render thread, metrics off |
| `webserver.conf` | `enabled: false` |
| `webapp.conf` | `client-decompression: true` |

The map definitions (`maps/*.conf`) and `plugin.conf` keep BlueMap's defaults
and are not managed. To change one, copy it from the world's
`config/bluemap/` into this repository's and commit it.

Useful commands (in game as an op, or `rcon-cli`):

```
bluemap                       render status
bluemap force-update world    re-render the Overworld map's changed regions
bluemap purge world           delete the Overworld map; it renders from scratch
```

A purge only takes effect on the public map after the next `stop`, and stale
tiles there stay until they are rendered again (`copy` never deletes). To start
the public map over, delete `map/` in the bucket in the Cloudflare dashboard.

## Checks after the first VPS stop

- `https://world.cactuz.dev/map/` loads and shows terrain.
- `https://world.cactuz.dev/map/maps/world/textures.json.gz` downloads as a
  gzip file (no `Content-Encoding: gzip` response header).
- The next `server start vps` log has "Pulling the published map", and
  `bluemap` in game reports the maps as updated within minutes, not hours.
