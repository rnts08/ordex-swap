# OrdexSwap

Off-chain centralized swap service for OXC (OrdexCoin) ↔ OXG (OrdexGold) exchange.

**Status**: v0.9.1 (176 tests passing, CSRF protection on critical endpoints)

## Features

- Quote-based swap engine supporting OXC ↔ OXG exchange
- Real-time price oracle with fallback support (NestEx)
- Configurable swap fees and rate limits
- Automated deposit address generation per swap
- **Admin Override System** - Complete control to change any swap's state with full audit trail
- Admin dashboard for operations and monitoring
- Automated backup system with restore capabilities
- Comprehensive security testing and hardening
- Full test suite (184 tests, 55% code coverage)
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

## CSRF Protection

Admin state-changing endpoints (POST, PUT, DELETE) are protected with CSRF tokens to prevent cross-site request forgery attacks.

### How CSRF Tokens Work

1. **Obtain a Token**: After authenticating with admin credentials, fetch a CSRF token from `GET /api/v1/admin/csrf-token`
2. **Include the Token**: Include the token in the `X-CSRF-Token` header of your state-changing requests
3. **Validation**: The server validates the token on each protected request. Tokens expire after 1 hour.

### Example Usage

```bash
# 1. Get CSRF token (requires admin auth)
TOKEN=$(curl -s -u admin:password http://localhost:8080/api/v1/admin/csrf-token | jq -r '.data.csrf_token')

# 2. Use token in admin requests (example: withdraw)
curl -X POST http://localhost:8080/api/v1/admin/wallets/withdraw \
  -u admin:password \
  -H "X-CSRF-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"coin": "OXC", "amount": 100, "to_address": "0x..."}'
```

### Protected Endpoints

All admin endpoints that modify state require CSRF token validation:
- `POST /api/v1/admin/wallets/withdraw` - Withdraw funds
- `POST /api/v1/admin/wallets/rotate` - Rotate wallet addresses
- `POST /api/v1/admin/audit/settle` - Settle orphaned transactions
- `POST /api/v1/admin/audit/refund` - Refund orphaned transactions
- `POST /api/v1/admin/audit/acknowledge` - Acknowledge transactions
- `POST /api/v1/admin/swaps/<id>/action` - Perform actions on swaps
- `POST /api/v1/admin/settings` - Update settings
- `PUT /api/v1/admin/wallet-configs` - Update wallet configuration

### Frontend Usage

The admin dashboard (`admin.html`) automatically handles CSRF token management:
- Token is fetched upon login
- Token is included in all state-changing requests
- Token is refreshed as needed

### Development Mode

When `TESTING_MODE=true`, CSRF protection remains enabled for security testing. The token can be obtained via the API and used in automated tests.

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
### Support the project

***ETH/ERC20:*** 0x968cC7D93c388614f620Ef812C5fdfe64029B92d

***SOL:*** HB2o6q6vsW5796U5y7NxNqA7vYZW1vuQjpAHDo7FAMG8

***BTC:*** bc1qkmzc6d49fl0edyeynezwlrfqv486nmk6p5pmta


See [DEPLOY.md](docs/DEPLOY.md) for production deployment guidelines.
