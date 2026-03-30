# Backup and Restore

OrdexSwap automatically backs up the database and wallet files. Backups are stored in the data volume and can be restored when needed.

## How Backups Work

- **Automatic backups**: Run every hour (configurable)
- **Location**: `/app/data/backups/` in the container (persisted via Docker volume)
- **Retention**: Keeps the last 24 backups
- **Contents**:
  - SQLite database (ordex.db.sql)
  - OXC wallet.dat
  - OXG wallet.dat

## Configuration

Environment variables (in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_ENABLED` | true | Enable/disable automatic backups |
| `BACKUP_INTERVAL_HOURS` | 1 | Hours between backups |

## Manual Backup

```bash
# Run backup manually
docker exec ordex-swap-ordex-swap-1 python /app/backup.py
```

## List Backups

```bash
docker exec ordex-swap-ordex-swap-1 python /app/restore.py --list
```

Output example:
```
Available backups:
--------------------------------------------------
ordex_backup_20240330_140000.tar.gz (15.23 MB, 2024-03-30 14:00:00)
ordex_backup_20240330_130000.tar.gz (15.21 MB, 2024-03-30 13:00:00)
ordex_backup_20240330_120000.tar.gz (15.20 MB, 2024-03-30 12:00:00)
```

## Copy Backups to Local Machine

```bash
# Copy a specific backup
docker cp ordex-swap-ordex-swap-1:/app/data/backups/ordex_backup_20240330_140000.tar.gz ./

# Copy all backups
docker cp ordex-swap-ordex-swap-1:/app/data/backups/ ./local_backups/
```

## Restore from Backup

**Warning**: Restoring will overwrite the current database and wallet files. A backup of the current state is created automatically before restoring.

```bash
# Restore from a specific backup
docker exec ordex-swap-ordex-swap-1 python /app/restore.py ordex_backup_20240330_140000.tar.gz
```

After restoring, you may need to restart the service:
```bash
docker compose -f docker-compose.prod.yml restart
```

## Restore from Local Backup

If you have a backup file on your local machine:

```bash
# Copy backup to container
docker cp ./ordex_backup_20240330_140000.tar.gz ordex-swap-ordex-swap-1:/app/data/backups/

# Restore
docker exec ordex-swap-ordex-swap-1 python /app/restore.py ordex_backup_20240330_140000.tar.gz
```

## Backup Files Location on Host

The backups are stored in a Docker named volume. To find the volume:

```bash
docker volume ls | grep ordex
```

To access directly:
```bash
docker run --rm -v ordex-swap_ordex-data:/data -v $(pwd):/backup alpine tar -cvf /backup/backup_extract.tar /data/backups/
```
