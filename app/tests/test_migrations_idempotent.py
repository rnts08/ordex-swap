"""Test that migrations are idempotent (can be run multiple times safely)."""

import os
import tempfile
import sqlite3
import pytest
from migrations.migrate_schema import run_migrations


class TestMigrationsIdempotent:
    """Test that migrations can be run multiple times without errors or data loss."""

    def test_migrations_run_idempotently(self):
        """Verify migrations can be run multiple times on the same database without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            os.environ["DB_PATH"] = db_path

            # First run - create all tables
            run_migrations()

            # Verify initial schema is created
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables_first = {row[0] for row in cursor.fetchall()}
            conn.close()

            assert "schema_migrations" in tables_first
            assert "admin_users" in tables_first
            assert "swaps" in tables_first
            assert "wallet_actions" in tables_first

            # Insert test data
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
                ("testuser", "hash123"),
            )
            conn.commit()

            # Verify data exists
            cursor = conn.execute("SELECT COUNT(*) FROM admin_users")
            initial_count = cursor.fetchone()[0]
            assert initial_count == 1
            conn.close()

            # Second run - migrations should skip already applied migrations
            run_migrations()

            # Verify schema is unchanged
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables_second = {row[0] for row in cursor.fetchall()}

            assert tables_first == tables_second, "Schema changed on second migration run"

            # Verify test data is preserved
            cursor = conn.execute("SELECT COUNT(*) FROM admin_users")
            final_count = cursor.fetchone()[0]
            assert (
                final_count == initial_count
            ), "Data was lost or modified on second migration run"

            cursor = conn.execute("SELECT username FROM admin_users LIMIT 1")
            username = cursor.fetchone()[0]
            assert username == "testuser", "Test data was corrupted"

            conn.close()

            # Third run - extra safety check
            run_migrations()

            # Verify everything still intact
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM admin_users")
            third_count = cursor.fetchone()[0]
            assert third_count == final_count, "Data lost on third migration run"

            # Verify migration tracking is correct
            cursor = conn.execute("SELECT COUNT(*) FROM schema_migrations")
            migration_count = cursor.fetchone()[0]
            assert migration_count > 0, "No migrations recorded"

            conn.close()

    def test_wallet_actions_columns_exist(self):
        """Verify wallet_actions table has all required columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            os.environ["DB_PATH"] = db_path

            run_migrations()

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            # Get table schema
            cursor = conn.execute("PRAGMA table_info(wallet_actions)")
            columns = {row["name"] for row in cursor.fetchall()}

            # Verify all expected columns exist
            expected_columns = {
                "id",
                "action_type",
                "coin",
                "purpose",
                "amount",
                "address",
                "txid",
                "performed_by",
                "ip_address",
                "created_at",
                "details",
                "status",
                "error_code",
            }

            assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

            conn.close()
