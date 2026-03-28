# OrdexSwap Backend

Off-chain centralized swap service for OXC (OrdexCoin) ↔ OXG (OrdexGold) exchange.

## Current Status

- **Frontend**: http://localhost:8080/
- **API**: http://localhost:8000/api/v1/ (nginx also proxies `/api/` on port 8080)
- **Status**: Running via docker-compose
- **Testing Mode**: Disabled (daemons run locally for address generation)

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

## Quick Start

### Installation

```bash
cd app
pip install -r requirements.txt
```

### Configuration

Copy the example env file and fill in real values:

```bash
cp .env.example .env
```

Do not commit `.env`; it contains secrets (NestEx API keys and RPC credentials).

### Running in Testing Mode (Development)

```bash
# Enable testing mode
sed -i 's/^TESTING_MODE=.*/TESTING_MODE=true/' app/.env

# Build and start the stack
docker-compose up -d --build

# Initialize/load wallets (idempotent)
docker exec ordex-swap-ordex-swap-1 /app/first-run.sh
```

### Running in Production Mode

```bash
# Disable testing mode
sed -i 's/^TESTING_MODE=.*/TESTING_MODE=false/' app/.env

# Build and start the stack
docker-compose up -d --build

# Initialize/load wallets (idempotent)
docker exec ordex-swap-ordex-swap-1 /app/first-run.sh
```

### Binaries

This repo does not include daemon binaries. Obtain `ordexcoind` and `ordexgoldd` from your internal distribution/source, then place them in `app/data/bin/` and ensure they are executable.

### Production Notes

- Ensure RPC credentials and wallet names are set in `app/.env` (`OXC_RPC_USER`, `OXC_RPC_PASSWORD`, `OXG_RPC_USER`, `OXG_RPC_PASSWORD`, `OXC_WALLET_NAME`, `OXG_WALLET_NAME`).
- Run `first-run.sh` after deployment to load/create the configured wallets.
- The UI is served on `http://localhost:8080/` and the admin UI is at `http://localhost:8080/admin.html`.

## Testing

See `TESTING.md` for how to run the full test suite (unit, e2e, and UI tests).

## Testing Mode

When `TESTING_MODE=true`, the service still runs the daemons for real RPC and address generation, but simulates outgoing payments:

| Component | Testing Mode | Production Mode |
|-----------|--------------|-----------------|
| Price fetching | Real NestEx API (cached) | Real NestEx API |
| Address generation | Real RPC to daemon | Real RPC to daemon |
| Balance checking | Real RPC to daemon | Real RPC to daemon |
| Coin sending | Mock txid (no on-chain) | Real wallet transaction |
| Daemon startup | Starts ordexcoind/ordexgoldd | Starts ordexcoind/ordexgoldd |
| Swap completion | Instant (simulated) | Real transaction |

### API Endpoints (Testing Mode)

```bash
# Health check (shows testing mode status)
curl http://localhost:8000/health
# {"success": true, "data": {"status": "healthy", "service": "ordex-swap", "testing_mode": true}}

# Get status
curl http://localhost:8000/api/v1/status
# {"success": true, "data": {"testing_mode": true, "supported_coins": ["OXC", "OXG"]}}

# Get quote
curl -X POST http://localhost:8000/api/v1/quote \
  -H "Content-Type: application/json" \
  -d '{"from": "OXC", "to": "OXG", "amount": 10}'

# Create swap
curl -X POST http://localhost:8000/api/v1/swap \
  -H "Content-Type: application/json" \
  -d '{"from": "OXC", "to": "OXG", "amount": 10, "user_address": "oxc_test_user"}'

# Confirm deposit (completes swap in testing mode)
curl -X POST http://localhost:8000/api/v1/swap/<swap_id>/confirm \
  -H "Content-Type: application/json" \
  -d '{"deposit_txid": "test_txid_123"}'

# Get wallet balances
curl http://localhost:8000/api/v1/balance

# Get deposit address for coin
curl http://localhost:8000/api/v1/deposit/OXC
```

### Full E2E Test Script

```bash
# Start service in testing mode
TESTING_MODE=true python main.py &

# Wait for startup
sleep 2

# 1. Get status
curl -s http://localhost:8000/api/v1/status | jq .

# 2. Create a quote
curl -s -X POST http://localhost:8000/api/v1/quote \
  -H "Content-Type: application/json" \
  -d '{"from": "OXC", "to": "OXG", "amount": 10}' | jq .

# 3. Create swap
SWAP_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/swap \
  -H "Content-Type: application/json" \
  -d '{"from": "OXC", "to": "OXG", "amount": 10, "user_address": "test_user_oxc"}')
echo "$SWAP_RESPONSE" | jq .

SWAP_ID=$(echo "$SWAP_RESPONSE" | jq -r '.data.swap_id')
DEPOSIT_ADDR=$(echo "$SWAP_RESPONSE" | jq -r '.data.deposit_address')

echo "Deposit address: $DEPOSIT_ADDR"

# 4. Confirm deposit (simulate user sending coins)
curl -s -X POST "http://localhost:8000/api/v1/swap/$SWAP_ID/confirm" \
  -H "Content-Type: application/json" \
  -d '{"deposit_txid": "mock_deposit_123"}' | jq .

# 5. Check swap status
curl -s "http://localhost:8000/api/v1/swap/$SWAP_ID" | jq .

# 6. List all swaps
curl -s http://localhost:8000/api/v1/swaps | jq .
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TESTING_MODE` | `false` | Enable testing/dev mode (set `false` to run daemons) |
| `NESTEX_API_KEY` | (dev key) | NestEx API key |
| `NESTEX_API_SECRET` | (dev secret) | NestEx API secret |
| `OXC_RPC_URL` | `http://127.0.0.1:25173` | OXC daemon RPC |
| `OXG_RPC_URL` | `http://127.0.0.1:25465` | OXG daemon RPC |
| `OXC_RPC_USER` | `rpcuser` | RPC username |
| `OXC_RPC_PASSWORD` | `rpcpassword` | RPC password |
| `API_HOST` | `127.0.0.1` | API bind host |
| `API_PORT` | `8000` | API bind port |
| `ORDEXCOIND_PATH` | `./data/bin/ordexcoind` | Path to ordexcoind binary |
| `ORDEXGOLDD_PATH` | `./data/bin/ordexgoldd` | Path to ordexgoldd binary |
| `DATA_DIR` | `./data` | Base data directory |
| `DB_PATH` | `./data/ordex.db` | SQLite database for prices and swaps |
| `ORDEXCOIND_DATADIR` | `./data/oxc` | OXC blockchain data directory |
| `ORDEXGOLDD_DATADIR` | `./data/oxg` | OXG blockchain data directory |

## Configuration

Edit `swap-service/config.py` to adjust:

- `SWAP_FEE_PERCENT` - Fee percentage (default: 1.0)
- `SWAP_MIN_AMOUNT` - Minimum swap amount (default: 0.0001)
- `SWAP_MAX_AMOUNT` - Maximum swap amount (default: 10000)
- `NESTEX_PRICE_TTL_SECONDS` - Price cache TTL (default: 30)
- `NESTEX_MAX_PRICE_AGE_SECONDS` - Max price age (default: 60)

## Price Oracle

The service uses NestEx API to get USDT trading pair prices and calculates the cross rate:

```
OXC/OXG = OXC/USDT ÷ OXG/USDT
```

Price history and cached rates are stored in SQLite (`DB_PATH`) so data persists across restarts and reduces API calls.

### Price Endpoints

```bash
# Get current prices (includes USDT rates and cross rate)
curl http://localhost:8000/api/v1/prices/current

# Get price history
curl http://localhost:8000/api/v1/prices/history?limit=10

# Get price statistics
curl http://localhost:8000/api/v1/prices/stats?hours=24
```

Price history stores:
- `oxc_usdt` - OXC price in USDT
- `oxg_usdt` - OXG price in USDT  
- `cross_rate` - OXC/OXG calculated from USDT pairs
- `source` - Always "nestex_cross_usdt"
- `timestamp` - UTC timestamp

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/status` | GET | Service status |
| `/api/v1/prices/current` | GET | Current USDT rates and cross rate |
| `/api/v1/prices/history` | GET | Price history with USDT rates |
| `/api/v1/prices/stats` | GET | Price statistics |
| `/api/v1/quote` | POST | Get swap quote |
| `/api/v1/swap` | POST | Create swap |
| `/api/v1/swap/<id>` | GET | Get swap details |
| `/api/v1/swap/<id>/confirm` | POST | Confirm deposit |
| `/api/v1/swap/<id>/cancel` | POST | Cancel swap |
| `/api/v1/balance` | GET | Wallet balances |
| `/api/v1/deposit/<coin>` | GET | Get deposit address |
| `/api/v1/swaps` | GET | List all swaps |

## Testing

```bash
cd app
python -m pytest tests/test_swap.py -v
```

All 34 tests pass.

## Docker

### Using docker-compose (recommended)

```bash
docker-compose up -d --build
```

Access at: http://localhost:8080/

### Manual Docker

```bash
docker build -t ordex-swap .
docker run -p 8080:8080 -e TESTING_MODE=false ordex-swap
```

Note: Container nginx runs on port 8080 internally, mapped to host port 8080.
Daemons are started with localhost-only RPC and bind settings and use independent data dirs under `data/`.

## Support this and other project development by rnts08

Support development of this project by donating:

    * BTC: bc1qkmzc6d49fl0edyeynezwlrfqv486nmk6p5pmta
    * ETH/ERC-20: 0xC13D012CdAae7978CAa0Ef5B1E30ac6e65e6b17F
    * LTC: ltc1q0ahxru7nwgey64agffr7x89swekj7sz8stqc6x
    * SOL: HB2o6q6vsW5796U5y7NxNqA7vYZW1vuQjpAHDo7FAMG8
    * XRP: rUW7Q64vR4PwDM3F27etd6ipxK8MtuxsFs
    * OXC: oxc1q3psft0hvlslddyp8ktr3s737req7q8hrl0rkly
    * OXG: oxg1q34apjkn2yc6rsvuua98432ctqdrjh9hdkhpx0t

Use Nestex to donate: https://nestex.one/pay/Black-Spirited-174344

Buy the creator a beer: https://buymeacoffee.com/timhbergsta

*** All donations goes directly to the creator of this project for development and maintenance. ***
