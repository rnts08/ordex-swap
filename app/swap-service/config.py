import os

NESTEX_PUBLIC_BASE_URL = "https://trade.nestex.one/api/cg"
NESTEX_PUBLIC_MIN_GAP_SECONDS = 6
NESTEX_PRICE_TTL_SECONDS = 30
NESTEX_MAX_PRICE_AGE_SECONDS = 60

OXC_RPC_URL = os.getenv("OXC_RPC_URL", "http://127.0.0.1:25173")
OXC_RPC_USER = os.getenv("OXC_RPC_USER", "")
OXC_RPC_PASSWORD = os.getenv("OXC_RPC_PASSWORD", "")
OXC_WALLET_NAME = os.getenv("OXC_WALLET_NAME", "oxc_wallet")

OXG_RPC_URL = os.getenv("OXG_RPC_URL", "http://127.0.0.1:25465")
OXG_RPC_USER = os.getenv("OXG_RPC_USER", "")
OXG_RPC_PASSWORD = os.getenv("OXG_RPC_PASSWORD", "")
OXG_WALLET_NAME = os.getenv("OXG_WALLET_NAME", "oxg_wallet")

SWAP_FEE_PERCENT = float(os.getenv("SWAP_FEE_PERCENT", "1.0"))
SWAP_MIN_FEE_OXC = float(os.getenv("SWAP_MIN_FEE_OXC", "1.0"))
SWAP_MIN_FEE_OXG = float(os.getenv("SWAP_MIN_FEE_OXG", "1.0"))
SWAP_MIN_AMOUNT = float(os.getenv("SWAP_MIN_AMOUNT", "0.0001"))
SWAP_MAX_AMOUNT = float(os.getenv("SWAP_MAX_AMOUNT", "10000.0"))
SWAP_SLIPPAGE_TOLERANCE_PERCENT = float(
    os.getenv("SWAP_SLIPPAGE_TOLERANCE_PERCENT", "2.0")
)

DEFAULT_LIMIT = 100
WALLET_RPC_TIMEOUT = 60
WALLET_MAX_CONF = 9999999

SETTLEMENT_INTERVAL_SECONDS = int(os.getenv("SETTLEMENT_INTERVAL_SECONDS", "30"))
PRICE_FETCH_INTERVAL_SECONDS = int(os.getenv("PRICE_FETCH_INTERVAL_SECONDS", "30"))

OXC_USDT_FALLBACK_PRICE = float(os.getenv("OXC_USDT_FALLBACK_PRICE", "0.001"))
OXG_USDT_FALLBACK_PRICE = float(os.getenv("OXG_USDT_FALLBACK_PRICE", "0.044"))

OXC_OXG_FALLBACK_PRICE = float(os.getenv("OXC_OXG_FALLBACK_PRICE", "0.02268"))

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

TESTING_MODE = os.getenv("TESTING_MODE", "false").lower() == "true"
# Disable rate limiting in testing mode, or if explicitly disabled
RATE_LIMIT_ENABLED = (
    os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true" and not TESTING_MODE
)

SWAP_CONFIRMATIONS_REQUIRED = int(os.getenv("SWAP_CONFIRMATIONS_REQUIRED", "1"))
if TESTING_MODE:
    SWAP_CONFIRMATIONS_REQUIRED = 0

SWAP_EXPIRE_MINUTES = int(os.getenv("SWAP_EXPIRE_MINUTES", "15"))

ORDEXCOIND_PATH = os.getenv("ORDEXCOIND_PATH", "./ordexcoind")
ORDEXGOLDD_PATH = os.getenv("ORDEXGOLDD_PATH", "./ordexgoldd")

ORDEXCOIND_DATADIR = os.getenv("ORDEXCOIND_DATADIR", "./data/oxc")
ORDEXGOLDD_DATADIR = os.getenv("ORDEXGOLDD_DATADIR", "./data/oxg")

DATA_DIR = os.getenv("DATA_DIR", "./data")
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "ordex.db"))

BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "1"))
BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "true").lower() == "true"
PRICE_HISTORY_MAX_ENTRIES = 1000

SUPPORTED_COINS = ["OXC", "OXG"]
# Stats include all swap statuses to show full volume including cancelled/failed/timed_out
STAT_INCLUDED_STATUSES = ["completed", "reconciled", "late_deposit", "pending", "processing", "delayed", "cancelled", "timed_out", "failed"]
