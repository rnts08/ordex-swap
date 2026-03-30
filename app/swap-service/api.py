import logging
import math
import re
import base64
from functools import wraps
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
    SWAP_FEE_PERCENT,
    SWAP_CONFIRMATIONS_REQUIRED,
    SWAP_MIN_FEE_OXC,
    SWAP_MIN_FEE_OXG,
    SWAP_MIN_AMOUNT,
    SWAP_MAX_AMOUNT,
)

logger = StructuredLogger(__name__)

app = Flask(__name__)

limiter = Limiter(
    app=app,
    key_func=lambda: request.headers.get("X-Forwarded-For", request.remote_addr),
    storage_uri="memory://",
    default_limits=["200 per day", "50 per hour"],
    enabled=not TESTING_MODE,
)

swap_engine: SwapEngine = None
price_oracle: PriceOracle = None
price_history: PriceHistoryService = None
swap_history: SwapHistoryService = None
admin_service: AdminService = None


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


def sanitize_error_message(error: Exception, default_message: str) -> str:
    error_msg = str(error)
    if not error_msg or len(error_msg) > 100:
        return default_message
    safe_patterns = [
        "invalid",
        "missing",
        "required",
        "cannot",
        "must be",
        "failed",
        "error",
    ]
    if any(p in error_msg.lower() for p in safe_patterns):
        return error_msg[:100]
    return default_message


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


@app.route("/health", methods=["GET"])
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

    try:
        swap = swap_engine.create_swap(from_coin, to_coin, amount, user_address)
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
def list_swaps():
    status = request.args.get("status")
    limit = int(request.args.get("limit", 100))
    swaps = swap_engine.list_swaps(status)
    return json_success({"swaps": swaps[:limit], "count": len(swaps)})


@app.route("/api/v1/swaps/stats", methods=["GET"])
def get_swap_stats():
    if swap_history:
        return json_success(swap_history.get_stats())
    return json_error("History service not available", 500)


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
    swaps = swap_engine.list_swaps(status)
    return json_success({"swaps": swaps[:limit], "count": len(swaps)})


@app.route("/api/v1/admin/queues/process", methods=["POST"])
@require_admin_auth
def admin_process_queue():
    if not swap_engine:
        return json_error("Swap engine not available", 500)
    processed = swap_engine.process_delayed_swaps()
    return json_success({"processed": processed})


@app.route("/api/v1/admin/wallets/rotate", methods=["POST"])
@require_admin_auth
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
        )
        return json_error("Failed to rotate wallet", 500)
    admin_service.log_wallet_action(
        action_type="rotate",
        coin=coin,
        purpose=purpose,
        address=address,
        performed_by=g.admin_username,
        ip_address=ip_address,
        details=f"New address generated for {purpose} wallet",
    )
    return json_success({"coin": coin, "purpose": purpose, "address": address})


@app.route("/api/v1/admin/wallets/withdraw", methods=["POST"])
@require_admin_auth
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

    wallet = swap_engine.oxc_wallet if coin == "OXC" else swap_engine.oxg_wallet
    txid = None
    ip_address = getattr(g, "admin_ip", None)
    try:
        txid = wallet.send(to_address, amount)
    except WalletRPCError as e:
        admin_service.log_wallet_action(
            action_type="withdraw_failed",
            coin=coin,
            purpose=purpose or None,
            amount=amount,
            address=to_address,
            performed_by=g.admin_username,
            ip_address=ip_address,
            details="Wallet RPC error during withdrawal",
        )
        return json_error("Withdraw failed", 500, "WITHDRAW_ERROR")

    admin_service.log_wallet_action(
        action_type="withdraw",
        coin=coin,
        purpose=purpose or None,
        amount=amount,
        address=to_address,
        txid=txid,
        performed_by=g.admin_username,
        ip_address=ip_address,
        details=f"Withdrew {amount} {coin} to external address",
    )

    return json_success(
        {"coin": coin, "amount": amount, "to_address": to_address, "txid": txid}
    )


@app.route("/api/v1/admin/wallets/actions", methods=["GET"])
@require_admin_auth
def admin_wallet_actions():
    limit = int(request.args.get("limit", 100))
    actions = admin_service.get_wallet_actions(limit)
    return json_success({"actions": actions})


@app.route("/api/v1/admin/users", methods=["GET"])
@require_admin_auth
def admin_list_users():
    return json_success({"users": admin_service.list_admins()})


@app.route("/api/v1/admin/users", methods=["POST"])
@require_admin_auth
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
def get_current_prices():
    """Get current USDT rates and cross rate."""
    if price_history:
        latest = price_history.get_latest()
        if latest:
            return json_success(latest)
    return json_error("Price not available", 500)


@app.route("/api/v1/prices/stats", methods=["GET"])
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


@app.errorhandler(Exception)
def handle_exception(e):
    logger.exception("Unhandled exception", error=str(e))
    return json_error("Internal server error", 500, "INTERNAL_ERROR")


def run_server(host: str = API_HOST, port: int = API_PORT, debug: bool = False):
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_server()
