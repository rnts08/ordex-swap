import logging
from flask import Flask, request, jsonify

from price_oracle import PriceOracle, PriceOracleError, PriceOracleStaleError
from wallet_rpc import WalletRPCError
from swap_engine import (
    SwapEngine,
    SwapError,
    InvalidAmountError,
    UnsupportedPairError,
)
from swap_history import SwapHistoryService
from price_history import PriceHistoryService
from config import (
    API_HOST,
    API_PORT,
    SUPPORTED_COINS,
    TESTING_MODE,
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

swap_engine: SwapEngine = None
price_oracle: PriceOracle = None
price_history: PriceHistoryService = None
swap_history: SwapHistoryService = None


def init_app(
    engine: SwapEngine,
    oracle: PriceOracle,
    price_hist: PriceHistoryService = None,
    swap_hist: SwapHistoryService = None,
):
    global swap_engine, price_oracle, price_history, swap_history
    swap_engine = engine
    price_oracle = oracle
    price_history = price_hist
    swap_history = swap_hist


def json_error(message: str, status_code: int, error_code: str = None):
    response = {"error": message, "success": False}
    if error_code:
        response["error_code"] = error_code
    return jsonify(response), status_code


def json_success(data):
    response = {"success": True, "data": data}
    return jsonify(response)


@app.route("/health", methods=["GET"])
def health_check():
    return json_success(
        {"status": "healthy", "service": "ordex-swap", "testing_mode": TESTING_MODE}
    )


@app.route("/api/v1/status", methods=["GET"])
def get_status():
    return json_success(
        {
            "testing_mode": TESTING_MODE,
            "supported_coins": SUPPORTED_COINS,
        }
    )


@app.route("/api/v1/quote", methods=["POST"])
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

    try:
        quote = swap_engine.create_swap_quote(from_coin, to_coin, amount)
        return json_success(quote)
    except (InvalidAmountError, UnsupportedPairError) as e:
        return json_error(str(e), 400, "VALIDATION_ERROR")
    except PriceOracleError as e:
        return json_error(str(e), 503, "PRICE_UNAVAILABLE")


@app.route("/api/v1/swap", methods=["POST"])
def create_swap():
    data = request.get_json() or {}

    from_coin = data.get("from", "").upper()
    to_coin = data.get("to", "").upper()
    amount = data.get("amount")
    user_address = data.get("user_address", "").strip()

    if not from_coin or not to_coin or amount is None or not user_address:
        return json_error("Missing required fields", 400, "MISSING_PARAMS")

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return json_error("Invalid amount", 400, "INVALID_AMOUNT")

    try:
        swap = swap_engine.create_swap(from_coin, to_coin, amount, user_address)
        return json_success(swap)
    except (InvalidAmountError, UnsupportedPairError) as e:
        return json_error(str(e), 400, "VALIDATION_ERROR")
    except PriceOracleError as e:
        return json_error(str(e), 503, "PRICE_UNAVAILABLE")
    except WalletRPCError as e:
        return json_error(str(e), 503, "WALLET_ERROR")


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
        return json_error("Missing deposit_txid", 400, "MISSING_PARAMS")

    try:
        swap = swap_engine.confirm_deposit(swap_id, deposit_txid)
        return json_success(swap)
    except SwapError as e:
        return json_error(str(e), 400, "SWAP_ERROR")


@app.route("/api/v1/swap/<swap_id>/cancel", methods=["POST"])
def cancel_swap(swap_id: str):
    try:
        swap = swap_engine.cancel_swap(swap_id)
        return json_success(swap)
    except SwapError as e:
        return json_error(str(e), 400, "SWAP_ERROR")


@app.route("/api/v1/balance", methods=["GET"])
def get_balances():
    try:
        oxc_balance = swap_engine.get_balance("OXC")
        oxg_balance = swap_engine.get_balance("OXG")
        return json_success({"OXC": oxc_balance, "OXG": oxg_balance})
    except (WalletRPCError, UnsupportedPairError) as e:
        return json_error(str(e), 500, "WALLET_ERROR")


@app.route("/api/v1/deposit/<coin>", methods=["GET"])
def get_deposit_address(coin: str):
    coin = coin.upper()

    if coin not in SUPPORTED_COINS:
        return json_error(f"Unsupported coin: {coin}", 400, "INVALID_COIN")

    try:
        address = swap_engine.get_deposit_address(coin)
        return json_success({"coin": coin, "address": address})
    except (WalletRPCError, UnsupportedPairError) as e:
        return json_error(str(e), 500, "WALLET_ERROR")


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


@app.route("/api/v1/prices/history", methods=["GET"])
def get_price_history():
    limit = int(request.args.get("limit", 100))
    if price_history:
        return json_success({"history": price_history.get_history(limit)})
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


@app.errorhandler(Exception)
def handle_exception(e):
    logger.exception(f"Unhandled exception: {e}")
    return json_error("Internal server error", 500, "INTERNAL_ERROR")


def run_server(host: str = API_HOST, port: int = API_PORT, debug: bool = False):
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_server()
