# Testing and Test Mode

## Run the application in test mode

1) Ensure test mode is enabled (pricing still uses live public tickers):

```bash
sed -i 's/^TESTING_MODE=.*/TESTING_MODE=true/' app/.env
```

2) Build and start the stack:

```bash
docker-compose up -d --build
```

3) Initialize/load wallets (idempotent):

```bash
docker exec ordex-swap-ordex-swap-1 /app/first-run.sh
```

4) Verify health:

```bash
curl -s http://localhost:8080/health
```

## Running tests locally (outside Docker)

### Python setup

```bash
cd app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Python unit + e2e tests

```bash
# Standard tests
source venv/bin/activate
python -m pytest tests/ -v

# With HTTP e2e tests
E2E_HTTP=1 python -m pytest tests/ -v
```

## Run the full test suite (Docker)

### 1) Build with tests included

```bash
BUILD_TEST=true docker-compose up -d --build
```

### 1.1) Initialize/load wallets (idempotent)

```bash
docker exec ordex-swap-ordex-swap-1 /app/first-run.sh
```

### 2) Run Python unit + e2e tests (inside container)

```bash
docker exec ordex-swap-ordex-swap-1 python -m pytest \
  tests/test_swap.py tests/test_admin.py tests/test_e2e.py -v
```

### 3) Run UI tests (Playwright from host)

```bash
cd ui-tests
npm install
npx playwright install
UI_BASE_URL=http://localhost:8080 npm test
```

## Notes

- `BUILD_TEST=false` omits `/app/tests` from the container image for cleaner production deploys.
- `first-run.sh` loads/creates the configured wallets and can be run multiple times safely. 
