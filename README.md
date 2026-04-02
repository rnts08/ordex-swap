# OrdexSwap

Off-chain centralized swap service for OXC (OrdexCoin) ↔ OXG (OrdexGold) exchange.

**Status**: v0.9.1 (176 tests passing, CSRF protection on critical endpoints)

## Features

- Quote-based swap engine supporting OXC ↔ OXG exchange
- Real-time price oracle with fallback support (NestEx)
- Configurable swap fees and rate limits
- Automated deposit address generation per swap
- Admin dashboard for operations and monitoring
- Automatic backup system with restore capabilities
- Comprehensive security testing and hardening
- Full test suite (176 tests, 54% code coverage)
- Docker containerization with production configs

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
- [Security Policy](docs/SECURITY.md) - Threat model, hardening measures, and incident response
- [Release Roadmap](docs/ROADMAP.md) - v1.0.0 GA timeline and planned features
- [Changelog](CHANGELOG.md) - Version history and breaking changes

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
- `TESTING_MODE` - Enable testing mode (mocked wallets, no daemons)
- `OXC_RPC_*` / `OXG_RPC_*` - RPC credentials (host, port, user, pass)
- `SWAP_FEE_PERCENT` - Fee percentage (default: 1.0)
- `RATE_LIMIT_ENABLED` - Enable rate limiting (default: true)
- `ADMIN_PASSWORD` - Admin interface password (required)
- `BACKUP_ENABLED` - Enable automatic backups (default: true)
- `BACKUP_INTERVAL_HOURS` - Hours between backups (default: 1)
- `DEBUG` - Debug mode (default: false, must be false in production)

## Testing

```bash
# Run full test suite
cd app && python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ --cov=swap-service --cov-report=html

# Run specific test file
python -m pytest tests/test_swap.py -v
```

Current test coverage: 176 tests passing across swap logic, API endpoints, security, and daemon lifecycle.

## Building for Production

```bash
# Build production Docker images
docker compose -f docker-compose.prod.yml up -d --build

# Verify health
curl http://localhost:8080/health
```

See [DEPLOY.md](docs/DEPLOY.md) for production deployment guidelines.
