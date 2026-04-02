# OrdexSwap Release Roadmap

**Last Updated**: April 2, 2026  
**Current Status**: v0.9.1 → v1.0.0 GA (Ready for Release)  
**Target**: v1.0.0 GA with security hardening & CI/CD

---

## Release Status Overview

| Milestone | Status | Progress | Blockers |
|-----------|--------|----------|----------|
| **v0.9.0-rc1** | READY | 100% | None |
| **v1.0.0 GA** | READY | 95% | CI/CD pipeline (optional) |
| **v1.1.0** | PLANNED | 0% | Features: notifications, monitoring |
| **v2.0.0** | FUTURE | 0% | Multi-coin, scaling |

---

## v1.0.0 GA - Remaining Tasks

### Must Complete Before Release

- [x] CSRF protection implemented & tested on all admin endpoints
- [x] Address validation for wallet withdrawals
- [x] Circuit breaker for abnormal swap ratios
- [x] Stats include all swap statuses (cancelled, timed_out, failed)
- [x] User swap tracking endpoint
- [x] Security documentation (SECURITY.md, OPERATIONS.md)
- [x] All tests passing (178 tests)
- [ ] Tag v1.0.0 release
- [ ] Publish release notes

### Optional (Post-Release OK)

- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Load testing baseline
- [ ] CONTRIBUTING.md
- [ ] API specification (OpenAPI/Swagger)

---

## Completed: Security Hardening

**Status**: [COMPLETE]

- [x] Credential masking in structured logging
- [x] Debug mode verification (disabled in production)
- [x] Error handling (non-leaking responses)
- [x] SECURITY.md published
- [x] CSRF tokens on all admin state-changing endpoints
- [x] Input validation on admin endpoints
- [x] Address validation for withdrawals
- [x] Circuit breaker protection

---

## v1.0.0 GA Success Criteria

### Must-Haves (Release Blocking)
```
✅ All pytest tests pass (178 tests)
✅ CSRF protection implemented on admin endpoints
✅ No hardcoded secrets in code
✅ Debug mode disabled in production
✅ SECURITY.md documented
✅ OPERATIONS.md published
✅ Docker build succeeds without warnings
✅ Backup/restore tested end-to-end
✅ Health check passes on startup
⬜ Git tag v1.0.0 created
```

### Should-Haves (Strongly Recommended)
```
✅ Incident runbook created & tested
✅ Monitoring setup documented
✅ Code coverage report generated (54%+)
⬜ CI/CD pipeline passing all checks (optional)
⬜ API documentation current (optional)
```

### Nice-to-Haves (Post-Release OK)
```
[NICE] Email notifications
[NICE] Webhook support
[NICE] Multi-language UI (i18n)
[NICE] Prometheus metrics export
[NICE] Terraform/Ansible IaC templates
```

---

## v1.1.0 Roadmap (Post-Release Features)

### Feature Tier 1: Notifications & Integration (High Priority)

| Feature | Purpose |
|---------|---------|
| **Email Notifications** | Alert admins & users on swap events |
| **Webhook Support** | External system integration |
| **API Key Auth** | Rate-limit quotas per client |
| **User History API** | Allow clients to retrieve swap history |

### Feature Tier 2: Observability & Monitoring (Medium Priority)

| Feature | Purpose |
|---------|---------|
| **Prometheus Metrics** | Performance monitoring & alerting |
| **ELK Integration** | Centralized logging & analysis |
| **Dashboard** | Admin analytics & swap volume trends |
| **Grafana Dashboards** | Visual metric display |

### Feature Tier 3: Frontend Enhancement (Medium Priority)

| Feature | Purpose |
|---------|---------|
| **Multi-language (i18n)** | Localization support |
| **PWA / Offline Mode** | Installable app, offline capability |
| **Mobile Responsiveness** | Improved mobile UX |
| **Theme Toggle** | Dark/light mode support |
| **Hardware Wallet** | Ledger / Trezor integration |

### Feature Tier 4: Scaling & HA (Lower Priority)

| Feature | Purpose |
|---------|---------|
| **PostgreSQL Migration** | Replace SQLite for production |
| **Multi-Region HA** | Active-active replication |
| **Redis Caching** | Improve price history performance |
| **Kubernetes Support** | Container orchestration templates |
| **Helm Charts** | Package manager integration |

---

## v2.0.0 Vision

**Strategic Goals**:
- [ ] Multi-coin pair support (OXC/OXG + future coins)
- [ ] Sidecar architecture for scalability
- [ ] Multi-region deployment
- [ ] Advanced fee structures (tiered, volume-based)
- [ ] User loyalty/referral system
- [ ] Mobile app (React Native)
- [ ] Hardware wallet support (Ledger, Trezor)

---

## Known Gaps & Technical Debt

### Security Debt
- [x] CSRF token implementation
- [x] Address validation for withdrawals
- [x] Circuit breaker protection
- [ ] Debug mode hardening verification
- [ ] Error message sanitization
- [ ] Input validation schema on admin endpoints
- [ ] Backup encryption support
- [ ] TLS for internal service communication

### Testing Debt
- [ ] Security testing (OWASP)
- [ ] Chaos testing (RPC failures)
- [ ] UI test automation (Playwright expansion)
- [ ] Performance benchmarks

### Infrastructure Debt
- [ ] CI/CD automation (GitHub Actions or similar)
- [ ] Database: SQLite → PostgreSQL path for HA
- [ ] Container registry setup (ECR, Docker Hub)
- [ ] Monitoring & alerting system
- [ ] Log aggregation (ELK stack or similar)

### Documentation Debt
- [x] SECURITY.md (threat model, hardening)
- [x] OPERATIONS.md (runbook, incident response)
- [ ] CONTRIBUTING.md (git workflow, PR review)
- [ ] API specification (OpenAPI/Swagger)
- [ ] Architecture decision records (ADRs)

---

## References

- [docs/TODO.md](./TODO.md) - Feature backlog & improvements
- [docs/DEPLOY.md](./DEPLOY.md) - Production deployment guide
- [docs/TESTING.md](./TESTING.md) - Testing procedures
- [docs/BACKUPS.md](./BACKUPS.md) - Backup & restore system
- [docs/SECURITY.md](./SECURITY.md) - Security policy, threat model, hardening guide
- [CHANGELOG.md](../CHANGELOG.md) - Version history, breaking changes, migration guides
- [AGENTS.md](../AGENTS.md) - Repository development guidelines

---

**Last Updated**: April 2, 2026  
**Next Step**: Tag v1.0.0 release