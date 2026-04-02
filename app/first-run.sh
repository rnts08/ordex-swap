#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Running schema migrations..."
python migrations/migrate_schema.py

echo "Running settings migrations..."
python migrations/migrate_settings.py

echo "Initializing wallets..."
python first_startup.py
