docker compose exec backup backup now
docker compose exec backup restic forget --keep-last 3 --prune
