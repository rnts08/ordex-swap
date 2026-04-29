# Deployment Guide

## Prerequisites

- Docker and Docker Compose installed on the server
- SSH access to the server
- Daemon binaries: `ordexcoind` and `ordexgoldd`

## Quick Deploy

1. **Copy daemon binaries** to `data/bin/`:
   ```
   data/bin/ordexcoind
   data/bin/ordexgoldd
   ```

2. **Configure environment** in `app/.env`:
   - Set `TESTING_MODE=false`
   - Set RPC credentials for OXC and OXG

3. **Run deployment script**:
   ```bash
   ./scripts/deploy.sh
   ```

4. **On the server**, build and start:
   ```bash
   cd /opt/ordex-swap
   docker compose -f docker-compose.prod.yml up -d --build
   ```

5. **Initialize wallets and run migrations**:
   ```bash
   docker exec ordex-swap-ordex-swap-1 /app/first-run.sh
   ```

   This step is idempotent - run it on first deployment and after updates.

## Server Structure

After deployment, the server will have:
```
/opt/ordex-swap/
├── app/
│   ├── swap-service/     # Python API code
│   ├── frontend/        # Static files
│   ├── main.py
│   ├── .env            # Environment config
│   └── data/           # Wallet data (in docker volume)
├── frontend/            # Frontend container
├── data/bin/           # Daemon binaries
├── Dockerfile
├── Dockerfile.frontend
├── docker-compose.prod.yml
└── Caddyfile (removed - deployed separately)
```

## Containers

- **ordex-swap**: Python API (port 8000, internal)
- **frontend**: Nginx serving static files (port 8080, internal)

## Managing Swaps

### Disable/Enable Swaps Globally

1. Open `/admin.html` in your browser
2. Login with admin credentials
3. Go to "Swap Control" section
4. Click "Disable Swaps" or "Enable Swaps"

When disabled:
- Users cannot create new swaps
- Quote and price endpoints still work
- Existing swaps can still be processed

## Troubleshooting

### Check logs
```bash
docker logs ordex-swap-ordex-swap-1
```

### Check health
```bash
curl https://ordexswap.online/health
```

### Restart services
```bash
cd /opt/ordex-swap
docker compose -f docker-compose.prod.yml restart
```

### Initialize wallets (if needed)
```bash
docker exec ordex-swap-ordex-swap-1 /app/first-run.sh
```

### Backup and Restore

See [BACKUPS.md](BACKUPS.md) for backup and restore procedures.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TESTING_MODE` | Set to `false` for production |
| `OXC_RPC_USER` | OXC RPC username |
| `OXC_RPC_PASSWORD` | OXC RPC password |
| `OXG_RPC_USER` | OXG RPC username |
| `OXG_RPC_PASSWORD` | OXG RPC password |
| `OXC_WALLET_NAME` | OXC wallet name (e.g., `oxc_wallet`) |
| `OXG_WALLET_NAME` | OXG wallet name (e.g., `oxg_wallet`) |
| `BACKUP_ENABLED` | Enable automatic backups (default: true) |
| `BACKUP_INTERVAL_HOURS` | Hours between backups (default: 1) |
