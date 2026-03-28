import logging
import os
import hashlib
from typing import Optional, Dict, Any, List
import requests
from requests.auth import HTTPBasicAuth

from config import TESTING_MODE

logger = logging.getLogger(__name__)


class WalletRPCError(Exception):
    pass


class WalletRPC:
    def __init__(
        self,
        rpc_url: str,
        rpc_user: str,
        rpc_password: str,
        coin_name: str,
        testing_mode: bool = None,
    ):
        self.rpc_url = rpc_url.rstrip("/")
        self.coin_name = coin_name
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(rpc_user, rpc_password)
        self._session.headers.update({"Content-Type": "application/json"})
        self._testing_mode = testing_mode if testing_mode is not None else TESTING_MODE
        self._address_counter = 0

    def _call(self, method: str, params: List[Any] = None) -> Dict[str, Any]:
        if self._testing_mode and method == "sendtoaddress":
            params = params or []
            return f"tx_test_{hashlib.md5(f'{params[0]}{params[1]}'.encode()).hexdigest()[:16]}"

        payload = {
            "jsonrpc": "1.0",
            "id": "ordex-swap",
            "method": method,
            "params": params or [],
        }

        try:
            response = self._session.post(self.rpc_url, json=payload, timeout=60)
            try:
                result = response.json()
            except ValueError:
                result = None

            if response.status_code >= 400:
                if isinstance(result, dict) and result.get("error"):
                    err = result["error"]
                    raise WalletRPCError(f"RPC error: {err}")
                response.raise_for_status()

            if isinstance(result, dict) and result.get("error"):
                raise WalletRPCError(f"RPC error: {result['error']}")

            return result.get("result", {}) if isinstance(result, dict) else {}
        except requests.RequestException as e:
            raise WalletRPCError(f"Request failed for {self.coin_name}: {e}")

    def _mock_call(self, method: str, params: List[Any] = None) -> Dict[str, Any]:
        if method == "getnewaddress":
            label = params[0] if params else ""
            self._address_counter += 1
            if self.coin_name == "OXC":
                return f"oxc_test_{self._address_counter}_{label}"
            else:
                return f"oxg_test_{self._address_counter}_{label}"

        elif method == "getbalance":
            return 1000.0

        elif method == "listunspent":
            return []

        return {}

    def get_new_address(self, label: str = "") -> str:
        params = [label] if label else []
        return self._call("getnewaddress", params)

    def get_balance(self, minconf: int = 0, include_watchonly: bool = False) -> float:
        params = [minconf, include_watchonly]
        return float(self._call("getbalance", params))

    def list_unspent(
        self, minconf: int = 0, maxconf: int = 9999999
    ) -> List[Dict[str, Any]]:
        params = [minconf, maxconf]
        return self._call("listunspent", params)

    def send_to_address(self, address: str, amount: float, comment: str = "") -> str:
        params = [address, amount]
        if comment:
            params.append(comment)
        return self._call("sendtoaddress", params)

    def get_transaction(self, txid: str) -> Dict[str, Any]:
        return self._call("gettransaction", [txid])

    def get_block_count(self) -> int:
        return self._call("getblockcount")

    def get_network_info(self) -> Dict[str, Any]:
        return self._call("getnetworkinfo")

    def get_wallet_info(self) -> Dict[str, Any]:
        return self._call("getwalletinfo")

    def validate_address(self, address: str) -> Dict[str, Any]:
        return self._call("validateaddress", [address])

    def is_valid(self) -> bool:
        try:
            self.get_wallet_info()
            return True
        except WalletRPCError:
            return False

    def create_wallet(self, wallet_name: str) -> Dict[str, Any]:
        return self._call("createwallet", [wallet_name])

    def load_wallet(self, wallet_name: str) -> Dict[str, Any]:
        return self._call("loadwallet", [wallet_name])


class OXCWallet:
    def __init__(
        self, rpc_url: str, rpc_user: str, rpc_password: str, testing_mode: bool = None
    ):
        self.rpc = WalletRPC(rpc_url, rpc_user, rpc_password, "OXC", testing_mode)

    @property
    def coin_name(self) -> str:
        return "OXC"

    def get_address(self) -> str:
        return self.rpc.get_new_address("swap-deposit")

    def get_balance(self) -> float:
        return self.rpc.get_balance()

    def send(self, address: str, amount: float) -> str:
        return self.rpc.send_to_address(address, amount, "swap-output")


class OXGWallet:
    def __init__(
        self, rpc_url: str, rpc_user: str, rpc_password: str, testing_mode: bool = None
    ):
        self.rpc = WalletRPC(rpc_url, rpc_user, rpc_password, "OXG", testing_mode)

    @property
    def coin_name(self) -> str:
        return "OXG"

    def get_address(self) -> str:
        return self.rpc.get_new_address("swap-deposit")

    def get_balance(self) -> float:
        return self.rpc.get_balance()

    def send(self, address: str, amount: float) -> str:
        return self.rpc.send_to_address(address, amount, "swap-output")
