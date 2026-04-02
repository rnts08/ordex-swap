# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- CSRF token protection for admin wallet withdraw endpoint
- Frontend CSRF token fetching and inclusion in state-changing requests

### Changed
- Updated roadmap documentation with v1.0.0 timeline
- Updated TODO with security fixes completed

### Security
- CSRF tokens now required for wallet withdraw operations

---

## [v0.9.0] - 2026-03-31

### Added
- Complete testing suite (176+ tests passing)
- Daemon manager tests (20 tests)
- API endpoint tests (32 tests)
- Security test suite (18 OWASP-focused tests)
- Late deposit settlement tests
- Comprehensive security documentation (docs/SECURITY.md)
- CI/CD pipeline template (.github/workflows/ci.yml)
- Configurable rate limiting (RATE_LIMIT_ENABLED env var)
- Wallet actions audit trail

### Fixed
- Rate limiter automatically disabled in TESTING_MODE
- Playwright tests handling of production state
- Missing columns in wallet_actions table for old databases
- Entrypoint startup order (wallet daemons ready before service)
- Docker build context and paths
- Migrations folder included in Docker build
- Migrations idempotency

### Changed
- Migrated from Flask dev server to Gunicorn WSGI server
- Moved migrations to standalone scripts
- Added app directory to sys.path for migrations

### Security
- Credential masking in structured logging
- Security test suite covering OWASP Top 10
- Rate limiting on public endpoints
- Debug mode verification

---

## [v0.8.0] - 2026-03-20

### Added
- Admin dashboard with financial stats
- Swap reconciliation system
- Audit logging for all admin actions
- Wallet action tracking
- Late deposit handling and settlement

### Fixed
- Swap engine state management
- Delayed queue processing
- Price oracle fallback handling

### Security
- Admin authentication with Basic Auth
- Audit trail for all privileged operations

---

## [v0.7.0] - 2026-03-10

### Added
- Docker containerization
- Automated backup & restore system
- Health check endpoint
- Background price fetching

### Fixed
- Entry point script configuration
- Docker volume mounts for daemon binaries

---

## [v0.6.0] - 2026-02-28

### Added
- Basic admin interface
- Swap control (enable/disable swaps)
- Fee configuration
- Wallet management (rotate addresses)

---

## [v0.5.0] - 2026-02-15

### Added
- Initial public swap API
- Price oracle integration
- SQLite database for swap history

---

## [v0.1.0] - 2026-01-01

### Added
- Project initialization
- Initial swap engine prototype

---

## v0.9.0-rc1 → v0.9.0 Changelog (Full)

```
32e4650 Updated roadmap document
8cf48c0 fix: disable rate limiter automatically in TESTING_MODE
a7479aa fix: update playwright tests to handle production state and UI text variations
d9f2897 fix: add missing columns to wallet_actions table for old databases
aa353aa fix: fix entrypoint startup order - wallet daemons not ready yet
1fa7d98 fix: add entrypoint script to run migrations before gunicorn starts
0cbe0d2 feat: add configurable rate limiting with RATE_LIMIT_ENABLED env var
63dc687 chore: update admin password in Playwright tests and fix hardcoded localhost URLs
632dec0 fix: copy daemon binaries to app/data/bin so volume mount includes them in production
8a96ca0 fix: docker build context and paths for correct file copying
45ea6fa fix: use baseURL in wallet actions test instead of hardcoded localhost
f6f9119 fix: add migrations folder to Docker build
9300472 refactor: move migrations to standalone scripts like migrate_settings
8cb8d9d fix: add app directory to sys.path for migrations import
4c8494a chore: ensure all migrations are idempotent
0afde7f fix: always run migrations on service initialization
916a3e5 Some fixes to the backups
e17b655 feat: add daemon manager tests, security docs, and CI/CD template
7aa5ad8 docs: update roadmap with API endpoint test completion
7099525 fix: correct API endpoint test initialization and parameters
cff8f38 docs: update roadmap with completion status - 124 tests passing, security suite added
5adbbf2 feat: add comprehensive security test suite (18 tests)
a1f8c61 fix: update test_late_deposit_settle to expect RECONCILED status for late deposits
974a097 Added reconcilliation fixes for 0.9
8b6f2a9 Changed backend to use production wsgi server instead of flask dev server
```

---

## Migration Guides

### v0.8.0 → v0.9.0

1. Update environment variables:
   - `RATE_LIMIT_ENABLED=true` (set to false for testing)

2. Run migrations:
   ```bash
   docker-compose exec app python -m migrations.runner
   ```

3. Restart services:
   ```bash
   docker-compose restart
   ```

### v0.7.0 → v0.8.0

1. Database backup before upgrade (see docs/BACKUPS.md)

2. Run migrations:
   ```bash
   docker-compose exec app python -m migrations.migrate_schema
   docker-compose exec app python -m migrations.migrate_settings
   ```

---

## Known Issues

- CSRF protection only partially implemented (withdraw endpoint protected)
- Backup encryption not yet supported
- No TLS for internal service communication

---

## Upcoming (v1.0.0)

- Full CSRF protection on all admin endpoints
- Complete security audit
- Load testing baseline
- Production hardening

---

**Last Updated**: April 2, 2026