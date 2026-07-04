Run these commands

On the server:

```sh
# Log into remote server
ssh mcprd
cd app

# Force backup now
docker compose exec backup backup now

# Verify backups
docker compose exec backup restic snapshots
```

On the client:

First remove the tailscale entry/key for `mc-prod` host in the tailscale admin console, since this is managed by cloudinit and not terraform (TODO: have it managed by terraform and not cloudinit)

```sh
tofu destroy
tofu apply -auto-approve
git commit --allow-empty -m "Trigger deployment on new server"
git push origin main

# On the server
./app/scripts/restore-backup.sh
docker compose up -d
```

> [!NOTE]
> Can only scale up with hetzner w/o destroying disk, not down. Upscale to higher servers can be done easily, not downscaling (needs to destroy+apply)
