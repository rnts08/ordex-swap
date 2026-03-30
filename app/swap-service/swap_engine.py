import uuid
import logging
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone

from price_oracle import PriceOracle, PriceOracleError, PriceOracleStaleError
from wallet_rpc import OXCWallet, OXGWallet, WalletRPCError
from swap_history import SwapHistoryService
from config import (
    SWAP_FEE_PERCENT,
    SWAP_MIN_AMOUNT,
    SWAP_MAX_AMOUNT,
    SUPPORTED_COINS,
    TESTING_MODE,
    SWAP_CONFIRMATIONS_REQUIRED,
    SWAP_EXPIRE_MINUTES,
    SWAP_MIN_FEE_OXC,
    SWAP_MIN_FEE_OXG,
    SETTLEMENT_INTERVAL_SECONDS,
    DEFAULT_LIMIT,
)

logger = logging.getLogger(__name__)


class SwapStatus(Enum):
    PENDING = "pending"
    AWAITING_DEPOSIT = "awaiting_deposit"
    PROCESSING = "processing"
    COMPLETED = "completed"
    DELAYED = "delayed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class SwapError(Exception):
    """Base exception for swap errors."""

    pass


class InvalidAmountError(SwapError):
    """Amount is outside allowed range."""

    pass


class LiquidityHoldError(SwapError):
    """Swap blocked by a pending delayed swap due to low liquidity."""

    pass


class UnsupportedPairError(SwapError):
    """Currency pair not supported."""

    pass


class SwapEngine:
    def __init__(
        self,
        price_oracle: PriceOracle,
        oxc_wallet: OXCWallet,
        oxg_wallet: OXGWallet,
        history_service: SwapHistoryService = None,
        fee_percent: float = SWAP_FEE_PERCENT,
        min_amount: float = SWAP_MIN_AMOUNT,
        max_amount: float = SWAP_MAX_AMOUNT,
        confirmations_required: int = SWAP_CONFIRMATIONS_REQUIRED,
        min_fee_oxc: float = SWAP_MIN_FEE_OXC,
        min_fee_oxg: float = SWAP_MIN_FEE_OXG,
    ):
        self.oracle = price_oracle
        self.oxc_wallet = oxc_wallet
        self.oxg_wallet = oxg_wallet
        self.history = history_service or SwapHistoryService()
        self.fee_percent = fee_percent
        self.min_amount = min_amount
        self.max_amount = max_amount
        self.confirmations_required = confirmations_required
        self.min_fee_oxc = min_fee_oxc
        self.min_fee_oxg = min_fee_oxg
        self._pending_swaps: Dict[str, Dict[str, Any]] = {}
        self._settlement_thread = None
        self._settlement_stop = None

        self._load_pending_swaps_from_db()

    def _load_pending_swaps_from_db(self) -> None:
        try:
            pending = self.history.get_pending_swaps()
            for swap in pending:
                self._pending_swaps[swap["swap_id"]] = swap
            if self._pending_swaps:
                logger.info(
                    f"Loaded {len(self._pending_swaps)} pending swaps from database"
                )
        except Exception as e:
            logger.warning(f"Failed to load pending swaps from database: {e}")

    def _is_liquidity_error(self, error: Exception) -> bool:
        message = str(error).lower()
        keywords = [
            "insufficient funds",
            "insufficient balance",
            "balance too low",
            "not enough funds",
            "not enough balance",
            "insufficient",
        ]
        return any(keyword in message for keyword in keywords)

    def _get_delayed_swaps(self) -> Dict[str, Dict[str, Any]]:
        delayed = {
            swap_id: swap
            for swap_id, swap in self._pending_swaps.items()
            if swap.get("status") == SwapStatus.DELAYED.value
        }

        for swap in self.history.get_swaps_by_statuses([SwapStatus.DELAYED.value]):
            swap_id = swap.get("swap_id")
            if swap_id and swap_id not in delayed:
                delayed[swap_id] = swap
        return delayed

    def _get_liquidity_hold(self, to_coin: str) -> Optional[float]:
        delayed_swaps = self._get_delayed_swaps().values()
        holds = [
            float(swap.get("net_amount", 0))
            for swap in delayed_swaps
            if swap.get("to_coin") == to_coin
        ]
        if not holds:
            return None
        return min(holds)

    def validate_swap_request(
        self, from_coin: str, to_coin: str, amount: float
    ) -> None:
        from_coin = from_coin.upper()
        to_coin = to_coin.upper()

        if from_coin not in SUPPORTED_COINS or to_coin not in SUPPORTED_COINS:
            raise UnsupportedPairError(f"Unsupported pair: {from_coin}/{to_coin}")

        if from_coin == to_coin:
            raise UnsupportedPairError("Cannot swap same coin")

        if amount < self.min_amount:
            raise InvalidAmountError(f"Amount {amount} below minimum {self.min_amount}")

        if amount > self.max_amount:
            raise InvalidAmountError(f"Amount {amount} above maximum {self.max_amount}")

        conversion = self.oracle.get_conversion_amount(
            from_coin,
            to_coin,
            amount,
            self.fee_percent,
            min_fee_oxc=self.min_fee_oxc,
            min_fee_oxg=self.min_fee_oxg,
        )

        if conversion["net_amount"] <= 0:
            raise InvalidAmountError(
                f"Fee too high: would result in zero or negative output. "
                f"Output would be {conversion['net_amount']} {to_coin}"
            )

    def get_deposit_address(self, coin: str) -> str:
        coin = coin.upper()

        if coin == "OXC":
            return self.oxc_wallet.get_address()
        elif coin == "OXG":
            return self.oxg_wallet.get_address()
        else:
            raise UnsupportedPairError(f"Unknown coin: {coin}")

    def _calculate_conversion(
        self, from_coin: str, to_coin: str, amount: float
    ) -> Dict[str, Any]:
        """Calculate conversion with fees. Returns conversion dict and liquidity status."""
        conversion = self.oracle.get_conversion_amount(
            from_coin,
            to_coin,
            amount,
            self.fee_percent,
            min_fee_oxc=self.min_fee_oxc,
            min_fee_oxg=self.min_fee_oxg,
        )
        liquidity_hold = self._get_liquidity_hold(to_coin)
        liquidity_blocked = (
            liquidity_hold is not None
            and float(conversion["net_amount"]) > liquidity_hold
        )
        return conversion, liquidity_hold, liquidity_blocked

    def create_swap_quote(
        self, from_coin: str, to_coin: str, amount: float
    ) -> Dict[str, Any]:
        self.validate_swap_request(from_coin, to_coin, amount)

        from_coin = from_coin.upper()
        to_coin = to_coin.upper()

        conversion, liquidity_hold, liquidity_blocked = self._calculate_conversion(
            from_coin, to_coin, amount
        )

        return {
            "quote_id": str(uuid.uuid4()),
            "from_coin": from_coin,
            "to_coin": to_coin,
            "from_amount": amount,
            "to_amount": conversion["to_amount"],
            "fee_amount": conversion["fee_amount"],
            "net_amount": conversion["net_amount"],
            "rate": conversion["rate"],
            "price_data": conversion["price_data"],
            "expires_at": datetime.now(timezone.utc).isoformat(),
            "fee_percent": self.fee_percent,
            "min_fee_oxc": self.min_fee_oxc,
            "min_fee_oxg": self.min_fee_oxg,
            "liquidity_hold_amount": liquidity_hold,
            "liquidity_blocked": liquidity_blocked,
            "liquidity_notice": (
                "Temporary liquidity delay on this output coin. "
                "Swaps above the queued amount are paused."
                if liquidity_blocked
                else None
            ),
        }

    def create_swap(
        self, from_coin: str, to_coin: str, amount: float, user_address: str
    ) -> Dict[str, Any]:
        self.validate_swap_request(from_coin, to_coin, amount)

        from_coin = from_coin.upper()
        to_coin = to_coin.upper()

        conversion, liquidity_hold, liquidity_blocked = self._calculate_conversion(
            from_coin, to_coin, amount
        )

        if liquidity_blocked:
            raise LiquidityHoldError(
                "Liquidity delay: swaps above the queued amount are temporarily paused."
            )

        swap_id = str(uuid.uuid4())
        deposit_address = self.get_deposit_address(from_coin)
        now = datetime.now(timezone.utc)

        swap = {
            "swap_id": swap_id,
            "from_coin": from_coin,
            "to_coin": to_coin,
            "from_amount": amount,
            "to_amount": conversion["to_amount"],
            "fee_amount": conversion["fee_amount"],
            "net_amount": conversion["net_amount"],
            "rate": conversion["rate"],
            "user_address": user_address,
            "deposit_address": deposit_address,
            "status": SwapStatus.PENDING.value,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "deposit_txid": None,
            "settle_txid": None,
        }

        self._pending_swaps[swap_id] = swap
        self.history.add_swap(swap)

        logger.info(
            f"Created swap {swap_id}: {amount} {from_coin} -> {conversion['net_amount']} {to_coin}"
        )

        return swap

    def get_swap(self, swap_id: str) -> Optional[Dict[str, Any]]:
        # Check pending swaps first
        if swap_id in self._pending_swaps:
            return self._pending_swaps[swap_id]
        # Check history
        return self.history.get_swap(swap_id)

    def confirm_deposit(self, swap_id: str, deposit_txid: str) -> Dict[str, Any]:
        swap = self._pending_swaps.get(swap_id)
        if not swap:
            # Check history
            swap = self.history.get_swap(swap_id)
            if not swap:
                raise SwapError(f"Swap not found: {swap_id}")
            raise SwapError(f"Swap already completed: {swap_id}")

        if swap["status"] not in [
            SwapStatus.PENDING.value,
            SwapStatus.AWAITING_DEPOSIT.value,
        ]:
            raise SwapError(f"Swap in invalid state: {swap['status']}")

        if self.confirmations_required > 0:
            try:
                from_coin = swap["from_coin"]
                if from_coin == "OXC":
                    tx = self.oxc_wallet.get_transaction(deposit_txid)
                elif from_coin == "OXG":
                    tx = self.oxg_wallet.get_transaction(deposit_txid)
                else:
                    raise UnsupportedPairError(f"Unknown input coin: {from_coin}")

                confirmations = 0
                if isinstance(tx, dict):
                    confirmations = int(tx.get("confirmations") or 0)

                if confirmations < self.confirmations_required:
                    swap["deposit_txid"] = deposit_txid
                    swap["status"] = SwapStatus.AWAITING_DEPOSIT.value
                    swap["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self.history.update_swap(swap_id, swap)
                    logger.info(
                        "Swap %s awaiting confirmations: %s/%s",
                        swap_id,
                        confirmations,
                        self.confirmations_required,
                    )
                    return swap
            except WalletRPCError as e:
                raise SwapError(f"Unable to verify deposit confirmations: {e}")

        swap["deposit_txid"] = deposit_txid
        swap["status"] = SwapStatus.PROCESSING.value
        swap["updated_at"] = datetime.now(timezone.utc).isoformat()

        return self._settle_swap(swap_id)

    def _settle_swap(self, swap_id: str) -> Dict[str, Any]:
        swap = self._pending_swaps.get(swap_id)
        if not swap:
            swap = self.history.get_swap(swap_id)
            if not swap:
                raise SwapError(f"Swap not found: {swap_id}")
            self._pending_swaps[swap_id] = swap

        try:
            from_coin = swap["from_coin"]
            to_coin = swap["to_coin"]
            user_address = swap["user_address"]
            net_amount = swap["net_amount"]

            if TESTING_MODE:
                settle_txid = f"tx_test_mock_{swap_id[:8]}"
                logger.info(f"Testing mode: simulating swap {swap_id} completion")
            else:
                if to_coin == "OXC":
                    settle_txid = self.oxc_wallet.send(user_address, net_amount)
                elif to_coin == "OXG":
                    settle_txid = self.oxg_wallet.send(user_address, net_amount)
                else:
                    raise UnsupportedPairError(f"Unknown output coin: {to_coin}")

            swap["settle_txid"] = settle_txid
            swap["status"] = SwapStatus.COMPLETED.value
            swap["updated_at"] = datetime.now(timezone.utc).isoformat()

            # Move to completed history
            if swap_id in self._pending_swaps:
                del self._pending_swaps[swap_id]
            self.history.complete_swap(swap_id)

            logger.info(f"Swap {swap_id} completed: {settle_txid}")

            return swap

        except WalletRPCError as e:
            if self._is_liquidity_error(e):
                swap["status"] = SwapStatus.DELAYED.value
                swap["delay_code"] = "liquidity_low"
                swap["delay_reason"] = "Insufficient liquidity to complete swap."
                swap["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
                swap["updated_at"] = swap["last_attempt_at"]
                self.history.update_swap(swap_id, swap)
                logger.warning(f"Swap {swap_id} delayed due to low liquidity: {e}")
                return swap

            swap["status"] = SwapStatus.FAILED.value
            swap["error"] = str(e)
            swap["updated_at"] = datetime.now(timezone.utc).isoformat()
            logger.error(f"Swap {swap_id} failed: {e}")
            raise SwapError(f"Settlement failed: {e}")

    def cancel_swap(self, swap_id: str) -> Dict[str, Any]:
        swap = self._pending_swaps.get(swap_id)
        if not swap:
            raise SwapError(f"Swap not found: {swap_id}")

        if swap["status"] in [SwapStatus.COMPLETED.value, SwapStatus.FAILED.value]:
            raise SwapError(f"Cannot cancel swap in state: {swap['status']}")

        swap["status"] = SwapStatus.CANCELLED.value
        swap["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Persist to database
        self.history.update_swap(swap_id, swap)

        logger.info(f"Swap {swap_id} cancelled")

        return swap

    def list_swaps(self, status: str = None, include_inactive: bool = False) -> list:
        return self.history.get_all_swaps(
            status=status, limit=100, include_inactive=include_inactive
        )

    def get_balance(self, coin: str) -> float:
        coin = coin.upper()

        if coin == "OXC":
            return self.oxc_wallet.get_balance()
        elif coin == "OXG":
            return self.oxg_wallet.get_balance()
        else:
            raise UnsupportedPairError(f"Unknown coin: {coin}")

    def process_delayed_swaps(self) -> int:
        processed = 0
        expired = 0
        now = datetime.now(timezone.utc)

        for swap_id, swap in self._get_delayed_swaps().items():
            try:
                result = self._settle_swap(swap_id)
                if result.get("status") == SwapStatus.COMPLETED.value:
                    processed += 1
            except SwapError:
                continue

        for swap_id, swap in dict(self._pending_swaps).items():
            if swap["status"] in [
                SwapStatus.PENDING.value,
                SwapStatus.AWAITING_DEPOSIT.value,
                SwapStatus.DELAYED.value,
            ]:
                if "expires_at" not in swap:
                    continue
                expires_at = datetime.fromisoformat(
                    swap["expires_at"].replace("Z", "+00:00")
                )
                if (now - expires_at).total_seconds() > SWAP_EXPIRE_MINUTES * 60:
                    swap["status"] = SwapStatus.EXPIRED.value
                    swap["updated_at"] = now.isoformat()
                    self.history.update_swap(swap_id, swap)
                    del self._pending_swaps[swap_id]
                    logger.info(
                        f"Swap {swap_id} expired after {SWAP_EXPIRE_MINUTES} minutes"
                    )
                    expired += 1

        return processed

    def start_background_settlement(self, interval_seconds: int = None) -> None:
        if self._settlement_thread:
            return
        import threading

        interval_seconds = interval_seconds or SETTLEMENT_INTERVAL_SECONDS
        self._settlement_stop = threading.Event()
        self._settlement_interval = interval_seconds
        self._last_settlement_run = None

        def loop():
            while not self._settlement_stop.is_set():
                try:
                    self._last_settlement_run = datetime.now(timezone.utc).isoformat()
                    self.process_delayed_swaps()
                except Exception as e:
                    logger.warning(f"Delayed swap processing error: {e}")
                self._settlement_stop.wait(interval_seconds)

        self._settlement_thread = threading.Thread(target=loop, daemon=True)
        self._settlement_thread.start()

    def stop_background_settlement(self) -> None:
        if not self._settlement_thread:
            return
        if self._settlement_stop:
            self._settlement_stop.set()
        self._settlement_thread.join(timeout=5)
        self._settlement_thread = None
        self._settlement_stop = None

    def get_settlement_status(self) -> Dict[str, Any]:
        return {
            "running": self._settlement_thread is not None,
            "last_run_at": self._last_settlement_run,
            "interval_seconds": getattr(self, "_settlement_interval", None),
        }
