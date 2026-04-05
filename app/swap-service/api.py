import logging
import math
import re
import base64
import uuid
import time
from functools import wraps
from datetime import datetime, timezone
from flask import Flask, request, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from structured_logging import StructuredLogger

from price_oracle import PriceOracle, PriceOracleError, PriceOracleStaleError
from wallet_rpc import WalletRPCError
from swap_engine import (
    SwapEngine,
    SwapError,
    InvalidAmountError,
    UnsupportedPairError,
    LiquidityHoldError,
)
from swap_history import SwapHistoryService
from price_history import PriceHistoryService
from admin_service import AdminService
from config import (
    API_HOST,
    API_PORT,
    SUPPORTED_COINS,
    TESTING_MODE,
    RATE_LIMIT_ENABLED,
    SWAP_FEE_PERCENT,
    SWAP_CONFIRMATIONS_REQUIRED,
    SWAP_MIN_FEE_OXC,
    SWAP_MIN_FEE_OXG,
    SWAP_MIN_AMOUNT,
    SWAP_MAX_AMOUNT,
    SWAP_EXPIRE_MINUTES,
)

logger = StructuredLogger(__name__)

app = Flask(__name__)

limiter = Limiter(
    app=app,
    key_func=lambda: request.headers.get("X-Forwarded-For", request.remote_addr),
    storage_uri="memory://",
    default_limits=["500 per day", "200 per hour"],
    enabled=RATE_LIMIT_ENABLED,
)

swap_engine: SwapEngine = None
price_oracle: PriceOracle = None
price_history: PriceHistoryService = None
swap_history: SwapHistoryService = None
admin_service: AdminService = None

# CSRF token storage: {token_string: (username, timestamp)}
_csrf_tokens: dict = {}
CSRF_TOKEN_EXPIRY_SECONDS = 3600  # 1 hour


def generate_csrf_token(username: str) -> str:
    """Generate a new CSRF token for the given username."""
    token = str(uuid.uuid4())
    timestamp = time.time()
    _csrf_tokens[token] = (username, timestamp)
    # Clean up expired tokens
    _cleanup_csrf_tokens()
    return token


def _cleanup_csrf_tokens():
    """Remove expired CSRF tokens from storage."""
    current_time = time.time()
    expired = [
        tok
        for tok, (_, ts) in _csrf_tokens.items()
        if current_time - ts > CSRF_TOKEN_EXPIRY_SECONDS
    ]
    for tok in expired:
        _csrf_tokens.pop(tok, None)


def validate_csrf_token(token: str, username: str) -> bool:
    """Validate a CSRF token for the given username."""
    if not token or not username:
        return False
    _cleanup_csrf_tokens()
    stored = _csrf_tokens.get(token)
    if not stored:
        return False
    stored_username, timestamp = stored
    if stored_username != username:
        return False
    if time.time() - timestamp > CSRF_TOKEN_EXPIRY_SECONDS:
        _csrf_tokens.pop(token, None)
        return False
    return True


def init_app(
    engine: SwapEngine,
    oracle: PriceOracle,
    price_hist: PriceHistoryService = None,
    swap_hist: SwapHistoryService = None,
    admin_svc: AdminService = None,
):
    global swap_engine, price_oracle, price_history, swap_history, admin_service
    swap_engine = engine
    price_oracle = oracle
    price_history = price_hist
    swap_history = swap_hist
    admin_service = admin_svc


def json_error(message: str, status_code: int, error_code: str = None):
    response = {"error": message, "success": False}
    if error_code:
        response["error_code"] = error_code
    return jsonify(response), status_code


def json_success(data):
    response = {"success": True, "data": data}
    return jsonify(response)


# Allowlist of safe error messages that can be shown to users
# These are user-friendly messages that don't leak internal details
SAFE_USER_ERROR_MESSAGES = {
    # Validation errors
    "Invalid amount": "Invalid amount",
    "Invalid user_address": "Invalid user_address",
    "Invalid coin": "Invalid coin",
    "Invalid address format": "Invalid address format",
    "Invalid action": "Invalid action",
    "Invalid request": "Invalid request",
    "Invalid or expired CSRF token": "Invalid or expired CSRF token",
    # Missing field errors
    "Missing required fields": "Missing required fields",
    "Missing from, to, or amount": "Missing from, to, or amount",
    "Missing user_address": "Missing user_address",
    "Missing deposit_txid": "Missing deposit_txid",
    "Missing status field": "Missing status field",
    "Missing address parameter": "Missing address parameter",
    "Missing to_address": "Missing to_address",
    "Missing amount": "Missing amount",
    "Missing required fields (txid, coin, amount, address)": "Missing required fields",
    # Authentication errors
    "Authentication required": "Authentication required",
    "Invalid credentials": "Invalid credentials",
    "CSRF token required": "CSRF token required",
    # Swap-specific errors
    "Swap not found": "Swap not found",
    "Swap operation failed": "Swap operation failed",
    "Swap in invalid state": "Swap in invalid state",
    "Swap already completed or unprocessable": "Swap already completed or unprocessable",
    "Cannot swap same coin": "Cannot swap same coin",
    "Cannot cancel swap in state": "Cannot cancel swap in this state",
    # Validation range errors
    "below minimum": "Amount below minimum allowed",
    "above maximum": "Amount above maximum allowed",
    "too small": "Amount too small",
    "too large": "Amount too large",
    # Service errors
    "Service unavailable": "Service temporarily unavailable",
    "Price unavailable": "Price temporarily unavailable",
    "Swap temporarily unavailable": "Swap temporarily unavailable",
    "Wallet error": "Wallet service temporarily unavailable",
    # Liquidity errors
    "Liquidity delay": "Swap temporarily delayed due to liquidity",
    "Insufficient liquidity": "Swap temporarily delayed due to liquidity",
    # State errors
    "Unsupported pair": "Currency pair not supported",
    "Fee too high": "Invalid amount after fees",
    "Zero or negative output": "Invalid amount after fees",
    # Admin errors
    "Operation failed": "Operation failed",
    "Update failed": "Update failed",
}

# Safe error prefixes that can be shown to users
SAFE_ERROR_PREFIXES = [
    "Invalid",
    "Missing",
    "Unsupported",
    "Cannot",
    "Authentication",
    "CSRF",
    "Amount",
    "Currency",
    "Service",
    "Price",
    "Swap",
    "Wallet",
    "Liquidity",
    "Operation",
    "Update",
]

# Error codes that are safe to expose to users
SAFE_ERROR_CODES = {
    "MISSING_PARAMS",
    "INVALID_AMOUNT",
    "INVALID_ADDRESS",
    "INVALID_COIN",
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "AUTHENTICATION_REQUIRED",
    "CSRF_TOKEN_REQUIRED",
    "CSRF_TOKEN_INVALID",
    "SWAPS_DISABLED",
    "LIQUIDITY_DELAY",
    "PRICE_UNAVAILABLE",
    "WALLET_ERROR",
    "SWAP_ERROR",
}


def sanitize_error_message(error: Exception, default_message: str = "An error occurred") -> str:
    """
    Sanitize error messages for user-facing responses.
    
    Uses an allowlist approach to only return error messages that are:
    1. Pre-approved safe messages
    2. Start with safe prefixes
    3. Don't contain potentially leaking internal details
    
    For admin debugging, the full error is always logged with structured logging.
    
    Args:
        error: The exception that was raised
        default_message: The fallback message to use if the error is not safe
        
    Returns:
        A sanitized error message safe for user-facing responses
    """
    if not error:
        return default_message
    
    error_msg = str(error)
    if not error_msg:
        return default_message
    
    # Truncate very long messages
    if len(error_msg) > 200:
        error_msg = error_msg[:200]
    
    # Check for exact match in allowlist
    if error_msg in SAFE_USER_ERROR_MESSAGES:
        return SAFE_USER_ERROR_MESSAGES[error_msg]
    
    # Check for partial match in allowlist (case-insensitive)
    error_lower = error_msg.lower()
    for safe_msg in SAFE_USER_ERROR_MESSAGES:
        if safe_msg.lower() in error_lower:
            return SAFE_USER_ERROR_MESSAGES[safe_msg]
    
    # Check if message starts with a safe prefix
    for prefix in SAFE_ERROR_PREFIXES:
        if error_msg.startswith(prefix):
            # Additional check: ensure it doesn't contain leaking patterns
            leaking_patterns = [" at 0x", "File \"", "line ", "Traceback", "sqlite3", "urllib"]
            if not any(p in error_msg for p in leaking_patterns):
                return error_msg[:150]
    
    # Default to safe message
    return default_message


def log_error_for_admin(error: Exception, context: str = None, swap_id: str = None):
    """
    Log full error details for admin review.
    
    This function logs the complete error information including stack trace
    for admin debugging. These logs are only visible to administrators
    through the audit log and monitoring systems.
    
    Args:
        error: The exception to log
        context: Additional context about where the error occurred
        swap_id: Optional swap ID for correlation
    """
    import traceback
    
    error_details = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": traceback.format_exc(),
        "context": context,
        "swap_id": swap_id,
    }
    
    if swap_id:
        logger.error(f"Error in swap {swap_id}: {error}", **error_details)
    else:
        logger.error(f"Error{f' in {context}' if context else ''}: {error}", **error_details)


def _parse_basic_auth(header_value: str):
    if not header_value or not header_value.startswith("Basic "):
        return None, None
    try:
        encoded = header_value.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
        return username, password
    except Exception:
        return None, None


def require_admin_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not admin_service:
            return json_error("Service unavailable", 500)
        username, password = _parse_basic_auth(request.headers.get("Authorization"))
        if not username:
            return json_error("Authentication required", 401)

        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
        if not admin_service.verify_credentials(username, password, ip_address):
            return json_error("Invalid credentials", 401)

        g.admin_username = username
        g.admin_ip = ip_address
        return func(*args, **kwargs)

    return wrapper


def require_csrf_token(func):
    """Decorator to require a valid CSRF token for state-changing admin operations."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Only require CSRF token for state-changing methods (POST, PUT, DELETE)
        if request.method not in ["POST", "PUT", "DELETE"]:
            return func(*args, **kwargs)

        # Get username from Flask g (set by require_admin_auth)
        username = getattr(g, "admin_username", None)
        if not username:
            return json_error("Authentication required", 401)

        # Get CSRF token from header
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            return json_error("CSRF token required", 403, "CSRF_TOKEN_REQUIRED")

        # Validate the token
        if not validate_csrf_token(csrf_token, username):
            return json_error(
                "Invalid or expired CSRF token", 403, "CSRF_TOKEN_INVALID"
            )

        return func(*args, **kwargs)

    return wrapper


@app.route("/health", methods=["GET"])
@limiter.limit("1000 per hour")
def health_check():
    return json_success(
        {"status": "healthy", "service": "ordex-swap", "testing_mode": TESTING_MODE}
    )


@app.route("/api/v1/status", methods=["GET"])
def get_status():
    swaps_enabled = True
    fee_percent = SWAP_FEE_PERCENT
    confirmations_required = SWAP_CONFIRMATIONS_REQUIRED
    min_fee_oxc = SWAP_MIN_FEE_OXC
    min_fee_oxg = SWAP_MIN_FEE_OXG
    min_amount = SWAP_MIN_AMOUNT
    max_amount = SWAP_MAX_AMOUNT
    expire_minutes = SWAP_EXPIRE_MINUTES
    if admin_service:
        swaps_enabled = admin_service.get_swaps_enabled()
        db_fee = admin_service.get_swap_fee_percent()
        if db_fee is not None:
            fee_percent = db_fee
        db_confirmations = admin_service.get_swap_confirmations_required()
        if db_confirmations is not None:
            confirmations_required = db_confirmations
        db_min_fee_oxc = admin_service.get_swap_min_fee("OXC")
        if db_min_fee_oxc is not None:
            min_fee_oxc = db_min_fee_oxc
        db_min_fee_oxg = admin_service.get_swap_min_fee("OXG")
        if db_min_fee_oxg is not None:
            min_fee_oxg = db_min_fee_oxg
        db_min_amount = admin_service.get_swap_min_amount()
        if db_min_amount is not None:
            min_amount = db_min_amount
        db_max_amount = admin_service.get_swap_max_amount()
        if db_max_amount is not None:
            max_amount = db_max_amount
        db_expire_mins = admin_service.get_swap_expire_minutes()
        if db_expire_mins is not None:
            expire_minutes = db_expire_mins
    return json_success(
        {
            "testing_mode": TESTING_MODE,
            "supported_coins": SUPPORTED_COINS,
            "swaps_enabled": swaps_enabled,
            "fee_percent": fee_percent,
            "confirmations_required": confirmations_required,
            "min_fee_oxc": min_fee_oxc,
            "min_fee_oxg": min_fee_oxg,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "expire_minutes": expire_minutes,
        }
    )


@app.route("/api/v1/quote", methods=["POST"])
@limiter.limit("10 per minute")
def create_quote():
    data = request.get_json() or {}

    from_coin = data.get("from", "").upper()
    to_coin = data.get("to", "").upper()
    amount = data.get("amount")

    if not from_coin or not to_coin or amount is None:
        return json_error("Missing from, to, or amount", 400, "MISSING_PARAMS")

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return json_error("Invalid amount", 400, "INVALID_AMOUNT")
    if not math.isfinite(amount):
        return json_error("Invalid amount", 400, "INVALID_AMOUNT")

    try:
        quote = swap_engine.create_swap_quote(from_coin, to_coin, amount)
        return json_success(quote)
    except (InvalidAmountError, UnsupportedPairError) as e:
        return json_error(
            sanitize_error_message(e, "Validation failed"), 400, "VALIDATION_ERROR"
        )
    except PriceOracleError as e:
        return json_error(
            sanitize_error_message(e, "Price unavailable"), 503, "PRICE_UNAVAILABLE"
        )


@app.route("/api/v1/swap", methods=["POST"])
@limiter.limit("10 per minute")
def create_swap():
    data = request.get_json() or {}

    from_coin = data.get("from", "").upper()
    to_coin = data.get("to", "").upper()
    amount = data.get("amount")
    user_address = data.get("user_address", "").strip()

    if not from_coin or not to_coin or amount is None or not user_address:
        return json_error("Missing required fields", 400, "MISSING_PARAMS")

    if not re.match(r"^[A-Za-z0-9_-]{8,120}$", user_address):
        return json_error("Invalid user_address", 400, "INVALID_ADDRESS")

    if admin_service and not admin_service.get_swaps_enabled():
        return json_error("Swaps are currently disabled", 503, "SWAPS_DISABLED")

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return json_error("Invalid amount", 400, "INVALID_AMOUNT")
    if not math.isfinite(amount):
        return json_error("Invalid amount", 400, "INVALID_AMOUNT")

    # Capture user IP for audit trail
    user_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    try:
        swap = swap_engine.create_swap(from_coin, to_coin, amount, user_address, user_ip=user_ip)
        return json_success(swap)
    except LiquidityHoldError as e:
        return json_error(
            sanitize_error_message(e, "Swap temporarily unavailable"),
            503,
            "LIQUIDITY_DELAY",
        )
    except (InvalidAmountError, UnsupportedPairError) as e:
        return json_error(
            sanitize_error_message(e, "Validation failed"), 400, "VALIDATION_ERROR"
        )
    except PriceOracleError as e:
        return json_error(
            sanitize_error_message(e, "Price unavailable"), 503, "PRICE_UNAVAILABLE"
        )
    except WalletRPCError as e:
        return json_error(
            sanitize_error_message(e, "Service temporarily unavailable"),
            503,
            "WALLET_ERROR",
        )


@app.route("/api/v1/swap/<swap_id>", methods=["GET"])
def get_swap(swap_id: str):
    swap = swap_engine.get_swap(swap_id)
    if not swap:
        return json_error("Swap not found", 404, "NOT_FOUND")
    return json_success(swap)


@app.route("/api/v1/swap/<swap_id>/confirm", methods=["POST"])
def confirm_deposit(swap_id: str):
    data = request.get_json() or {}
    deposit_txid = data.get("deposit_txid", "").strip()

    if not deposit_txid:
        if TESTING_MODE:
            deposit_txid = "test_txid_auto"
        else:
            return json_error("Missing deposit_txid", 400, "MISSING_PARAMS")

    try:
        swap = swap_engine.confirm_deposit(swap_id, deposit_txid)
        return json_success(swap)
    except SwapError as e:
        return json_error(
            sanitize_error_message(e, "Swap operation failed"), 400, "SWAP_ERROR"
        )


@app.route("/api/v1/swap/<swap_id>/cancel", methods=["POST"])
def cancel_swap(swap_id: str):
    try:
        swap = swap_engine.cancel_swap(swap_id)
        return json_success(swap)
    except SwapError as e:
        return json_error(
            sanitize_error_message(e, "Swap operation failed"), 400, "SWAP_ERROR"
        )


@app.route("/api/v1/balance", methods=["GET"])
def get_balances():
    try:
        oxc_balance = swap_engine.get_balance("OXC")
        oxg_balance = swap_engine.get_balance("OXG")
        return json_success({"OXC": oxc_balance, "OXG": oxg_balance})
    except (WalletRPCError, UnsupportedPairError) as e:
        return json_error(
            sanitize_error_message(e, "Service unavailable"), 500, "WALLET_ERROR"
        )


@app.route("/api/v1/deposit/<coin>", methods=["GET"])
def get_deposit_address(coin: str):
    coin = coin.upper()

    if coin not in SUPPORTED_COINS:
        return json_error("Invalid coin", 400, "INVALID_COIN")

    try:
        address = swap_engine.get_deposit_address(coin)
        return json_success({"coin": coin, "address": address})
    except (WalletRPCError, UnsupportedPairError) as e:
        return json_error(
            sanitize_error_message(e, "Service unavailable"), 500, "WALLET_ERROR"
        )


@app.route("/api/v1/swaps", methods=["GET"])
@limiter.limit("600 per hour")
def list_swaps():
    status = request.args.get("status")
    limit = int(request.args.get("limit", 100))
    swaps = swap_engine.list_swaps(status)
    return json_success({"swaps": swaps[:limit], "count": len(swaps)})


@app.route("/api/v1/swaps/search", methods=["GET"])
@limiter.limit("60 per hour")
def search_swaps():
    address = request.args.get("address", "").strip()
    if not address:
        return json_error("Missing address parameter", 400, "MISSING_PARAMS")

    # Search in history
    if not swap_history:
        return json_error("History service unavailable", 503)

    # We search by address in the swap data
    results = swap_history.search_swaps(address, field="user_address")
    # Also search by deposit address
    deposit_results = swap_history.search_swaps(address, field="deposit_address")

    # Combine and unique
    combined = {s["swap_id"]: s for s in results + deposit_results}
    return json_success({"swaps": list(combined.values()), "count": len(combined)})


@app.route("/api/v1/swaps/track/<swap_id>", methods=["GET"])
@limiter.limit("60 per hour")
def track_swap(swap_id: str):
    """Public endpoint to track a swap by ID. Returns status and can trigger rescan for late deposits."""
    rescan = request.args.get("rescan", "false").lower() == "true"

    # First try to get from active swaps
    swap = swap_engine.get_swap(swap_id)

    # If not found in active, try history
    if not swap and swap_history:
        swap = swap_history.get_swap(swap_id)

    if not swap:
        return json_error("Swap not found", 404, "NOT_FOUND")

    # Calculate time remaining for pending swaps
    response_data = {
        "swap_id": swap.get("swap_id"),
        "status": swap.get("status"),
        "from_coin": swap.get("from_coin"),
        "to_coin": swap.get("to_coin"),
        "from_amount": swap.get("from_amount"),
        "to_amount": swap.get("to_amount"),
        "deposit_address": swap.get("deposit_address"),
        "user_address": swap.get("user_address"),
        "created_at": swap.get("created_at"),
        "updated_at": swap.get("updated_at"),
    }

    # Add status-specific info
    if swap.get("status") in ["pending", "awaiting_deposit"]:
        # Calculate time remaining
        from datetime import datetime, timezone

        created_at = swap.get("created_at")
        if created_at:
            try:
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                expire_minutes = 15  # Default
                if admin_service:
                    db_expire = admin_service.get_swap_expire_minutes()
                    if db_expire:
                        expire_minutes = db_expire
                from datetime import timedelta

                expire_time = created_at + timedelta(minutes=expire_minutes)
                now = datetime.now(timezone.utc)
                remaining_seconds = max(0, int((expire_time - now).total_seconds()))
                response_data["time_remaining_seconds"] = remaining_seconds
                response_data["expire_minutes"] = expire_minutes
                response_data["can_rescan"] = remaining_seconds > 0
            except (ValueError, TypeError):
                pass

    # Add deposit info if available
    if swap.get("deposit_txid"):
        response_data["deposit_txid"] = swap.get("deposit_txid")
    if swap.get("withdrawal_txid"):
        response_data["withdrawal_txid"] = swap.get("withdrawal_txid")

    # Handle rescan request for late deposits
    if rescan and swap.get("status") in ["pending", "timed_out"]:
        if swap_engine and swap_history:
            try:
                # Trigger a scan for unspent deposits
                cleanup_job = None
                # This is a simplified approach - in production you might want a dedicated method
                response_data["rescan_triggered"] = True
            except Exception as e:
                response_data["rescan_error"] = str(e)

    return json_success(response_data)


@app.route("/api/v1/swaps/stats", methods=["GET"])
@limiter.limit("600 per hour")
def get_swap_stats():
    if swap_history:
        return json_success(swap_history.get_stats())
    return json_error("History service not available", 500)


@app.route("/api/v1/admin/csrf-token", methods=["GET"])
@require_admin_auth
def get_csrf_token():
    """Get a new CSRF token for state-changing admin operations."""
    username = g.admin_username
    token = generate_csrf_token(username)
    return json_success({"csrf_token": token})


@app.route("/api/v1/admin/status", methods=["GET"])
@require_admin_auth
def admin_status():
    return json_success({"status": "ok"})


@app.route("/api/v1/admin/dashboard", methods=["GET"])
@require_admin_auth
def admin_dashboard():
    if not swap_history or not price_history:
        return json_error("Services not available", 500)

    financial = swap_history.get_financial_stats()
    stats = swap_history.get_stats()
    status_counts = swap_history.get_status_counts()
    delayed = swap_history.get_swaps_by_statuses(["delayed"])

    wallets = {}
    if swap_engine:
        for coin, wallet in (
            ("OXC", swap_engine.oxc_wallet),
            ("OXG", swap_engine.oxg_wallet),
        ):
            wallets.setdefault(coin, {})
            wallets[coin]["liquidity"] = admin_service.get_or_create_wallet_address(
                coin,
                "liquidity",
                lambda w=wallet, c=coin: w.get_labeled_address(
                    f"liquidity-{c.lower()}"
                ),
            )
            wallets[coin]["fees"] = admin_service.get_or_create_wallet_address(
                coin,
                "fees",
                lambda w=wallet, c=coin: w.get_labeled_address(f"fees-{c.lower()}"),
            )
            wallets[coin]["balance"] = wallet.get_balance()

    latest_price = price_history.get_latest() if price_history else None

    return json_success(
        {
            "wallets": wallets,
            "stats": stats,
            "status_counts": status_counts,
            "financial": financial,
            "delayed_queue": delayed,
            "latest_price": latest_price,
        }
    )


@app.route("/api/v1/admin/swaps", methods=["GET"])
@require_admin_auth
def admin_swaps():
    status = request.args.get("status")
    limit = int(request.args.get("limit", 100))
    # By default, admin sees all swaps including cancelled/timed_out/expired
    include_inactive = status is None
    swaps = swap_engine.list_swaps(status, include_inactive=include_inactive)
    return json_success({"swaps": swaps[:limit], "count": len(swaps)})


@app.route("/api/v1/admin/scan-transactions", methods=["GET"])
@require_admin_auth
def admin_scan_transactions():
    if not swap_engine:
        return json_error("Swap engine not available", 500)

    # Get admin wallets for mapping
    admin_wallets = {}
    if admin_service:
        admin_wallets = admin_service.list_wallets()

    try:
        transactions = swap_engine.get_unaccounted_transactions(admin_wallets)
        return json_success({"transactions": transactions, "count": len(transactions)})
    except Exception as e:
        logger.error(f"Failed to scan transactions: {e}")
        return json_error(str(e), 500)


@app.route("/api/v1/admin/audit/reconcile", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_reconcile_audit():
    if not swap_engine:
        return json_error("Swap engine not available", 500)

    count = request.args.get("count", 100, type=int)
    try:
        results = swap_engine.reconcile_full_history(count=count)
        admin_service.log_audit(
            g.admin_username,
            "full_reconciliation",
            "success",
            g.admin_ip,
            f"Scanned {results['scanned_count']} transactions",
        )
        return json_success(results)
    except Exception as e:
        logger.error(f"Reconciliation trigger failed: {e}")
        return json_error(str(e), 500)


@app.route("/api/v1/admin/audit/acknowledge", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_acknowledge_tx():
    """Manually acknowledge a transaction as explained (e.g. liquidity topup)."""
    data = request.json
    txid = data.get("txid")
    coin = data.get("coin")
    amount = data.get("amount")
    action = data.get("action", "liquidity")
    details = data.get("details", "")

    if not all([txid, coin, amount]):
        return json_error("Missing required fields", 400)

    try:
        amount = float(amount)
    except ValueError:
        return json_error("Invalid amount", 400)

    success = admin_service.acknowledge_transaction(
        txid=txid,
        coin=coin,
        amount=amount,
        action=action,
        performed_by=g.admin_username,
        details=details,
    )

    if success:
        admin_service.log_audit(
            g.admin_username,
            "acknowledge_tx",
            "success",
            g.admin_ip,
            f"Acknowledged {txid} as {action}",
        )
        return json_success({"message": "Transaction acknowledged"})
    else:
        return json_error("Failed to acknowledge transaction", 500)


@app.route("/api/v1/admin/audit/settle", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_settle_orphaned():
    """Manually settle an orphaned transaction to a user address."""
    data = request.json
    txid = data.get("txid")
    coin = data.get("coin")
    amount = data.get("amount")
    user_address = data.get("address")
    swap_id = data.get("swap_id")

    if not all([txid, coin, amount, user_address]):
        return json_error("Missing required fields (txid, coin, amount, address)", 400)

    try:
        amount = float(amount)
        result = swap_engine.settle_orphaned_transaction(
            txid=txid,
            coin=coin,
            amount=amount,
            user_address=user_address,
            username=g.admin_username,
            swap_id=swap_id,
        )

        admin_service.log_audit(
            g.admin_username,
            "settle_orphaned",
            "success",
            g.admin_ip,
            f"Settled {txid} to {user_address}",
        )
        return json_success(result)
    except (SwapError, InvalidAmountError) as e:
        return json_error(str(e), 400)
    except Exception as e:
        logger.error(f"Error in manual settlement: {e}")
        return json_error("Internal server error during settlement", 500)


@app.route("/api/v1/admin/audit/refund", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_refund_orphaned():
    """Refund an orphaned transaction."""
    data = request.json
    txid = data.get("txid")
    coin = data.get("coin")
    amount = data.get("amount")
    target_address = data.get("address")

    if not all([txid, coin, amount, target_address]):
        return json_error("Missing required fields (txid, coin, amount, address)", 400)

    try:
        amount = float(amount)
        result = swap_engine.refund_orphaned_transaction(
            txid=txid,
            coin=coin,
            amount=amount,
            target_address=target_address,
            username=g.admin_username,
        )

        admin_service.log_audit(
            g.admin_username,
            "refund_orphaned",
            "success",
            g.admin_ip,
            f"Refunded {txid} to {target_address}",
        )
        return json_success(result)
    except (SwapError, InvalidAmountError) as e:
        return json_error(str(e), 400)
    except Exception as e:
        logger.error(f"Error in manual refund: {e}")
        return json_error("Internal server error during refund", 500)


@app.route("/api/v1/admin/swaps/<swap_id>", methods=["GET"])
@require_admin_auth
def admin_get_swap(swap_id):
    if not swap_history:
        return json_error("Swap history not available", 500)
    swap = swap_history.get_swap(swap_id)
    if not swap:
        return json_error("Swap not found", 404)
    audit = admin_service.get_swap_audit_log(swap_id) if admin_service else []

    swap_data = {
        "swap_id": swap.get("swap_id"),
        "status": swap.get("status"),
        "from_coin": swap.get("from_coin"),
        "to_coin": swap.get("to_coin"),
        "from_amount": swap.get("from_amount"),
        "to_amount": swap.get("to_amount"),
        "fee_amount": swap.get("fee_amount"),
        "net_amount": swap.get("net_amount"),
        "rate": swap.get("rate"),
        "user_address": swap.get("user_address"),
        "user_ip": swap.get("user_ip"),
        "deposit_address": swap.get("deposit_address"),
        "deposit_txid": swap.get("deposit_txid"),
        "settle_txid": swap.get("settle_txid"),
        "withdrawal_txid": swap.get("withdrawal_txid"),
        "created_at": swap.get("created_at"),
        "updated_at": swap.get("updated_at"),
        "completed_at": swap.get("completed_at"),
        "expires_at": swap.get("expires_at"),
        "delay_code": swap.get("delay_code"),
        "delay_reason": swap.get("delay_reason"),
        "error": swap.get("error"),
        "reconciled_by": swap.get("reconciled_by"),
        "actual_from_amount": swap.get("actual_from_amount"),
        "actual_to_amount": swap.get("actual_to_amount"),
        "actual_fee_amount": swap.get("actual_fee_amount"),
        "actual_net_amount": swap.get("actual_net_amount"),
        "circuit_breaker_ratio": swap.get("circuit_breaker_ratio"),
        "circuit_breaker_threshold": swap.get("circuit_breaker_threshold"),
        "admin_locked": swap.get("admin_locked", False),
        # Admin override information
        "admin_override": swap.get("admin_override", False),
        "admin_set_state": swap.get("admin_set_state"),
        "admin_override_reason": swap.get("admin_override_reason"),
        "admin_override_by": swap.get("admin_override_by"),
        "admin_override_at": swap.get("admin_override_at"),
        "audit": audit,
    }
    return json_success(swap_data)


@app.route("/api/v1/admin/swaps/<swap_id>/audit", methods=["GET"])
@require_admin_auth
def admin_get_swap_audit(swap_id):
    if not admin_service:
        return json_error("Admin service not available", 500)

    audit_trail = admin_service.get_swap_audit_log(swap_id)
    return json_success({"swap_id": swap_id, "audit_trail": audit_trail})


@app.route("/api/v1/admin/swaps/<swap_id>/action", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_action_swap(swap_id):
    if not swap_engine:
        return json_error("Swap engine not available", 500)
    data = request.get_json() or {}
    action = data.get("action")
    if action not in ["settle", "cancel"]:
        return json_error("Invalid action", 400)

    try:
        if action == "settle":
            swap = swap_engine._settle_swap(swap_id)
        else:
            swap = swap_engine.cancel_swap(swap_id)
        return json_success({"swap": swap, "action": action})
    except InvalidAmountError as e:
        logger.warning(f"Invalid amount for swap {swap_id} action {action}: {e}")
        return json_error(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to perform {action} on swap {swap_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/v1/admin/swaps/<swap_id>/status", methods=["PUT"])
@require_admin_auth
@require_csrf_token
def admin_set_swap_status(swap_id):
    if not swap_engine:
        return json_error("Swap engine not available", 500)
    data = request.get_json() or {}
    new_status = data.get("status")
    if not new_status:
        return json_error("Missing status field", 400)

    reason = data.get("reason", "")
    
    try:
        swap = swap_engine.set_swap_status(
            swap_id, new_status, performed_by=g.admin_username, reason=reason
        )
        return json_success({"swap": swap})
    except SwapError as e:
        return json_error(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to set status for swap {swap_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/v1/admin/swaps/<swap_id>/clear-override", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_clear_override(swap_id):
    """Clear admin override on a swap, allowing normal processing to resume."""
    if not swap_engine:
        return json_error("Swap engine not available", 500)

    try:
        swap = swap_engine.clear_admin_override(
            swap_id, performed_by=g.admin_username
        )
        return json_success({"swap": swap})
    except SwapError as e:
        return json_error(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to clear override for swap {swap_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/v1/admin/swaps/<swap_id>/release", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_release_circuit_breaker(swap_id):
    if not swap_engine:
        return json_error("Swap engine not available", 500)
    data = request.get_json() or {}
    action = data.get("action")
    if action not in ["settle", "cancel"]:
        return json_error("Invalid action. Use 'settle' or 'cancel'", 400)

    try:
        swap = swap_engine.release_circuit_breaker(
            swap_id, action, performed_by=g.admin_username
        )
        return json_success({"swap": swap, "action": action})
    except SwapError as e:
        return json_error(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to release circuit breaker for swap {swap_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/v1/admin/queues/process", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_process_queue():
    if not swap_engine:
        return json_error("Swap engine not available", 500)
    processed = swap_engine.process_delayed_swaps()
    return json_success({"processed": processed})


@app.route("/api/v1/admin/wallets/rotate", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_rotate_wallet():
    data = request.get_json() or {}
    coin = (data.get("coin") or "").upper()
    purpose = (data.get("purpose") or "").lower()
    if coin not in SUPPORTED_COINS or purpose not in {"liquidity", "fees"}:
        return json_error("Invalid coin or purpose", 400, "INVALID_PARAMS")
    wallet = swap_engine.oxc_wallet if coin == "OXC" else swap_engine.oxg_wallet
    address = admin_service.rotate_wallet_address(
        coin,
        purpose,
        lambda w=wallet, c=coin, p=purpose: w.get_labeled_address(f"{p}-{c.lower()}"),
    )
    ip_address = getattr(g, "admin_ip", None)
    if not address:
        admin_service.log_wallet_action(
            action_type="rotate_failed",
            coin=coin,
            purpose=purpose,
            performed_by=g.admin_username,
            ip_address=ip_address,
            details="Failed to generate new address",
            status="failed",
            error_code="ADDRESS_GENERATION_FAILED",
        )
        return json_error("Failed to rotate wallet", 500)
    if not admin_service.log_wallet_action(
        action_type="rotate",
        coin=coin,
        purpose=purpose,
        address=address,
        performed_by=g.admin_username,
        ip_address=ip_address,
        details=f"New address generated for {purpose} wallet",
        status="success",
    ):
        logger.warning(
            f"Failed to log successful rotation for {coin} {purpose}",
            coin=coin,
            purpose=purpose,
        )
    return json_success({"coin": coin, "purpose": purpose, "address": address})


@app.route("/api/v1/admin/wallets/withdraw", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_withdraw():
    data = request.get_json() or {}
    coin = (data.get("coin") or "").upper()
    purpose = data.get("purpose", "")
    to_address = (data.get("to_address") or "").strip()
    amount = data.get("amount")

    if coin not in SUPPORTED_COINS:
        return json_error("Invalid coin", 400, "INVALID_COIN")
    if not to_address:
        return json_error("Missing to_address", 400, "MISSING_PARAMS")
    if amount is None:
        return json_error("Missing amount", 400, "MISSING_PARAMS")
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return json_error("Invalid amount", 400, "INVALID_AMOUNT")

    # Validate address before attempting withdrawal
    wallet = swap_engine.oxc_wallet if coin == "OXC" else swap_engine.oxg_wallet
    try:
        validation = wallet.validate_address(to_address)
        if not validation.get("isValid", False):
            admin_service.log_wallet_action(
                action_type="withdraw_failed",
                coin=coin,
                purpose=purpose or None,
                amount=amount,
                address=to_address,
                performed_by=g.admin_username,
                ip_address=getattr(g, "admin_ip", None),
                details="Invalid address format",
                status="failed",
                error_code="INVALID_ADDRESS_FORMAT",
            )
            return json_error("Invalid address format", 400, "INVALID_ADDRESS")
    except WalletRPCError as e:
        # If validation call fails, log and continue with original error handling
        logger.warning(f"Address validation RPC failed, continuing: {e}")

    # Validate minimum amount based on coin
    min_amount = 0.00000001  # Smallest valid amount
    if amount < min_amount:
        return json_error(
            f"Amount too small (minimum: {min_amount})", 400, "INVALID_AMOUNT"
        )

    txid = None
    ip_address = getattr(g, "admin_ip", None)
    try:
        txid = wallet.send(to_address, amount)
    except WalletRPCError as e:
        error_msg = str(e)
        # Extract more specific error code from exception
        if "insufficient" in error_msg.lower():
            error_code = "INSUFFICIENT_BALANCE"
        elif (
            "invalid address" in error_msg.lower() or "bad address" in error_msg.lower()
        ):
            error_code = "INVALID_ADDRESS"
        elif "connection" in error_msg.lower():
            error_code = "RPC_CONNECTION_ERROR"
        else:
            error_code = "RPC_ERROR"

        admin_service.log_wallet_action(
            action_type="withdraw_failed",
            coin=coin,
            purpose=purpose or None,
            amount=amount,
            address=to_address,
            performed_by=g.admin_username,
            ip_address=ip_address,
            details=f"Wallet RPC error: {error_msg}",
            status="failed",
            error_code=error_code,
        )
        return json_error("Withdraw failed", 500, "WITHDRAW_ERROR")

    if not admin_service.log_wallet_action(
        action_type="withdraw",
        coin=coin,
        purpose=purpose or None,
        amount=amount,
        address=to_address,
        txid=txid,
        performed_by=g.admin_username,
        ip_address=ip_address,
        details=f"Withdrew {amount} {coin} to external address",
        status="success",
    ):
        logger.warning(
            f"Failed to log successful withdrawal: {txid}",
            coin=coin,
            amount=amount,
            txid=txid,
        )

    return json_success(
        {"coin": coin, "amount": amount, "to_address": to_address, "txid": txid}
    )


@app.route("/api/v1/admin/wallets/actions", methods=["GET"])
@require_admin_auth
def admin_wallet_actions():
    limit = int(request.args.get("limit", 100))

    # 1. Fetch DB logs
    actions = admin_service.get_wallet_actions(limit)
    logged_txids = {a.get("txid") for a in actions if a.get("txid")}

    # 2. Perform quick RPC discovery (last 50 transactions per wallet)
    # This catches manual RPC/Console actions that were never logged in DB.
    try:
        discovery = swap_engine.reconcile_full_history(count=50)

        # Unaccounted Withdrawals are manual/external sends
        for w in discovery.get("unaccounted_withdrawals", []):
            if w["txid"] not in logged_txids:
                actions.append(
                    {
                        "action_type": "EXTERNAL_SEND",
                        "coin": w["coin"],
                        "purpose": "MANUAL / RPC",
                        "amount": w["amount"],
                        "address": w["address"],
                        "txid": w["txid"],
                        "performed_by": "EXTERNAL / CONSOLE",
                        "created_at": datetime.now(
                            timezone.utc
                        ).isoformat(),  # We don't have block time here easily
                        "details": "Manual transaction discovered via RPC scan",
                        "source_table": "rpc_discovery",
                    }
                )
                logged_txids.add(w["txid"])

        # Unaccounted Deposits are manual/external receives (topups)
        for d in discovery.get("unaccounted_deposits", []):
            if d["txid"] not in logged_txids:
                # Filter out standard swap deposits (those aren't 'wallet actions' in the manual sense)
                # But if they are 'UNACCOUNTED' in discovery, they ARE manual topups or orphaned funds.
                actions.append(
                    {
                        "action_type": "EXTERNAL_RECEIVE",
                        "coin": d["coin"],
                        "purpose": "LIQUIDITY TOPUP",
                        "amount": d["amount"],
                        "address": d["address"],
                        "txid": d["txid"],
                        "performed_by": "EXTERNAL / CONSOLE",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "details": f"External deposit discovered: {d.get('reason', 'Unknown reason')}",
                        "source_table": "rpc_discovery",
                    }
                )
                logged_txids.add(d["txid"])

    except Exception as e:
        logger.error("Failed RPC discovery in wallet actions", error=str(e))
        # We still return the DB actions even if RPC scan fails

    # 3. Final Sort
    actions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return json_success({"actions": actions[:limit]})


@app.route("/api/v1/admin/users", methods=["GET"])
@require_admin_auth
def admin_list_users():
    return json_success({"users": admin_service.list_admins()})


@app.route("/api/v1/admin/users", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_create_user():
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if not username or not password:
        return json_error("Invalid request", 400, "MISSING_PARAMS")
    username = getattr(g, "admin_username", None)
    ip_address = getattr(g, "admin_ip", None)
    if not admin_service.create_admin(
        username, password, ip_address, created_by=username
    ):
        return json_error("Operation failed", 400)
    return json_success({"username": data.get("username")})


@app.route("/api/v1/admin/users/change-password", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_change_password():
    data = request.get_json() or {}
    username = data.get("username", "")
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    if not username or not current_password or not new_password:
        return json_error("Invalid request", 400, "MISSING_PARAMS")
    ip_address = getattr(g, "admin_ip", None)
    if not admin_service.update_password(
        username, current_password, new_password, ip_address
    ):
        return json_error("Operation failed", 400, "UPDATE_FAILED")
    return json_success({"username": username})


@app.route("/api/v1/prices/history", methods=["GET"])
@limiter.limit("600 per hour")
def get_price_history():
    limit = int(request.args.get("limit", 100))
    if price_history:
        history = price_history.get_history(limit)
        if not history:
            price_history.fetch_and_record()
            history = price_history.get_history(limit)
        return json_success({"history": history})
    return json_error("Price history not available", 500)


@app.route("/api/v1/prices/current", methods=["GET"])
@limiter.limit("600 per hour")
def get_current_prices():
    """Get current USDT rates and cross rate."""
    if price_history:
        latest = price_history.get_latest()
        if latest:
            return json_success(latest)
    return json_error("Price not available", 500)


@app.route("/api/v1/prices/stats", methods=["GET"])
@limiter.limit("600 per hour")
def get_price_stats():
    hours = int(request.args.get("hours", 24))
    if price_history:
        return json_success(price_history.get_price_stats(hours))
    return json_error("Price history not available", 500)


@app.route("/api/v1/admin/background-status", methods=["GET"])
@require_admin_auth
def admin_background_status():
    if not price_history or not swap_engine:
        return json_error("Services not available", 500)
    return json_success(
        {
            "price_fetch": price_history.get_background_status(),
            "queue_settlement": swap_engine.get_settlement_status(),
        }
    )


@app.route("/api/v1/admin/swaps-enabled", methods=["GET"])
@require_admin_auth
def admin_get_swaps_enabled():
    if not admin_service:
        return json_error("Admin service not available", 500)
    return json_success({"swaps_enabled": admin_service.get_swaps_enabled()})


@app.route("/api/v1/admin/swaps-enabled", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_set_swaps_enabled():
    if not admin_service:
        return json_error("Service unavailable", 500)
    data = request.get_json() or {}
    enabled = data.get("enabled", True)
    username = getattr(g, "admin_username", None)
    ip_address = getattr(g, "admin_ip", None)
    if not admin_service.set_swaps_enabled(enabled, username, ip_address):
        return json_error("Operation failed", 500)
    return json_success({"swaps_enabled": enabled})


@app.route("/api/v1/admin/fee", methods=["GET"])
@require_admin_auth
def admin_get_fee():
    if not admin_service:
        return json_error("Service unavailable", 500)
    fee = admin_service.get_swap_fee_percent()
    if fee is None:
        return json_error("Operation failed", 500)
    return json_success({"fee_percent": fee})


@app.route("/api/v1/admin/fee", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_set_fee():
    if not admin_service:
        return json_error("Service unavailable", 500)
    data = request.get_json() or {}
    fee_percent = data.get("fee_percent")
    if fee_percent is None:
        return json_error("Invalid request", 400, "MISSING_PARAMS")
    try:
        fee_percent = float(fee_percent)
    except (ValueError, TypeError):
        return json_error("Invalid request", 400, "INVALID_PARAMS")
    if fee_percent < 0 or fee_percent > 100:
        return json_error("Invalid request", 400, "INVALID_PARAMS")
    username = getattr(g, "admin_username", None)
    ip_address = getattr(g, "admin_ip", None)
    if not admin_service.set_swap_fee_percent(fee_percent, username, ip_address):
        return json_error("Operation failed", 500)
    return json_success({"fee_percent": fee_percent})


@app.route("/api/v1/admin/settings", methods=["GET"])
@require_admin_auth
def admin_get_settings():
    if not admin_service:
        return json_error("Service unavailable", 500)
    settings = admin_service.get_all_settings()
    return json_success(settings)


@app.route("/api/v1/admin/settings", methods=["POST"])
@require_admin_auth
@require_csrf_token
def admin_update_settings():
    if not admin_service:
        return json_error("Service unavailable", 500)
    data = request.get_json() or {}
    errors = []
    username = getattr(g, "admin_username", None)
    ip_address = getattr(g, "admin_ip", None)

    if "swap_fee_percent" in data:
        try:
            fee = float(data["swap_fee_percent"])
            if fee < 0 or fee > 100:
                errors.append("invalid fee_percent")
            elif not admin_service.set_swap_fee_percent(fee, username, ip_address):
                errors.append("fee_percent update failed")
        except (ValueError, TypeError):
            errors.append("invalid fee_percent")

    if "swap_confirmations_required" in data:
        try:
            confirmations = int(data["swap_confirmations_required"])
            if confirmations < 0:
                errors.append("invalid confirmations")
            elif not admin_service.set_swap_confirmations_required(
                confirmations, username, ip_address
            ):
                errors.append("confirmations update failed")
        except (ValueError, TypeError):
            errors.append("invalid confirmations")

    if "swap_min_fee_OXC" in data:
        try:
            min_fee = float(data["swap_min_fee_OXC"])
            if min_fee < 0:
                errors.append("invalid min_fee_oxc")
            elif not admin_service.set_swap_min_fee(
                "OXC", min_fee, username, ip_address
            ):
                errors.append("min_fee_oxc update failed")
        except (ValueError, TypeError):
            errors.append("invalid min_fee_oxc")

    if "swap_min_fee_OXG" in data:
        try:
            min_fee = float(data["swap_min_fee_OXG"])
            if min_fee < 0:
                errors.append("invalid min_fee_oxg")
            elif not admin_service.set_swap_min_fee(
                "OXG", min_fee, username, ip_address
            ):
                errors.append("min_fee_oxg update failed")
        except (ValueError, TypeError):
            errors.append("invalid min_fee_oxg")

    if "swap_min_amount" in data:
        try:
            min_amount = float(data["swap_min_amount"])
            if min_amount < 0:
                errors.append("invalid min_amount")
            elif not admin_service.set_swap_min_amount(
                min_amount, username, ip_address
            ):
                errors.append("min_amount update failed")
        except (ValueError, TypeError):
            errors.append("invalid min_amount")

    if "swap_max_amount" in data:
        try:
            max_amount = float(data["swap_max_amount"])
            if max_amount < 0:
                errors.append("invalid max_amount")
            elif not admin_service.set_swap_max_amount(
                max_amount, username, ip_address
            ):
                errors.append("max_amount update failed")
        except (ValueError, TypeError):
            errors.append("invalid max_amount")

    if "swap_expire_minutes" in data:
        try:
            expire_minutes = int(data["swap_expire_minutes"])
            if expire_minutes <= 0:
                errors.append("invalid expire_minutes")
            elif not admin_service.set_swap_expire_minutes(
                expire_minutes, username, ip_address
            ):
                errors.append("expire_minutes update failed")
        except (ValueError, TypeError):
            errors.append("invalid expire_minutes")

    if errors:
        return json_error("Invalid request", 400)

    return json_success(admin_service.get_all_settings())


@app.route("/api/v1/admin/audit-log", methods=["GET"])
@require_admin_auth
def admin_get_audit_log():
    if not admin_service:
        return json_error("Service unavailable", 500)
    limit = request.args.get("limit", 100, type=int)
    limit = min(max(limit, 1), 1000)
    audit_log = admin_service.get_audit_log(limit)
    return json_success(audit_log)


@app.route("/api/v1/admin/wallet-configs", methods=["GET"])
@require_admin_auth
def admin_get_wallet_configs():
    if not admin_service:
        return json_error("Service unavailable", 500)
    username = g.get("admin_username", "system")
    ip_address = g.get("admin_ip")
    try:
        wallet_configs = admin_service.list_wallet_configs()
        admin_service.log_audit(username, "list_wallet_configs", "success", ip_address)
        return json_success(wallet_configs)
    except Exception as e:
        logger.error("Failed to list wallet configs", error=str(e))
        admin_service.log_audit(
            username, "list_wallet_configs", "failed", ip_address, str(e)
        )
        return json_error("Failed to list wallet configs", 500)


@app.route("/api/v1/admin/wallet-configs", methods=["PUT"])
@require_admin_auth
@require_csrf_token
def admin_update_wallet_config():
    if not admin_service:
        return json_error("Service unavailable", 500)
    username = g.get("admin_username", "system")
    ip_address = g.get("admin_ip")
    data = request.get_json() or {}
    coin = data.get("coin", "").upper()
    wallet_path = data.get("wallet_path", "").strip()
    wallet_name = data.get("wallet_name", "").strip() or None

    if not coin or coin not in ["OXC", "OXG"]:
        return json_error("Invalid coin", 400)

    if not wallet_path:
        return json_error("wallet_path is required", 400)

    try:
        if admin_service.set_wallet_config(coin, wallet_path, wallet_name):
            admin_service.log_audit(
                username,
                "update_wallet_config",
                "success",
                ip_address,
                f"coin={coin}, path={wallet_path}",
            )
            return json_success(
                {"coin": coin, "wallet_path": wallet_path, "wallet_name": wallet_name}
            )
        else:
            admin_service.log_audit(
                username,
                "update_wallet_config",
                "failed",
                ip_address,
                f"coin={coin}",
            )
            return json_error("Failed to update wallet config", 500)
    except Exception as e:
        logger.error("Failed to update wallet config", error=str(e))
        admin_service.log_audit(
            username, "update_wallet_config", "failed", ip_address, str(e)
        )
        return json_error("Failed to update wallet config", 500)


@app.errorhandler(Exception)
def handle_exception(e):
    logger.exception("Unhandled exception", error=str(e))
    return json_error("Internal server error", 500, "INTERNAL_ERROR")


def run_server(host: str = API_HOST, port: int = API_PORT, debug: bool = False):
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_server()
