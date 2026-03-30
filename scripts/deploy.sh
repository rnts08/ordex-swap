#!/bin/bash
set -e

SERVER="ordexswap.online"
USER="deploy"
DEPLOY_DIR="/opt/ordex-swap"

echo "Deploying to $SERVER..."

# Create remote directory
ssh $USER@$SERVER "mkdir -p $DEPLOY_DIR"

# Copy deployment files (excluding local-only files)
rsync -av --exclude='.git' \
    --exclude='docker-compose.yml' \
    --exclude='.gitignore' \
    --exclude='app/data' \
    --exclude='app/tests' \
    --exclude='app/__pycache__' \
    --exclude='app/.pytest_cache' \
    --exclude='app/.ruff_cache' \
    --exclude='app/.env' \
    --exclude='app/.env.example' \
    --exclude='app/pytest.ini' \
    --exclude='ui-tests' \
    --exclude='node_modules' \
    --exclude='*.md' \
    --exclude='test-results' \
    --exclude='.pytest_cache' \
    --exclude='.ruff*' \
    --exclude='docs' \
    --exclude='scripts' \
    ./ $USER@$SERVER:$DEPLOY_DIR/

# Copy daemon binaries
echo "Copying daemon binaries..."
ssh $USER@$SERVER "mkdir -p $DEPLOY_DIR/data/bin"
rsync -av data/bin/ $USER@$SERVER:$DEPLOY_DIR/data/bin/

# Copy current .env as production environment
echo "Copying environment configuration..."
if [ -f app/.env ]; then
    scp app/.env $USER@$SERVER:$DEPLOY_DIR/app/.env
    echo "Production .env copied."
else
    echo "ERROR: app/.env not found!"
    exit 1
fi

echo ""
echo "========================================"
echo "Files deployed to $DEPLOY_DIR"
echo "========================================"
echo "To deploy, run on server:"
echo "  cd $DEPLOY_DIR"
echo "  docker compose -f docker-compose.prod.yml up -d --build"
echo ""
echo "Then initialize wallets:"
echo "  docker exec ordex-swap-ordex-swap-1 /app/first-run.sh"
