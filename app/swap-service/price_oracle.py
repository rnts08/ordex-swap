import json
import time
import logging
import sqlite3
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import requests

from config import (
    NESTEX_PUBLIC_BASE_URL,
    NESTEX_PUBLIC_MIN_GAP_SECONDS,
    NESTEX_PRICE_TTL_SECONDS,
    NESTEX_MAX_PRICE_AGE_SECONDS,
    OXC_USDT_FALLBACK_PRICE,
    OXG_USDT_FALLBACK_PRICE,
    OXC_OXG_FALLBACK_PRICE,
    TESTING_MODE,
    DB_PATH,
    SWAP_MIN_FEE_OXC,
    SWAP_MIN_FEE_OXG,
)
from db_pool import get_pool

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
    def __init__(self):
        self._price_cache: Dict[str, Any] = {}
        self._last_public_call = 0
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._db_path = DB_PATH
        self._pool = get_pool(self._db_path)
        self._init_cache_db()

    def _init_cache_db(self) -> None:
        try:
            with self._pool.get_connection() as conn:
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
            with self._pool.get_connection() as conn:
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
            with self._pool.get_connection() as conn:
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

    def _rate_limit_public(self):
        elapsed = time.time() - self._last_public_call
        if elapsed < NESTEX_PUBLIC_MIN_GAP_SECONDS:
            sleep_time = NESTEX_PUBLIC_MIN_GAP_SECONDS - elapsed
            logger.debug(f"Public rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_public_call = time.time()

    def _make_public_request(
        self, endpoint: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        self._rate_limit_public()
        url = f"{NESTEX_PUBLIC_BASE_URL}/{endpoint}"
        try:
            response = self._session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise PriceOracleAPIError(f"Public API request failed: {e}")

    def get_public_tickers(self) -> list:
        cached = self._price_cache.get("public_tickers")
        if cached:
            age = time.time() - cached.get("cached_at", 0)
            if age < NESTEX_PRICE_TTL_SECONDS:
                return cached["data"]
        tickers = self._make_public_request("tickers")
        self._price_cache["public_tickers"] = {
            "data": tickers,
            "cached_at": time.time(),
        }
        return tickers

    def get_tradebook(self, ticker_id: str, page: int = 1) -> Dict[str, Any]:
        params = {"page": page}
        return self._make_public_request(f"tradebook/{ticker_id}", params=params)

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
        """Fetch price from NestEx public tickers."""

        oxc_price = None
        oxg_price = None
        try:
            tickers = self.get_public_tickers()
            if isinstance(tickers, list):
                for t in tickers:
                    if t.get("ticker_id") == "OXC_USDT":
                        oxc_price = float(t.get("last_price", 0) or 0)
                    elif t.get("ticker_id") == "OXG_USDT":
                        oxg_price = float(t.get("last_price", 0) or 0)
        except PriceOracleAPIError as e:
            logger.warning(f"Failed to fetch public tickers: {e}")

        if oxc_price and oxg_price:
            cross_rate = oxc_price / oxg_price
            if from_coin == "OXG" and to_coin == "OXC":
                cross_rate = 1.0 / cross_rate
            return {
                "from_coin": from_coin,
                "to_coin": to_coin,
                "price": cross_rate,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "oxc_usdt": oxc_price,
                "oxg_usdt": oxg_price,
                "source": "nestex_ticker",
            }

        if TESTING_MODE:
            logger.warning("Insufficient ticker data for cross rate, using fallback")

        if from_coin == "OXC" and to_coin == "OXG":
            if oxc_price and OXG_USDT_FALLBACK_PRICE:
                return {
                    "from_coin": from_coin,
                    "to_coin": to_coin,
                    "price": oxc_price / OXG_USDT_FALLBACK_PRICE,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "oxc_usdt": oxc_price,
                    "oxg_usdt": OXG_USDT_FALLBACK_PRICE,
                    "source": "fallback",
                }
            return {
                "from_coin": from_coin,
                "to_coin": to_coin,
                "price": OXC_OXG_FALLBACK_PRICE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "fallback",
            }
        elif from_coin == "OXG" and to_coin == "OXC":
            if oxg_price and OXC_USDT_FALLBACK_PRICE:
                cross = OXC_USDT_FALLBACK_PRICE / oxg_price
                return {
                    "from_coin": from_coin,
                    "to_coin": to_coin,
                    "price": 1.0 / cross,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "oxc_usdt": OXC_USDT_FALLBACK_PRICE,
                    "oxg_usdt": oxg_price,
                    "source": "fallback",
                }
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
        """Get coin price in USDT from public tickers."""
        try:
            tickers = self.get_public_tickers()
            if isinstance(tickers, list):
                for t in tickers:
                    if t.get("ticker_id") == f"{coin}_USDT":
                        return float(t.get("last_price", 0) or 0)
        except PriceOracleAPIError:
            return None
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
        self,
        from_coin: str,
        to_coin: str,
        amount: float,
        fee_percent: float,
        min_fee_oxc: float = SWAP_MIN_FEE_OXC,
        min_fee_oxg: float = SWAP_MIN_FEE_OXG,
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

        min_fee = min_fee_oxg if to_coin.upper() == "OXG" else min_fee_oxc
        if fee < min_fee:
            fee = min_fee

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
