#!/usr/bin/env python3
"""
Wallet management CLI for OrdexSwap production server.
Provides commands to get balances and send transactions via daemon RPC.

Usage:
    python wallet_cli.py getbalance [--coin OXC|OXG]
    python wallet_cli.py sendtoaddress <address> <amount> [--coin OXC|OXG]
    python wallet_cli.py status
    python wallet_cli.py getnewaddress [--label label] [--coin OXC|OXG]
    python wallet_cli.py gettransaction <txid> [--coin OXC|OXG]
"""

import argparse
import os
import sys
import json
import requests
from requests.auth import HTTPBasicAuth
from typing import Optional, Dict, Any, List

WALLET_RPC_TIMEOUT = 30


class WalletClient:
    def __init__(self, rpc_url: str, rpc_user: str, rpc_password: str, coin_name: str):
        self.rpc_url = rpc_url.rstrip("/")
        self.coin_name = coin_name
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(rpc_user, rpc_password)
        self._session.headers.update({"Content-Type": "application/json"})

    def _call(self, method: str, params: List[Any] = None) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "1.0",
            "id": "wallet-cli",
            "method": method,
            "params": params or [],
        }

        try:
            response = self._session.post(
                self.rpc_url, json=payload, timeout=WALLET_RPC_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()

            if isinstance(result, dict) and result.get("error"):
                raise RuntimeError(f"RPC error: {result['error']}")

            return result.get("result", {}) if isinstance(result, dict) else {}
        except requests.RequestException as e:
            raise RuntimeError(f"Request failed for {self.coin_name}: {e}")

    def get_balance(self, minconf: int = 0) -> float:
        try:
            return float(self._call("getbalance", ["*", minconf]))
        except RuntimeError:
            return float(self._call("getbalance", [minconf]))

    def sendtoaddress(self, address: str, amount: float, comment: str = "") -> str:
        params = [address, amount]
        if comment:
            params.append(comment)
        return self._call("sendtoaddress", params)

    def getnewaddress(self, label: str = "") -> str:
        params = [label] if label else []
        return self._call("getnewaddress", params)

    def gettransaction(self, txid: str) -> Dict[str, Any]:
        return self._call("gettransaction", [txid])

    def getnetworkinfo(self) -> Dict[str, Any]:
        return self._call("getnetworkinfo")

    def getwalletinfo(self) -> Dict[str, Any]:
        return self._call("getwalletinfo")


def get_clients() -> tuple[WalletClient, WalletClient]:
    oxc_rpc_url = os.environ.get("OXC_RPC_URL", "http://127.0.0.1:25173")
    oxc_rpc_user = os.environ.get("OXC_RPC_USER", "rpcuser")
    oxc_rpc_pass = os.environ.get("OXC_RPC_PASSWORD", "rpcpassword")

    oxg_rpc_url = os.environ.get("OXG_RPC_URL", "http://127.0.0.1:25465")
    oxg_rpc_user = os.environ.get("OXG_RPC_USER", "rpcuser")
    oxg_rpc_pass = os.environ.get("OXG_RPC_PASSWORD", "rpcpassword")

    oxc = WalletClient(oxc_rpc_url, oxc_rpc_user, oxc_rpc_pass, "OXC")
    oxg = WalletClient(oxg_rpc_url, oxg_rpc_user, oxg_rpc_pass, "OXG")
    return oxc, oxg


def cmd_getbalance(coin: str = "both") -> int:
    oxc, oxg = get_clients()
    if coin in ("OXC", "both"):
        try:
            bal = oxc.get_balance()
            print(f"OXC balance: {bal}")
        except RuntimeError as e:
            print(f"OXC error: {e}", file=sys.stderr)
    if coin in ("OXG", "both"):
        try:
            bal = oxg.get_balance()
            print(f"OXG balance: {bal}")
        except RuntimeError as e:
            print(f"OXG error: {e}", file=sys.stderr)
    return 0


def cmd_sendtoaddress(address: str, amount: float, coin: str = "OXC") -> int:
    oxc, oxg = get_clients()
    client = oxc if coin == "OXC" else oxg
    try:
        txid = client.sendtoaddress(address, amount)
        print(f"Sent {amount} {coin} to {address}")
        print(f"Transaction ID: {txid}")
        return 0
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_getnewaddress(label: str = "", coin: str = "OXC") -> int:
    oxc, oxg = get_clients()
    client = oxc if coin == "OXC" else oxg
    try:
        addr = client.getnewaddress(label)
        print(f"{coin} address: {addr}")
        return 0
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_status() -> int:
    oxc, oxg = get_clients()
    print("=== Wallet Status ===")
    for client in [oxc, oxg]:
        try:
            info = client.getwalletinfo()
            print(f"\n{client.coin_name}:")
            print(f"  Wallet: {info.get('walletname', 'unknown')}")
            print(f"  Balance: {info.get('balance', 0)}")
            print(f"  Transactions: {info.get('txcount', 0)}")
        except RuntimeError as e:
            print(f"\n{client.coin_name}: ERROR - {e}")
    print()
    return 0


def cmd_gettransaction(txid: str, coin: str = "OXC") -> int:
    oxc, oxg = get_clients()
    client = oxc if coin == "OXC" else oxg
    try:
        tx = client.gettransaction(txid)
        print(json.dumps(tx, indent=2))
        return 0
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="OrdexSwap Wallet Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show wallet status for both daemons")

    bal_parser = subparsers.add_parser("getbalance", help="Get wallet balance")
    bal_parser.add_argument("--coin", choices=["OXC", "OXG", "both"], default="both")

    newaddr_parser = subparsers.add_parser("getnewaddress", help="Generate new address")
    newaddr_parser.add_argument("--label", default="", help="Address label")
    newaddr_parser.add_argument("--coin", choices=["OXC", "OXG"], default="OXC")

    send_parser = subparsers.add_parser("sendtoaddress", help="Send to address")
    send_parser.add_argument("address", help="Recipient address")
    send_parser.add_argument("amount", type=float, help="Amount to send")
    send_parser.add_argument("--coin", choices=["OXC", "OXG"], default="OXC")

    tx_parser = subparsers.add_parser("gettransaction", help="Get transaction details")
    tx_parser.add_argument("txid", help="Transaction ID")
    tx_parser.add_argument("--coin", choices=["OXC", "OXG"], default="OXC")

    args = parser.parse_args()

    if args.command == "getbalance":
        return cmd_getbalance(args.coin)
    elif args.command == "sendtoaddress":
        return cmd_sendtoaddress(args.address, args.amount, args.coin)
    elif args.command == "getnewaddress":
        return cmd_getnewaddress(args.label, args.coin)
    elif args.command == "status":
        return cmd_status()
    elif args.command == "gettransaction":
        return cmd_gettransaction(args.txid, args.coin)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
