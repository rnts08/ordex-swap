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
    --exclude='.github/' \
    --exclude='.opencode/' \
    --exclude='.vscode' \
    --exclude='app/.coverage' \
    --exclude='app/data' \
    --exclude='app/tests' \
    --exclude='app/__pycache__' \
    --exclude='app/swap-service/__pycache__' \
    --exclude='app/.pytest_cache' \
    --exclude='app/.ruff_cache' \
    --exclude='app/htmlcov' \
    --exclude='app/venv/' \
    --exclude='.venv/' \
    --exclude='app/.venv/' \
    --exclude='app/venv' \
    --exclude='app/.env.example' \
    --exclude='app/migrations/__pycache__' \
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

echo ""
echo "========================================"
echo "Files deployed to $DEPLOY_DIR"
echo "========================================"
echo "To deploy, run on server:"
echo "  cd $DEPLOY_DIR"
echo "  docker compose -f docker-compose.prod.yml up -d --build"
echo ""
