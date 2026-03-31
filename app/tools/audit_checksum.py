#!/usr/bin/env python3
"""
Audit Checksum Tool - Ordex Swap Service
Performs 100% parity check between Blockchain RPC and Application Database.
"""

import os
import sys
import logging
import argparse
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add swap-service to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(script_dir, "..", "swap-service")))

# Discovery: Load environment from the app directory
env_path = os.path.abspath(os.path.join(script_dir, "..", ".env"))
if os.path.exists(env_path):
    load_dotenv(env_path)

# Ensure DATA_DIR is absolute and exists
data_dir = os.environ.get("DATA_DIR", os.path.abspath(os.path.join(script_dir, "..", "data")))
if not os.path.isabs(data_dir):
    data_dir = os.path.abspath(os.path.join(script_dir, "..", data_dir))
os.environ["DATA_DIR"] = data_dir
os.environ["DB_PATH"] = os.path.join(data_dir, "ordex.db")

from wallet_rpc import OXCWallet, OXGWallet
from swap_engine import SwapEngine, SwapStatus
from swap_history import SwapHistoryService
from admin_service import AdminService
from price_oracle import PriceOracle

from config import (
    OXC_RPC_URL, OXC_RPC_USER, OXC_RPC_PASSWORD,
    OXG_RPC_URL, OXG_RPC_USER, OXG_RPC_PASSWORD,
    TESTING_MODE
)

# Disable unnecessary logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("audit_checksum")

def print_banner():
    print("=" * 60)
    print("       ORDEX SWAP - FINANCIAL AUDIT CHECKSUM TOOL")
    print("=" * 60)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Mode: {'TESTING' if TESTING_MODE else 'PRODUCTION'}")
    print(f"Data Dir: {data_dir}")
    print("-" * 60)

def main():
    parser = argparse.ArgumentParser(description="Perform blockchain vs database parity check.")
    parser.add_argument("--count", type=int, default=100, help="Number of recent transactions to scan (default: 100)")
    parser.add_argument("--verbose", action="store_true", help="Show detailed discrepancy lists")
    args = parser.parse_args()

    print_banner()

    try:
        # Initialize Services
        oracle = PriceOracle()
        oxc_wallet = OXCWallet(OXC_RPC_URL, OXC_RPC_USER, OXC_RPC_PASSWORD, testing_mode=TESTING_MODE)
        oxg_wallet = OXGWallet(OXG_RPC_URL, OXG_RPC_USER, OXG_RPC_PASSWORD, testing_mode=TESTING_MODE)
        history = SwapHistoryService(data_dir=data_dir)
        admin = AdminService(db_path=os.environ["DB_PATH"])

        engine = SwapEngine(
            oxc_wallet=oxc_wallet,
            oxg_wallet=oxg_wallet,
            oracle=oracle,
            history=history,
            admin=admin
        )

        print(f"Scanning the last {args.count} transactions on OXC and OXG...")
        results = engine.reconcile_full_history(count=args.count)

        # Print Summary
        print("\n[ AUDIT SUMMARY ]")
        print(f"Scanned Transactions:   {results['scanned_count']}")
        print(f"Matched Swap Events:    {results['matched_swaps_count']}")
        print(f"Acknowledged (Handled): {len(results['acknowledged_deposits'])}")
        
        # Discrepancies
        unaccounted_in = len(results['unaccounted_deposits'])
        unaccounted_out = len(results['unaccounted_withdrawals'])
        mismatched = len(results['mismatched_amounts'])
        late = len(results['late_deposits'])

        print(f"Late Deposits Found:    {late}")
        print(f"Mismatched Amounts:     {mismatched}")
        print(f"Unaccounted Inbound:    {unaccounted_in}")
        print(f"Unaccounted Outbound:   {unaccounted_out}")

        # Balance Check
        print("\n[ BALANCE CHECK (Satoshi Parity) ]")
        for coin in ["OXC", "OXG"]:
            stats = results["coin_stats"][coin]
            print(f"{coin}: Received +{stats['total_received']:.8f} | Sent -{stats['total_sent']:.8f}")

        # Health Check
        print("\n[ STATUS ]")
        if (unaccounted_in + unaccounted_out + mismatched + late) == 0:
            print(">>> SUCCESS: 100% of scanned transactions are accounted for in the database.")
            sys.exit(0)
        else:
            print(">>> WARNING: Discrepancies detected. Action required in Admin Dashboard.")
            
            if args.verbose:
                print("\n[ DISCREPANCY DETAILS ]")
                for d in results['unaccounted_deposits']:
                    print(f" - UNACCOUNTED INCOMING: {d['txid']} ({d['amount']} {d['coin']})")
                for w in results['unaccounted_withdrawals']:
                    print(f" - UNACCOUNTED OUTGOING: {w['txid']} ({w['amount']} {w['coin']})")
                for m in results['mismatched_amounts']:
                    print(f" - MISMATCHED [{m.get('type','UNKNOWN')}]: Swap {m['swap_id']} (Expected {m['expected']}, Actual {m['actual']})")
                for l in results['late_deposits']:
                    print(f" - LATE DEPOSIT: Swap {l['swap_id']} ({l['amount']} {l['coin']}) - Status: {l['status']}")
            
            sys.exit(1)

    except Exception as e:
        print(f"\nFATAL ERROR during audit: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
