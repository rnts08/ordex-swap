import hashlib
import hmac
import json
import time
import logging
import sqlite3
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import requests

from config import (
    NESTEX_BASE_URL,
    NESTEX_API_KEY,
    NESTEX_API_SECRET,
    NESTEX_MIN_GAP_SECONDS,
    NESTEX_PRICE_TTL_SECONDS,
    NESTEX_MAX_PRICE_AGE_SECONDS,
    OXC_USDT_FALLBACK_PRICE,
    OXG_USDT_FALLBACK_PRICE,
    OXC_OXG_FALLBACK_PRICE,
    TESTING_MODE,
    DB_PATH,
)

logger = logging.getLogger(__name__)


class PriceOracleError(Exception):
    """Base exception for price oracle errors."""

    pass


class PriceOracleAPIError(PriceOracleError):
    """API-level errors from NestEx."""

    pass


class PriceOracleStaleError(PriceOracleError):
    """Price data is stale."""

    pass


class PriceOracle:
    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or NESTEX_API_KEY
        self.api_secret = api_secret or NESTEX_API_SECRET
        self._price_cache: Dict[str, Any] = {}
        self._last_api_call = 0
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._db_path = DB_PATH
        self._init_cache_db()

    def _init_cache_db(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS price_cache (
                        cache_key TEXT PRIMARY KEY,
                        price_json TEXT NOT NULL,
                        fetched_at REAL NOT NULL
                    )
                    """
                )
        except sqlite3.Error as e:
            logger.warning(f"Failed to initialize price cache db: {e}")

    def _get_persistent_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT price_json, fetched_at FROM price_cache WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
            if not row:
                return None
            price_json, fetched_at = row
            if time.time() - fetched_at >= NESTEX_PRICE_TTL_SECONDS:
                return None
            return json.loads(price_json)
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.warning(f"Failed reading price cache: {e}")
            return None

    def _set_persistent_cache(self, cache_key: str, price_data: Dict[str, Any]) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO price_cache (cache_key, price_json, fetched_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        price_json=excluded.price_json,
                        fetched_at=excluded.fetched_at
                    """,
                    (cache_key, json.dumps(price_data), time.time()),
                )
        except sqlite3.Error as e:
            logger.warning(f"Failed writing price cache: {e}")

    def _rate_limit(self):
        elapsed = time.time() - self._last_api_call
        if elapsed < NESTEX_MIN_GAP_SECONDS:
            sleep_time = NESTEX_MIN_GAP_SECONDS - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_api_call = time.time()

    def _generate_signature(self, data: Dict[str, Any]) -> str:
        message = f"{self.api_key}{data.get('cur', '')}{data.get('side', '')}{data.get('qty', '')}{data.get('price', '')}"
        signature = hmac.new(
            self.api_secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return signature

    def _make_request(
        self, endpoint: str, data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        self._rate_limit()

        payload = {
            "apikey": self.api_key,
            "apisecret": self.api_secret,
        }
        if data:
            payload.update(data)

        url = f"{NESTEX_BASE_URL}/{endpoint}"

        try:
            response = self._session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            if result.get("success") != "ok":
                raise PriceOracleAPIError(f"API returned error: {result}")

            return result
        except requests.RequestException as e:
            raise PriceOracleAPIError(f"Request failed: {e}")

    def check_token(self) -> bool:
        """Check if API credentials are valid."""
        result = self._make_request("checktoken")
        return result.get("status") == "token valid"

    def get_balances(self) -> Dict[str, float]:
        """Get account balances."""
        result = self._make_request("balances")
        balances = result.get("balances", {})
        return {k: float(v) for k, v in balances.items()}

    def get_orders(self) -> list:
        """Get unfulfilled orders."""
        result = self._make_request("orders")
        return result.get("orders", [])

    def get_trades(self, cur: str = None) -> list:
        """Get fulfilled trades, optionally filtered by currency."""
        result = self._make_request("trades")
        trades = result.get("trades", [])
        if cur:
            trades = [t for t in trades if t.get("cur") == cur]
        return trades

    def place_limit_order(self, cur: str, side: str, qty: float, price: float) -> int:
        """Place a limit order. Returns order_id."""
        data = {"cur": cur, "side": side.upper(), "qty": str(qty), "price": str(price)}
        result = self._make_request("placelimitorder", data)
        return result.get("order_id")

    def cancel_order(self, order_id: int) -> bool:
        """Cancel an order."""
        data = {"order_id": str(order_id)}
        result = self._make_request("cancelorder", data)
        return result.get("success") == "ok"

    def get_price(self, from_coin: str, to_coin: str) -> Dict[str, Any]:
        """Get current exchange rate between two coins."""
        cache_key = f"{from_coin}_{to_coin}"
        now = time.time()

        persistent = self._get_persistent_cache(cache_key)
        if persistent:
            return persistent

        cached = self._price_cache.get(cache_key)
        if cached:
            age = now - cached.get("cached_at", 0)
            if age < NESTEX_PRICE_TTL_SECONDS:
                logger.debug(f"Using cached price for {cache_key}")
                return cached["price_data"]

        price_data = self._fetch_price(from_coin, to_coin)

        self._price_cache[cache_key] = {"price_data": price_data, "cached_at": now}
        self._set_persistent_cache(cache_key, price_data)

        return price_data

    def _fetch_price(self, from_coin: str, to_coin: str) -> Dict[str, Any]:
        """Fetch price from NestEx API.

        Uses the user's own trade history to calculate cross rates:
        - OXC/OXG rate = OXC/USDT price / OXG/USDT price

        Note: This private API only returns user's own trades, so we need to
        have traded both coins against USDT to calculate cross rate.
        """

        # Get user's trades for both coins against USDT
        oxc_trades = self.get_trades(cur="OXC")
        oxg_trades = self.get_trades(cur="OXG")

        oxc_price = None
        oxg_price = None

        # Calculate OXC/USDT price from recent trades
        if oxc_trades:
            oxc_trades = sorted(
                oxc_trades, key=lambda x: x.get("trade_at", ""), reverse=True
            )
            prices = [
                float(t.get("price", 0)) for t in oxc_trades[:5] if t.get("price")
            ]
            if prices:
                oxc_price = sum(prices) / len(prices)
                logger.info(f"OXC/USDT price from trades: {oxc_price}")

        # Calculate OXG/USDT price from recent trades
        if oxg_trades:
            oxg_trades = sorted(
                oxg_trades, key=lambda x: x.get("trade_at", ""), reverse=True
            )
            prices = [
                float(t.get("price", 0)) for t in oxg_trades[:5] if t.get("price")
            ]
            if prices:
                oxg_price = sum(prices) / len(prices)
                logger.info(f"OXG/USDT price from trades: {oxg_price}")

        # Calculate cross rate
        if oxc_price and oxg_price:
            cross_rate = oxc_price / oxg_price
            return {
                "from_coin": from_coin,
                "to_coin": to_coin,
                "price": cross_rate,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "oxc_usdt": oxc_price,
                "oxg_usdt": oxg_price,
                "source": "nestex_cross_usdt",
            }

        # Fallback if no trades
        if TESTING_MODE:
            logger.warning(f"Insufficient trade history for cross rate, using fallback")

        if from_coin == "OXC" and to_coin == "OXG":
            return {
                "from_coin": from_coin,
                "to_coin": to_coin,
                "price": OXC_OXG_FALLBACK_PRICE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "fallback",
            }
        elif from_coin == "OXG" and to_coin == "OXC":
            price = 1.0 / OXC_OXG_FALLBACK_PRICE if OXC_OXG_FALLBACK_PRICE else 1.0
            return {
                "from_coin": from_coin,
                "to_coin": to_coin,
                "price": price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "fallback",
            }
        elif from_coin == to_coin:
            return {
                "from_coin": from_coin,
                "to_coin": to_coin,
                "price": 1.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "fallback",
            }

        raise PriceOracleError(f"No price data available for {from_coin}/{to_coin}")

    def _get_coin_usdt_price(self, coin: str) -> float:
        """Get coin price in USDT."""
        trades = self.get_trades(cur=coin)

        if not trades:
            return None

        trades = sorted(trades, key=lambda x: x.get("trade_at", ""), reverse=True)
        recent = trades[:10]
        prices = [float(t.get("price", 0)) for t in recent if t.get("price")]

        if prices:
            return sum(prices) / len(prices)
        return None

    def validate_price(self, price_data: Dict[str, Any]) -> bool:
        """Validate that price data is fresh enough."""
        if not price_data:
            return False

        try:
            price_time_str = price_data.get("timestamp", "")
            if price_time_str.endswith("+00:00"):
                price_time = datetime.fromisoformat(price_time_str)
            else:
                price_time = datetime.fromisoformat(price_time_str).replace(
                    tzinfo=timezone.utc
                )
            now = datetime.now(timezone.utc)
            age = (now - price_time).total_seconds()

            if age > NESTEX_MAX_PRICE_AGE_SECONDS:
                raise PriceOracleStaleError(f"Price is stale: {age:.1f}s old")

            return True
        except (ValueError, TypeError):
            return False

    def get_conversion_amount(
        self, from_coin: str, to_coin: str, amount: float, fee_percent: float
    ) -> Dict[str, Any]:
        """Calculate conversion with fees."""
        price_data = self.get_price(from_coin, to_coin)

        if not self.validate_price(price_data):
            raise PriceOracleStaleError("Price validation failed")

        rate = price_data.get("price", 0)
        if rate <= 0:
            raise PriceOracleError("Invalid price rate")

        from_amount = amount
        to_amount = amount * rate

        fee = to_amount * (fee_percent / 100)
        net_amount = to_amount - fee

        return {
            "from_coin": from_coin,
            "to_coin": to_coin,
            "from_amount": from_amount,
            "to_amount": to_amount,
            "fee_amount": fee,
            "net_amount": net_amount,
            "rate": rate,
            "price_data": price_data,
        }
