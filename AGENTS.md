# Repository Guidelines

## Project Structure & Module Organization
- `app/` hosts the Python backend service and runtime assets.
  - `app/main.py` is the Flask entrypoint.
  - `app/swap-service/` contains core modules (swap engine, price oracle, RPC, history).
  - `app/tests/` contains pytest tests (e.g., `test_swap.py`).
- `frontend/` contains the static UI (`index.html`, `ordexnetwork.png`).
- `docs/` includes daemon and API reference material.

## Build, Test, and Development Commands
Run commands from `app/` unless noted.
- Always run in a virtual environment with `python3 -m venv .venv && source .venv/bin/activate` before running any pip install or other code.
- `pip install -r requirements.txt` installs backend dependencies.
- `TESTING_MODE=true python main.py` runs the API in testing mode (mocked wallets, no daemons).
- `python main.py` runs production mode (requires `ordexcoind` and `ordexgoldd` in `app/`).
- `python -m pytest tests/test_swap.py -v` runs the backend test suite.
- `docker-compose up -d --build` builds and runs the stack (serves UI on `http://localhost:8080/`, API proxied under `/api/`).

## Coding Style & Naming Conventions
- Python style: 4-space indentation, PEP 8 conventions, `snake_case` for functions/variables, `PascalCase` for classes.
- Keep modules focused on a single responsibility inside `app/swap-service/`.
- No formatter or linter is configured in-repo; if you add one, document it here.

## Testing Guidelines
- Test framework: pytest (see `app/requirements.txt`).
- Name tests `test_*.py` and use `test_*` functions.
- Prefer unit tests for swap logic and price calculations; add integration tests when touching API routes.

## Commit & Pull Request Guidelines
- Use a clear, conventional style like `feat: ...`, `fix: ...`, `chore: ...`.
- PRs should include: a concise summary, test results (or rationale if not run).

## Configuration & Security Notes
- Runtime config is via environment variables (see `README.md`), typically loaded with `python-dotenv`.
- Do not commit real RPC credentials or API keys; use local `.env` files for secrets.
