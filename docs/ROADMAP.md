# OrdexSwap Release Roadmap

**Last Updated**: March 31, 2026  
**Current Status**: v0.9.0-dev (9 uncommitted files ready for pre-release staging)  
**Target**: v1.0.0 GA with security hardening & CI/CD

---

## Release Status Overview

| Milestone | Status | Target Date | Blockers |
|-----------|--------|-------------|----------|
| **v0.9.0-rc1** | 🟡 Staging | Week of Apr 7 | Commit & security review |
| **v1.0.0 GA** | 🔴 Blocked | Week of Apr 21 | CSRF fixes, CI/CD, security audit |
| **v1.1.0** | 🟢 Planned | Week of May 19 | Features: notifications, webhooks, monitoring |
| **v2.0.0** | 🟢 Future | Q3 2026 | Multi-coin, sidecar architecture, scaling |

---

## Critical Path: v0.9.0-rc1 → v1.0.0 GA

### Phase 1: Code Staging & Pre-Release (Target: Apr 7)

**Status**: 🟡 In Progress  
**Effort**: 8 hours  

#### Tasks

| ID | Task | Owner | Effort | Priority |
|----|------|-------|--------|----------|
| 1.1 | Review & commit uncommitted changes (swap_engine, api, admin.html, index_mm.html) | Dev | 2h | 🔴 Critical |
| 1.2 | Clarify purpose of index_mm.html (document or deprecate) | Dev | 1h | 🔴 Critical |
| 1.3 | Create git tag v0.9.0-rc1 | Dev | 15m | 🔴 Critical |
| 1.4 | Create CHANGELOG.md documenting changes | Dev | 1h | 🟠 High |
| 1.5 | Update AGENTS.md with test command examples | Dev | 30m | 🟡 Medium |
| 1.6 | Run full test suite locally | QA | 1h | 🔴 Critical |
| 1.7 | Test Docker build & stack startup | QA | 1h | 🔴 Critical |
| 1.8 | Verify no secrets in git history | Security | 30m | 🔴 Critical |

---

### Phase 2: Security Hardening (Target: Apr 14)

**Status**: 🔴 Blocked  
**Effort**: 12 hours  
**Blocking**: v1.0.0 GA

#### Critical Security Fixes

| ID | Vulnerability | CVSS | Fix | Effort |
|----|---------------|----|-----|--------|
| 2.1 | CSRF on admin endpoints | 7.5 | Add CSRF token middleware to Flask; validate POST/PUT/DELETE | 2h |
| 2.2 | Debug mode potential exposure | 6.5 | Verify DEBUG=False in wsgi.py + gunicorn config; add test | 1h |
| 2.3 | Hardcoded admin password in .env.example | 5.4 | Force password change on first run; update docs | 1h |
| 2.4 | Error responses leak sensitive info | 5.5 | Audit all error responses; add credential masking | 2h |
| 2.5 | No input validation on admin endpoints | 5.5 | Add request validation schema; test injection | 3h |
| 2.6 | Backup files unencrypted | 4.0 | Add optional GPG encryption; document | 2h |
| 2.7 | RPC credentials in logs | 5.0 | Implement credential masking in structured_logging | 1h |

#### Deliverables

- [ ] Create `docs/SECURITY.md` with threat model, mitigations, audit checklist
- [ ] CSRF token implementation & tests
- [ ] Debug mode verification & documentation
- [ ] Security test suite (OWASP top-10 basic coverage)

---

### Phase 3: Operations & Documentation (Target: Apr 18)

**Status**: 🔴 Blocked  
**Effort**: 8 hours  
**Blocking**: v1.0.0 GA

#### Documentation Tasks

| ID | Document | Owner | Effort | Purpose |
|----|-----------|-------|--------|---------|
| 3.1 | SECURITY.md | Security | 2h | Threat model, hardening guide, audit checklist |
| 3.2 | OPERATIONS.md | Ops | 2h | Runbook: incident response, monitoring, troubleshooting |
| 3.3 | CHANGELOG.md | Dev | 1h | Version history, breaking changes, migration guides |
| 3.4 | API_DETAILED.md (optional) | Dev | 1.5h | Swagger/OpenAPI spec or detailed endpoint docs |
| 3.5 | CONTRIBUTING.md | Dev | 1h | Git workflow, PR review, code style |
| 3.6 | Update README.md | Dev | 30m | Add links to new docs, verify instructions |

#### Deliverables

- [ ] SECURITY.md published
- [ ] OPERATIONS.md with incident response playbooks
- [ ] Release notes / CHANGELOG.md
- [ ] API documentation updated or linked

---

### Phase 4: Infrastructure & CI/CD (Target: Apr 21)

**Status**: 🔴 Blocked  
**Effort**: 6 hours  

#### CI/CD Setup

| Platform | Status | Owner | Effort | Features |
|----------|--------|-------|--------|----------|
| **GitHub Actions** | 🟡 Recommended | DevOps | 4h | Test on push, security scan, Docker build |
| **Alternative: GitLab CI** | 🟢 Option | DevOps | 4h | Similar features |
| **Alternative: Manual** | 🟢 Fallback | Ops | 0h | Document manual process |

**Actions Workflow**:
```yaml
on: [push, pull_request]
jobs:
  test:
    - Lint (ruff, bandit)
    - Unit tests (pytest)
    - Docker build
    - Security scan (pip-audit, SAST)
  
  release:
    - Tag creation triggers automated build + publish
    - Generate release notes
```

#### Deliverables

- [ ] `.github/workflows/test.yml` created
- [ ] `.github/workflows/release.yml` created
- [ ] Pre-commit hooks documented
- [ ] Security scanning enabled (Bandit, pip-audit)

---

### Phase 5: Testing & Validation (Target: Apr 21)

**Status**: 🔴 Blocked  
**Effort**: 10 hours  

#### Test Coverage Extensions

| Test Type | Current | Target | Effort | Owner |
|-----------|---------|--------|--------|-------|
| **Unit Tests** | 11 files | 80%+ coverage | 2h | QA |
| **Load Tests** | None | k6 baseline | 3h | QA |
| **Security Tests** | None | OWASP top-10 | 3h | Security |
| **Chaos Tests** | None | RPC failure scenarios | 2h | QA |

**Test Commands**:
```bash
# Full test suite
python -m pytest app/tests/ -v --cov=app/swap-service

# Load test
k6 run tests/load-test.js

# Security scan
bandit -r app/swap-service/
pip-audit
```

#### Deliverables

- [ ] Load test script (k6) + baseline report
- [ ] Security test checklist + manual audit results
- [ ] Coverage report (target: 75%+)
- [ ] Chaos test scenarios documented

---

### Phase 6: Release & GA (Target: Apr 21)

**Status**: 🔴 Pending  
**Effort**: 2 hours  

#### Release Checklist

**Code Quality**
- [ ] All tests pass (unit + integration + security)
- [ ] No uncommitted changes
- [ ] Git tag v1.0.0 created
- [ ] CHANGELOG.md detailed

**Security**
- [ ] CSRF protection implemented & tested
- [ ] Debug mode verified disabled
- [ ] Rate limiting verified active
- [ ] Credentials masked in logs
- [ ] No secrets in code/history

**Infrastructure**
- [ ] Docker images built & tagged
- [ ] docker-compose.prod.yml verified
- [ ] Daemon binaries placed in data/bin/
- [ ] Environment template (.env.example) reviewed

**Documentation**
- [ ] README.md instructions tested
- [ ] DEPLOY.md deployment steps verified
- [ ] SECURITY.md published
- [ ] OPERATIONS.md published
- [ ] TESTING.md up-to-date
- [ ] Release notes published

**Monitoring**
- [ ] Health check endpoint verified
- [ ] Backup schedule confirmed
- [ ] Logging configured appropriately
- [ ] Alert strategy documented

#### Release Tasks

| Task | Owner | Effort | Deadline |
|------|-------|--------|----------|
| Final security audit | Security | 2h | Apr 20 |
| Run full deployment test | Ops | 1.5h | Apr 20 |
| Create release notes | Dev | 1h | Apr 20 |
| Tag v1.0.0 & push | Dev | 15m | Apr 21 |
| Publish release on GitHub | Dev | 15m | Apr 21 |
| Notify stakeholders | Product | 30m | Apr 21 |

---

## v1.0.0 GA Success Criteria

### Must-Haves (Release Blocking)
```
✓ All pytest tests pass (unit + integration)
✓ CSRF protection implemented on admin endpoints
✓ No hardcoded secrets in code
✓ Debug mode disabled in production
✓ Security.md documented
✓ Operations.md published
✓ Docker build succeeds without warnings
✓ Backup/restore tested end-to-end
✓ Health check passes on startup
✓ Git tag v1.0.0 created
```

### Should-Haves (Strongly Recommended)
```
✓ CI/CD pipeline passing all checks
✓ Load testing baseline established
✓ Incident runbook created & tested
✓ Monitoring setup documented
✓ API documentation current
✓ Code coverage report generated (75%+)
```

### Nice-to-Haves (Post-Release OK)
```
✓ Email notifications
✓ Webhook support
✓ Multi-language UI (i18n)
✓ Prometheus metrics export
✓ Terraform IaC templates
```

---

## v1.1.0 Roadmap (Post-Release Features)

**Target**: Week of May 19, 2026  
**Effort**: 8-10 weeks (distributed)

### Feature Tier 1: Notifications & Integration (High Priority)

| Feature | Effort | Owner | Q2 2026 | Purpose |
|---------|--------|-------|---------|---------|
| **Email Notifications** | 3w | Backend | May 19 | Alert admins & users on swap events |
| **Webhook Support** | 2w | Backend | May 26 | External system integration |
| **API Key Auth** | 1w | Backend | Jun 2 | Rate-limit quotas per client |
| **User History API** | 1w | Backend | Jun 2 | Allow clients to retrieve swap history |

### Feature Tier 2: Observability & Monitoring (Medium Priority)

| Feature | Effort | Owner | Q2 2026 | Purpose |
|---------|--------|-------|---------|---------|
| **Prometheus Metrics** | 2w | DevOps | May 19 | Performance monitoring & alerting |
| **ELK Integration** | 2w | DevOps | Jun 2 | Centralized logging & analysis |
| **Dashboard** | 2w | Frontend | Jun 9 | Admin analytics & swap volume trends |
| **Grafana Dashboards** | 1w | DevOps | Jun 16 | Visual metric display |

### Feature Tier 3: Frontend Enhancement (Medium Priority)

| Feature | Effort | Owner | Q2 2026 | Purpose |
|---------|--------|-------|---------|---------|
| **Multi-language (i18n)** | 2w | Frontend | May 26 | Localization support |
| **PWA / Offline Mode** | 2w | Frontend | Jun 2 | Installable app, offline capability |
| **Mobile Responsiveness** | 1w | Frontend | May 26 | Improved mobile UX |
| **Theme Toggle** | 1w | Frontend | Jun 9 | Dark/light mode support |
| **Hardware Wallet** | 3w | Backend | Jun 16 | Ledger / Trezor integration |

### Feature Tier 4: Scaling & HA (Lower Priority)

| Feature | Effort | Owner | Q3 2026 | Purpose |
|---------|--------|-------|---------|---------|
| **PostgreSQL Migration** | 2w | DevOps | Jul | Replace SQLite for production |
| **Multi-Region HA** | 3w | DevOps | Aug | Active-active replication |
| **Redis Caching** | 1w | Backend | Jul | Improve price history performance |
| **Kubernetes Support** | 2w | DevOps | Aug | Container orchestration templates |
| **Helm Charts** | 1w | DevOps | Aug | Package manager integration |

---

## v2.0.0 Vision (Q3+ 2026)

**Strategic Goals**:
- [ ] Multi-coin pair support (OXC/OXG + future coins)
- [ ] Sidecar architecture for scalability
- [ ] Multi-region deployment
- [ ] Advanced fee structures (tiered, volume-based)
- [ ] User loyalty/referral system
- [ ] Mobile app (React Native)
- [ ] Hardware wallet support (Ledger, Trezor)

**Effort**: 12-16 weeks  
**Resources**: 2 backend engineers, 1 frontend engineer, 1 DevOps engineer

---

## Known Gaps & Technical Debt

### Security Debt (v0.9.0 → v1.0.0)
- [ ] CSRF token implementation
- [ ] Debug mode hardening verification
- [ ] Error message sanitization
- [ ] Input validation schema on admin endpoints
- [ ] Backup encryption support
- [ ] TLS for internal service communication

### Testing Debt
- [ ] Load testing baseline
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
- [ ] SECURITY.md (threat model, hardening)
- [ ] OPERATIONS.md (runbook, incident response)
- [ ] CONTRIBUTING.md (git workflow, PR review)
- [ ] API specification (OpenAPI/Swagger)
- [ ] Architecture decision records (ADRs)

---

## Dependency Matrix

```
v1.0.0 GA
├─ Phase 1: Code Staging (Apr 7)
│  └─ Phase 2: Security Hardening (Apr 14)
│     └─ Phase 3: Documentation (Apr 18)
│        └─ Phase 4: CI/CD Infrastructure (Apr 21)
│           └─ Phase 5: Testing & Validation (Apr 21)
│              └─ Phase 6: Release (Apr 21)

v1.1.0 Features (May 19)
├─ Notifications (email, webhooks)
├─ Monitoring (Prometheus, ELK, Grafana)
├─ Frontend enhancements (i18n, PWA, mobile)
└─ Scaling prep (PostgreSQL, Redis, HA)

v2.0.0 Vision (Q3+ 2026)
├─ Multi-coin support
├─ Sidecar architecture
├─ Multi-region HA
└─ Mobile app + hardware wallets
```

---

## Communication & Stakeholder Updates

### Weekly Standups
- **v0.9.0 Phase** (Apr 1-7): 3x weekly sync on blockers
- **v1.0.0 Phase** (Apr 7-21): 2x weekly security + infrastructure reviews
- **v1.1.0 Phase** (May onward): 1x weekly feature planning

### Release Notes Template
```markdown
# v1.0.0 - Initial GA Release

**Release Date**: April 21, 2026

## What's New
- ✨ Production WSGI server with Gunicorn
- ✨ Admin panel with audit & reconciliation
- ✨ Automated backup & restore system
- ✨ Docker containerization for easy deployment

## Security
- 🔒 CSRF token protection on admin endpoints
- 🔒 Credential masking in logs
- 🔒 Rate limiting on public endpoints
- 🔒 Debug mode validated disabled

## Breaking Changes
- None (first stable release)

## Migration Guide
See docs/DEPLOY.md for production deployment.

## Known Issues / Future Work
See docs/TODO.md for full feature backlog.
```

---

## References

- [docs/TODO.md](./TODO.md) - Feature backlog & improvements
- [docs/DEPLOY.md](./DEPLOY.md) - Production deployment guide
- [docs/TESTING.md](./TESTING.md) - Testing procedures
- [docs/BACKUPS.md](./BACKUPS.md) - Backup & restore system
- [docs/SECURITY.md](./SECURITY.md) - *To be created*
- [docs/OPERATIONS.md](./OPERATIONS.md) - *To be created*
- [AGENTS.md](../AGENTS.md) - Repository development guidelines

---

**Last Updated**: March 31, 2026  
**Next Review**: April 7, 2026 (v0.9.0-rc1 planning)
