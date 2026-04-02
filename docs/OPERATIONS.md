# OrdexSwap Operations Guide

**Last Updated**: April 2, 2026  
**Purpose**: Deployment, monitoring, and troubleshooting procedures for OrdexSwap production environment.

---

## Production Deployment

### Standard Deployment Procedure

1. **Build and deploy on development machine:**
   ```bash
   ./scripts/deploy.sh
   ```

2. **Pull and restart on production server (ordexswap.online):**
   ```bash
   ssh user@ordexswap.online
   cd /opt/ordex-swap/
   docker compose -f docker-compose.prod.yml up -d --build
   ```

3. **Monitor startup logs:**
   ```bash
   docker logs -f ordex-swap-ordex-swap-1
   ```

4. **Verify health endpoint:**
   ```bash
   curl https://ordexswap.online/health
   ```

5. **Run validation tests:**
   ```bash
   # Run Playwright UI tests
   cd ui-tests && npm test
   
   # Run E2E HTTP tests
   cd app && python -m pytest tests/test_e2e_http.py -v
   ```

---

## Monitoring

### Health Check

```bash
curl https://ordexswap.online/health
```

Expected response:
```json
{"success": true, "data": {"status": "healthy", "service": "ordex-swap", "testing_mode": false}}
```

### Service Status

```bash
# Check container status
docker ps

# View logs
docker logs ordex-swap-ordex-swap-1 --tail 100

# Follow logs in real-time
docker logs -f ordex-swap-ordex-swap-1
```

### Admin Dashboard

Access the admin interface at: https://ordexswap.online/admin.html

---

## Backup Procedures

See [docs/BACKUPS.md](BACKUPS.md) for complete backup and restore procedures.

### Quick Backup
```bash
docker exec ordex-swap-ordex-swap-1 python backup.py
```

### Verify Backup
```bash
ls -la app/backups/
```

---

## Troubleshooting

### Common Issues

#### Service Won't Start
1. Check logs: `docker logs ordex-swap-ordex-swap-1`
2. Verify environment variables in `.env`
3. Ensure daemon binaries are in `app/data/bin/`

#### Swap Not Processing
1. Check wallet connectivity: Admin Dashboard → Wallets
2. Verify daemon status: `docker exec ordex-swap-ordex-swap-1 ps aux | grep ordex`
3. Check price oracle status

#### Database Issues
1. Verify SQLite file exists: `ls -la app/data/ordex.db`
2. Check migrations: `docker exec ordex-swap-ordex-swap-1 python -m migrations.runner`
3. Restore from backup if needed

### Rollback Procedure

```bash
# Stop current deployment
docker compose -f docker-compose.prod.yml down

# Restore previous version (if git tag available)
git checkout v0.9.0
./scripts/deploy.sh

# On production server:
cd /opt/ordex-swap/
git checkout v0.9.0
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Incident Response

### Critical Issues

1. **Service Down**: Check Docker daemon, restart container
2. **Funds at Risk**: Disable swaps immediately via Admin → Swap Control
3. **Suspicious Activity**: Check audit log, freeze service

### Emergency Contacts

- Development Team: [contact info]
- On-Call: [contact info]

---

## Security Checklist

Before production deployment:

- [ ] `DEBUG=false` in production environment
- [ ] `TESTING_MODE=false` in production
- [ ] `RATE_LIMIT_ENABLED=true`
- [ ] Strong admin password set
- [ ] TLS/SSL configured (via reverse proxy)
- [ ] Backups verified working
- [ ] Health check passing

---

**Next Review**: Weekly (Every Monday)
