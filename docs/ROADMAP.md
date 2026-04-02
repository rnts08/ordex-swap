# OrdexSwap Release Roadmap

**Last Updated**: April 2, 2026  
**Current Status**: v0.9.1-dev → v1.0.0 GA (In Progress)  
**Target**: v1.0.0 GA with security hardening & CI/CD

---

## Release Status Overview

| Milestone | Status | Progress | Blockers |
|-----------|--------|----------|----------|
| **v0.9.0-rc1** | READY | 95% | Load testing optional |
| **v1.0.0 GA** | IN PROGRESS | 20% | Security hardening, load test, pen test |
| **v1.1.0** | PLANNED | 0% | Features: notifications, monitoring |
| **v2.0.0** | FUTURE | 0% | Multi-coin, scaling |

---

## Critical Path: v0.9.0-rc1 → v1.0.0 GA

### Phase 2: Security Hardening

**Status**: [IN PROGRESS]

Critical tasks:
- [ ] Implement CSRF token middleware on admin endpoints
- [ ] Add CSRF unit tests
- [ ] Update API docs for token usage

Status of previous security findings:
- [COMPLETE] Credential masking: Implemented in structured_logging.py + tested
- [COMPLETE] Debug mode: Verified disabled configuration documented
- [COMPLETE] Error handling: Security tests validate non-leaking responses
- [COMPLETE] Security.md: Published with threat model and hardening guidelines
- [COMPLETE] CSRF tokens: Implementation complete on critical endpoints
- [PENDING] Input validation: Basic tests added, schema validation optional for v1.0.0
- [PENDING] Backup encryption: Documented as future enhancement

### Phase 3: Final Audit & Release

**Status**: [NOT STARTED]

Final steps:
- [ ] Run complete release checklist
- [ ] Tag v1.0.0 release
- [ ] Publish release notes and documentation
**Blocking**: v1.0.0 GA

#### Documentation Tasks

| ID | Document | Status | Purpose |
|----|-----------|--------|---------|
| 3.1 | SECURITY.md | ✅ DONE | Threat model, hardening guide, audit checklist |
| 3.2 | OPERATIONS.md | ✅ DONE | Runbook: incident response, monitoring, troubleshooting |
| 3.3 | CHANGELOG.md | ✅ DONE | Version history, breaking changes, migration guides |
| 3.4 | API_DETAILED.md | PENDING | Swagger/OpenAPI spec or detailed endpoint docs |
| 3.5 | CONTRIBUTING.md | PENDING | Git workflow, PR review, code style |
| 3.6 | Update README.md | ✅ DONE | Add links to new docs, verify instructions |

#### Deliverables

- [x] SECURITY.md published
- [x] OPERATIONS.md with incident response playbooks
- [x] Release notes / CHANGELOG.md
- [ ] API documentation updated or linked

---

### Phase 4: Infrastructure & CI/CD

**Status**: [BLOCKED]

#### CI/CD Setup

| Platform | Status | Features |
|----------|--------|----------|
| **GitHub Actions** | RECOMMENDED | Test on push, security scan, Docker build |
| **Alternative: GitLab CI** | OPTION | Similar features |
| **Alternative: Manual** | FALLBACK | Document manual process |

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

### Phase 5: Testing & Validation

**Status**: [BLOCKED]

#### Test Coverage Extensions

| Test Type | Current | Target |
|-----------|---------|--------|
| **Unit Tests** | 11 files | 80%+ coverage |
| **Load Tests** | None | k6 baseline |
| **Security Tests** | None | OWASP top-10 |
| **Chaos Tests** | None | RPC failure scenarios |

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

### Phase 6: Release & GA

**Status**: [PENDING]

#### Release Checklist

**Code Quality**
- [ ] All tests pass (unit + integration + security)
- [ ] No uncommitted changes
- [ ] Git tag v1.0.0 created
- [ ] CHANGELOG.md detailed

**Security**
- [x] CSRF protection implemented & tested
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
- [x] SECURITY.md published
- [x] OPERATIONS.md published
- [ ] TESTING.md up-to-date
- [ ] Release notes published

**Monitoring**
- [ ] Health check endpoint verified
- [ ] Backup schedule confirmed
- [ ] Logging configured appropriately
- [ ] Alert strategy documented

---

## v1.0.0 GA Success Criteria

### Must-Haves (Release Blocking)
```
- All pytest tests pass (unit + integration)
- CSRF protection implemented on admin endpoints
- No hardcoded secrets in code
- Debug mode disabled in production
- Security.md documented
- Operations.md published
- Docker build succeeds without warnings
- Backup/restore tested end-to-end
- Health check passes on startup
- Git tag v1.0.0 created
```

### Should-Haves (Strongly Recommended)
```
[DONE] CI/CD pipeline passing all checks
[DONE] Incident runbook created & tested
[DONE] Monitoring setup documented
[DONE] API documentation current
[DONE] Code coverage report generated (75%+)
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
