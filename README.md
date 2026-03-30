# OrdexSwap

Off-chain centralized swap service for OXC (OrdexCoin) ↔ OXG (OrdexGold) exchange.

## Quick Start (Development)

```bash
# Copy environment template
cp app/.env.example app/.env

# Enable testing mode for development
sed -i 's/^TESTING_MODE=.*/TESTING_MODE=true/' app/.env

# Start the application
docker compose up -d --build
```

Access at:
- **Frontend**: http://localhost:8080/
- **Admin**: http://localhost:8080/admin.html
- **API**: http://localhost:8080/api/v1/

## Documentation

See the `docs/` folder for detailed documentation:

- [Deployment Guide](docs/DEPLOY.md) - Production deployment instructions
- [Testing Guide](docs/TESTING.md) - Running tests locally and in Docker
- [Backup & Restore](docs/BACKUPS.md) - Backup system and restore procedures

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  User       │────▶│  Swap API    │────▶│  Price Oracle   │
│  (Frontend) │     │  (Flask)     │     │  (NestEx)       │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       ┌──────────────┐         ┌─────────────────┐
       │  ordexcoind  │         │  ordexgoldd     │
       │  (OXC)       │         │  (OXG)          │
       └──────────────┘         └─────────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/status` | GET | Service status |
| `/api/v1/prices/current` | GET | Current prices |
| `/api/v1/quote` | POST | Get swap quote |
| `/api/v1/swap` | POST | Create swap |
| `/api/v1/swap/<id>` | GET | Get swap details |
| `/api/v1/balance` | GET | Wallet balances |
| `/api/v1/deposit/<coin>` | GET | Get deposit address |

## Configuration

Environment variables (see `app/.env.example`):
- `TESTING_MODE` - Enable testing mode
- `OXC_RPC_*` / `OXG_RPC_*` - RPC credentials
- `SWAP_FEE_PERCENT` - Fee percentage (default: 1.0)
- `BACKUP_ENABLED` - Enable automatic backups (default: true)
- `BACKUP_INTERVAL_HOURS` - Hours between backups (default: 1)
