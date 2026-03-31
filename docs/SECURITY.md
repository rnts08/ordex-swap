# Security Policy for OrdexSwap

**Last Updated**: March 31, 2026  
**Status**: v0.9.0 Pre-Release (Before GA)

This document outlines security practices, threat model, hardening measures, and incident response procedures for OrdexSwap.

---

## Table of Contents

1. [Security Standards & Baseline](#security-standards--baseline)
2. [Threat Model](#threat-model)
3. [Security Hardening](#security-hardening)
4. [Authentication & Authorization](#authentication--authorization)
5. [Input Validation & Injection Prevention](#input-validation--injection-prevention)
6. [Error Handling & Information Disclosure](#error-handling--information-disclosure)
7. [Cryptography & Secrets Management](#cryptography--secrets-management)
8. [Deployment Security](#deployment-security)
9. [Monitoring & Incident Response](#monitoring--incident-response)
10. [Audit Checklist](#audit-checklist)

---

## Security Standards & Baseline

OrdexSwap follows industry-standard security frameworks:

- **OWASP Top 10 (2021)** - Application security best practices
- **NIST Cybersecurity Framework** - Risk management baseline
- **CWE Top 25** - Common Weakness Enumeration mitigation

### Verified Baseline Controls

Current security testing confirms:

- Rate limiting enabled on public endpoints (10/min, 60/hr for admin)
- Debug mode verified disabled in production
- Error messages sanitized (no file paths, line numbers, or stack traces in responses)
- Input validation implemented on all entry points
- Basic authentication enforced on admin endpoints
- Database queries use parameterized statements (no SQL injection)

---

## Threat Model

### High Priority Threats

1. **API Abuse & Denial of Service (DoS)**
   - Mitigated by: Rate limiting, request validation
   - Status: **MITIGATED**
   - Monitoring: Request rate logs, 429 responses tracked

2. **Unauthorized Admin Access**
   - Mitigated by: Basic auth on admin routes, IP logging
   - Status: **MITIGATED**
   - Monitoring: Failed auth attempts logged at WARN level

3. **Transaction Tampering**
   - Mitigated by: Input validation, parameterized SQL, swap record immutability
   - Status: **MITIGATED**
   - Monitoring: Audit log entries for all admin operations

4. **Information Disclosure via Error Messages**
   - Mitigated by: Error message sanitization, generic 500 responses
   - Status: **MITIGATED**
   - Testing: test_security.py verifies no sensitive data in errors

5. **Cross-Site Request Forgery (CSRF)**
   - Status: **UNIMPLEMENTED** (TODO: v1.0.0 requires implementation)
   - Mitigation plan: Token-based CSRF protection on state-changing endpoints

6. **SQL Injection**
   - Mitigated by: Parameterized queries via sqlite3
   - Status: **MITIGATED**
   - Testing: test_security.py validates input sanitization

### Medium Priority Threats

7. **Weak Credentials**
   - Mitigated by: Environment-based credential management (no hardcoding)
   - Status: **MITIGATED**
   - Best practice: Use strong random passwords (16+ chars, mixed case, symbols)

8. **Daemon RPC Exposure**
   - Mitigated by: RPC bound to 127.0.0.1, firewall rules
   - Status: **MITIGATED**
   - Deployment requirement: Never expose daemon ports publicly

9. **Wallet Private Key Exposure**
   - Mitigated by: Wallet files stored in daemon data directories with restricted permissions
   - Status: **MITIGATED**
   - Deployment requirement: Ensure data directory permissions (750)

10. **Race Conditions in Swap Settlement**
    - Mitigated by: Database locks, atomic transactions
    - Status: **MITIGATED**
    - Testing: Concurrency tests in test_swap.py

### Low Priority Threats

11. **Timing Attacks**
    - Status: **ACKNOWLEDGED** (out of scope for crypto library handling)
    - Mitigation: Rely on Python hashlib (immune to timing attacks)

12. **Side-Channel Attacks**
    - Status: **ACKNOWLEDGED** (hardware/OS level, out of scope)

---

## Security Hardening

### Application Hardening

#### 1. Request Rate Limiting

All public endpoints have rate limits configured via Flask-Limiter:

```python
@limiter.limit("10 per minute")  # Quote/swap creation
@limiter.limit("60 per hour")     # Price queries
@limiter.limit("600 per hour")    # Balance/status
```

**Verification**: `pytest tests/test_security.py -k rate_limiting`

#### 2. Input Validation

All user inputs validated before processing:

- Numeric amounts: Must be finite, non-negative, <= 999999999
- Coin pairs: Must be "OXC" or "OXG" exactly
- Addresses: Alphanumeric, 8-120 chars, no special chars (regex: `^[A-Za-z0-9_-]{8,120}$`)
- Status enums: Limited to valid swap states

**Verification**: `pytest tests/test_api_endpoints.py -k validates` or  `pytest tests/test_security.py -k validation`

#### 3. Error Handling

All error messages sanitized before sending to client:

```python
def sanitize_error_message(exception, fallback="An error occurred"):
    """Remove sensitive info from error messages."""
```

- No file paths in responses
- No line numbers or stack traces
- No SQL queries
- Generic "Price unavailable" instead of specific Oracle errors

**Verification**: `pytest tests/test_security.py -k error_sanitization`

#### 4. Debug Mode Verification

Debug mode forced OFF in production via `DEBUG=false` environment variable.

**Verification**: `pytest tests/test_security.py -k debug_mode`

#### 5. Structured Logging

Sensitive data (API keys, credentials) masked in logs via `StructuredLogger`:

```python
logger.info(f"Swap created: {swap_id}")  # OK
logger.info(f"Auth: {password}")         # MASKED
```

**Verification**: `pytest tests/test_structured_logging.py`

---

## Authentication & Authorization

### Admin Endpoint Protection

All admin endpoints (`/api/v1/admin/*`) require basic HTTP authentication:

```python
@require_admin_auth
def admin_operation():
    """Admin endpoints require username:password in Authorization header."""
```

**Credentials**: Environment variable based

```bash
ADMIN_USERNAME=swap
ADMIN_PASSWORD=<strong-random-password>
```

**Test Verification**:

```bash
pytest tests/test_api_endpoints.py::TestAdminEndpoints
```

### Public Endpoint Access

Public endpoints (`/api/v1/quote`, `/api/v1/swap`, etc.) available without authentication.

**Rate Limiting**: Applies to all endpoints (public and admin)

---

## Input Validation & Injection Prevention

### SQL Injection Prevention

All database queries use parameterized statements:

```python
# SAFE: Parameterized query
conn.execute("SELECT * FROM swaps WHERE swap_id = ?", (swap_id,))

# NEVER: String concatenation
conn.execute(f"SELECT * FROM swaps WHERE swap_id = '{swap_id}'")  # BAD!
```

**Verification**: `pytest tests/test_security.py::test_sql_injection`

### Cross-Site Scripting (XSS) Prevention

JSON responses never rendered as HTML. API returns JSON only.

**Input validation** prevents XSS payloads from entering database:

- Usernames: `^[A-Za-z0-9_-]{8,120}$` (no angle brackets)
- All string inputs validated against whitelist patterns

**Verification**: `pytest tests/test_security.py::test_xss_prevention`

### Command Injection Prevention

Daemon arguments built via list (not string concatenation):

```python
# SAFE: List of args (subprocess uses execvp internally)
subprocess.Popen(["/path/to/daemon", "-arg", value])

# NEVER: String concatenation
subprocess.Popen(f"/path/to/daemon -arg {value}", shell=True)  # BAD!
```

---

## Error Handling & Information Disclosure

### Generic Error Responses

Client errors (4xx) and server errors (5xx) return generic messages:

```json
{
  "success": false,
  "error": "An error occurred"
}
```

Internal errors never exposed to client.

### Logging Without Information Disclosure

Errors logged with full details for debugging:

```python
logger.error(f"Failed processing swap: {e}", exc_info=True)
```

But client sees:

```json
{
  "error": "Processing failed"
}
```

**Verification**: Log output and API response differ

---

## Cryptography & Secrets Management

### RPC Credentials

Daemon RPC credentials stored as environment variables (never in code):

```bash
OXC_RPC_USER=rpc_user
OXC_RPC_PASSWORD=<random-64-char-string>
OXG_RPC_USER=rpc_user2
OXG_RPC_PASSWORD=<random-64-char-string>
```

### Admin Credentials

Admin credentials also environment-based:

```bash
ADMIN_USERNAME=swap
ADMIN_PASSWORD=<random-32-char-string>
```

### No Secrets in Code

Verification: `grep -r "password\|secret\|key" --include="*.py" app/swap-service/ | grep -v "def\|#\|logger"`

Expected result: No hardcoded credentials

### TLS/HTTPS

**Note**: OrdexSwap API runs behind reverse proxy (Caddy) which handles TLS.

Deployment requirement: Always deploy with TLS in production.

---

## Deployment Security

### Docker Deployment Best Practices

1. **Image Building**:
   - Use minimal base images (python:3.12-slim)
   - No secrets in Dockerfile
   - Multi-stage builds where possible

2. **Container Runtime**:
   - Run as non-root user (uid:gid = 1000:1000)
   - Remove unnecessary capabilities
   - Use read-only root filesystem where possible

3. **Environment Configuration**:
   - Load secrets from `.env` files (never committed)
   - Use `python-dotenv` in development only
   - Production uses environment variable injection

### Network Security

1. **Port Exposure**:
   - API port (8080): Behind reverse proxy only
   - Daemon RPC ports (25173, 25465): localhost only
   - Database: localhost only

2. **Firewall Rules**:
   ```
   ALLOW 127.0.0.1:8080 -> 127.0.0.1:5000  (Caddy to Flask)
   ALLOW 127.0.0.1:5000 -> 127.0.0.1:25173 (Flask to OXC RPC)
   ALLOW 127.0.0.1:5000 -> 127.0.0.1:25465 (Flask to OXG RPC)
   DENY ALL outside traffic
   ```

### File Permissions

```bash
# Data directory (contains wallet files)
chmod 750 /app/data

# Configuration files
chmod 600 /app/.env

# Application code
chmod 755 /app
chmod 644 /app/swap-service/*.py
```

---

## Monitoring & Incident Response

### Security Monitoring

#### Metrics to Track

1. **Failed Authentication**:
   - Source: API logs
   - Alert threshold: > 10 failed attempts in 1 hour
   - Response: Check admin credentials, review access logs

2. **Rate Limit Exceeded**:
   - Source: Flask-Limiter
   - Alert threshold: > 100 429 responses in 1 hour
   - Response: May indicate DDoS, check IP reputation

3. **Error Rate**:
   - Source: Application logs
   - Alert threshold: > 5% 5xx errors
   - Response: Check logs, review recent changes

4. **Daemon Health**:
   - Source: Daemon manager status endpoint
   - Alert threshold: Any daemon down > 5 minutes
   - Response: Check daemon logs, restart if needed

#### Logging Configuration

All security events logged to `app.log` and stdout:

```python
logger.warning(f"Failed admin auth from {ip}: {username}")
logger.error(f"Input validation failed for {field}: {value}")
logger.info(f"Admin action {action} by {username} from {ip}")
```

### Incident Response Procedure

#### 1. Unauthorized Access Attempt

**Detection**: Multiple failed `require_admin_auth` checks

**Response**:
1. Review authentication logs: `grep "Failed admin auth" app.log`
2. Check IP addresses for patterns
3. Update `ADMIN_PASSWORD` if compromised
4. Review audit log for unauthorized actions

#### 2. Suspected SQL Injection Attack

**Detection**: Unusual characters in request logs, database errors

**Response**:
1. Review application logs for validation failures
2. Check database transaction logs
3. Verify no data corruption in swap records
4. Audit `admin_audit_log` table

#### 3. Rate Limit Abuse (Potential DDoS)

**Detection**: High 429 response rate, low-entropy source IPs

**Response**:
1. Identify attacking IP(s) from access logs
2. Implement IP-level firewall blocks (reverse proxy)
3. Consider stricter rate limits for affected endpoints
4. Monitor recovery over next hour

#### 4. Daemon Compromise or Malfunction

**Detection**: Daemon process terminated, RPC unreachable, suspicious transactions

**Response**:
1. Check daemon error logs
2. Inspect blockchain transaction history
3. Shut down service if suspicious activity detected
4. Run blockchain validation (`ordexcoind -reindex`)
5. Restart service after validation

---

## Security Audit Checklist

### Pre-Release v0.9.0 Audit (✓ = Complete)

- [x] All endpoints rate-limited
- [x] Debug mode disabled
- [x] Error messages sanitized
- [x] Input validation on all entry points
- [x] SQL injection prevention (parameterized queries)
- [x] Admin authentication working
- [x] No hardcoded credentials
- [x] Log files don't contain secrets
- [x] Structured logging configured
- [x] Unit tests for security controls (18 tests in test_security.py)
- [x] API endpoint tests (32 tests in test_api_endpoints.py)
- [x] Daemon manager lifecycle tests (16 tests in test_daemon_manager.py)

### For v1.0.0 GA Release

- [ ] CSRF token implementation & tests
- [ ] Automated security testing in CI/CD
- [ ] Penetration test (external security firm)
- [ ] OWASP dependency check (no known vulnerabilities)
- [ ] Security headers in reverse proxy (CSP, X-Frame-Options, etc.)
- [ ] Rate limit tuning based on load testing
- [ ] Incident response playbook documentation
- [ ] Security training for operations team

### For v1.1.0+ & Beyond

- [ ] OAuth2 support (optional, for advanced deployments)
- [ ] API key rotation mechanism
- [ ] Secrets rotation automation
- [ ] Enhanced audit logging
- [ ] Security event alerting integration
- [ ] Compliance (SOC2 audit trails)

---

## Contact & Reporting Security Issues

**Do not open public GitHub issues for security vulnerabilities.**

Report security concerns via email to: [contact info to be added]

Include:
- Clear description of vulnerability
- Steps to reproduce
- Impact assessment
- Proposed remediation (if any)

**Response SLA**: 24-48 hours acknowledgment, 7 days for security patches

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Mar 31, 2026 | Initial security policy document |

