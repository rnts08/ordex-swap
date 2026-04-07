# OrdexSwap TODO - v1.0.x

**Last Updated**: April 6, 2026  
**Version**: v1.0.0 GA

---

## Quick Reference

| Area | Status |
|------|--------|
| Swap Flow | ✅ Complete |
| Admin UI | ✅ Complete |
| CSRF Protection | ✅ Complete |
| Circuit Breaker | ✅ Complete |
| Reconciliation | ⚠️ Needs e2e test verification |
| Liquidity Hold (both directions) | ⚠️ Needs e2e test verification |
| Admin Override Override | ⚠️ Needs e2e test verification |

---

## Priority 1: Testing & Verification

### Required Test Coverage

- [ ] **Liquidity Hold E2E** - Test that liquidity holds work for OXG→OXC swaps
- [ ] **Admin Override Override** - Verify admin status takes precedence over late deposit detection
- [ ] **Reconciliation E2E** - Test full reconciliation flow with mock wallet data

### Test Locations
- Unit tests: `app/tests/test_swap.py`
- E2E tests: `app/tests/test_e2e.py`
- Reconciliation: `app/tests/test_reconciliation.py`

---

## Known Gaps (Non-Critical)

### Test Coverage Areas (<60%)
- `price_history.py`: 34% - Background fetch, backfill logic untested
- `wallet_rpc.py`: 36% - Many RPC methods only have mock implementations
- `api.py`: 55% - Some admin endpoints need more tests
- `admin_service.py`: 54% - Wallet management partially tested

### Missing Features (Future)
1. **Swap Status Webhooks** - External notifications
2. **Email Notifications** - Admin alerts
3. **Export Functionality** - CSV export
4. **API Key Auth** - Programmatic access
5. **Batch Operations** - Bulk admin actions

---

## Configuration

All configurable values are in `app/swap-service/config.py`:
- `SWAP_FEE_PERCENT` (default: 1.0)
- `SWAP_MIN_AMOUNT` (default: 0.0001)
- `SWAP_MAX_AMOUNT` (default: 10000)
- `SWAP_EXPIRE_MINUTES` (default: 15)
- `CIRCUIT_BREAKER_RATIO` (default: 5.0)
- `SETTLEMENT_INTERVAL_SECONDS` (default: 60)

---

## References

- [ROADMAP.md](./ROADMAP.md) - Release timeline
- [SECURITY.md](./SECURITY.md) - Security policy
- [OPERATIONS.md](./OPERATIONS.md) - Operations runbook
- [CHANGELOG.md](../CHANGELOG.md) - Version history
