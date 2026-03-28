import os
import time
import sqlite3
import unittest
import requests
import subprocess

API_BASE = os.getenv("E2E_API_BASE", "http://localhost:8080")
DB_PATH = os.getenv(
    "E2E_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "ordex.db")
)
RUN_HTTP_E2E = os.getenv("E2E_HTTP", "").lower() in {"1", "true", "yes"}
ALLOW_DOCKER_EXEC = os.getenv("E2E_HTTP_DOCKER_EXEC", "1").lower() in {
    "1",
    "true",
    "yes",
}


class TestE2EHttp(unittest.TestCase):
    @unittest.skipUnless(RUN_HTTP_E2E, "Set E2E_HTTP=1 to run HTTP e2e tests")
    def test_http_swap_flow_and_db(self):
        # Wait for API to be healthy
        healthy = False
        for _ in range(30):
            try:
                health = requests.get(f"{API_BASE}/health", timeout=2)
                if health.ok:
                    healthy = True
                    break
            except requests.RequestException:
                time.sleep(1)

        if not healthy and ALLOW_DOCKER_EXEC:
            script_lines = [
                "import requests, time",
                "API_BASE = 'http://127.0.0.1:8000'",
                "for _ in range(30):",
                "    try:",
                "        r = requests.get(f'{API_BASE}/health', timeout=2)",
                "        if r.ok:",
                "            break",
                "    except Exception:",
                "        time.sleep(1)",
                "else:",
                "    raise SystemExit(2)",
                "status = requests.get(f'{API_BASE}/api/v1/status', timeout=5).json()",
                "if not status.get('success'):",
                "    raise SystemExit(3)",
                "payloads = [{'from': 'OXC', 'to': 'OXG', 'amount': 10}, {'from': 'OXG', 'to': 'OXC', 'amount': 5}]",
                "for p in payloads:",
                "    q = requests.post(f'{API_BASE}/api/v1/quote', json=p, timeout=10)",
                "    q.raise_for_status()",
                "    s = requests.post(f'{API_BASE}/api/v1/swap', json={**p, 'user_address': 'user_addr_123'}, timeout=10)",
                "    s.raise_for_status()",
            ]
            script = "\n".join(script_lines)
            code = subprocess.run(
                [
                    "docker",
                    "exec",
                    "bin-ordex-swap-1",
                    "python",
                    "-c",
                    script,
                ],
                text=True,
                capture_output=True,
            )
            if code.returncode != 0:
                if "permission denied" in code.stderr.lower():
                    raise unittest.SkipTest(
                        "Docker socket not accessible for HTTP fallback; "
                        "run with docker access or set E2E_API_BASE to a reachable host."
                    )
                self.fail(
                    f"API did not become healthy (docker exec fallback failed): {code.stderr}"
                )
            healthy = True

        if not healthy:
            raise unittest.SkipTest(
                "API not reachable from host; set E2E_API_BASE to a reachable URL."
            )

        status = requests.get(f"{API_BASE}/api/v1/status", timeout=5).json()
        self.assertTrue(status.get("success"))
        testing_mode = status["data"].get("testing_mode", False)

        def create_swap(from_coin, to_coin, amount):
            quote = requests.post(
                f"{API_BASE}/api/v1/quote",
                json={"from": from_coin, "to": to_coin, "amount": amount},
                timeout=10,
            )
            self.assertTrue(quote.ok, quote.text)

            resp = requests.post(
                f"{API_BASE}/api/v1/swap",
                json={
                    "from": from_coin,
                    "to": to_coin,
                    "amount": amount,
                    "user_address": f"user_{from_coin.lower()}_addr_123",
                },
                timeout=10,
            )
            self.assertTrue(resp.ok, resp.text)
            return resp.json()["data"]["swap_id"]

        swap_oxc = create_swap("OXC", "OXG", 10)
        swap_oxg = create_swap("OXG", "OXC", 5)

        if testing_mode:
            for swap_id in (swap_oxc, swap_oxg):
                confirm = requests.post(
                    f"{API_BASE}/api/v1/swap/{swap_id}/confirm",
                    json={"deposit_txid": "test_txid_http"},
                    timeout=10,
                )
                self.assertTrue(confirm.ok, confirm.text)

        # Ensure swaps are in DB
        for _ in range(30):
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    total = conn.execute("SELECT COUNT(*) FROM swaps").fetchone()[0]
                    completed = conn.execute(
                        "SELECT COUNT(*) FROM swaps WHERE status = ?",
                        ("completed",),
                    ).fetchone()[0]
                if total >= 2 and (not testing_mode or completed >= 2):
                    break
            except sqlite3.Error:
                pass
            time.sleep(1)
        else:
            self.fail("Swaps not recorded in DB")


if __name__ == "__main__":
    unittest.main()
