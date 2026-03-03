#!/usr/bin/env bash
# ============================================================
# HighFold-C2C Docker Management Script
# ============================================================
# This script manages only the HighFold-C2C app container.
# PostgreSQL and SeaweedFS are expected to be running on the host.
#
# Usage:
#   ./docker-manage.sh build           Build images
#   ./docker-manage.sh up              Start app service
#   ./docker-manage.sh down            Stop app service
#   ./docker-manage.sh logs [--follow] View logs
#   ./docker-manage.sh shell           Open shell in app container
#   ./docker-manage.sh status          Show running containers
#   ./docker-manage.sh restart         Restart app service
#   ./docker-manage.sh init-db         Initialize highfold tables in host DB
#
# Flags:
#   --dev       Use development overrides (hot-reload)
#   --follow    Follow log output (with 'logs')

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILES="-f docker-compose.yml"
ENV_FILE="--env-file ../.env"

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --dev)
            COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.dev.yml"
            ;;
        --follow)
            FOLLOW="-f"
            ;;
    esac
done

# Remove flags from arguments
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --dev|--follow) ;;
        *) ARGS+=("$arg") ;;
    esac
done

CMD="${ARGS[0]:-help}"
COMPOSE="docker compose $COMPOSE_FILES $ENV_FILE"

case "$CMD" in
    build)
        echo "Building HighFold-C2C image..."
        $COMPOSE build app
        ;;
    up)
        echo "Starting HighFold-C2C app..."
        echo "  Requires: PostgreSQL on host:5432, SeaweedFS on host:8888"
        $COMPOSE up -d app
        echo "App started. API available at http://localhost:${APP_PORT:-8003}"
        ;;
    down)
        echo "Stopping HighFold-C2C app..."
        $COMPOSE down
        ;;
    logs)
        $COMPOSE logs ${FOLLOW:-}
        ;;
    shell)
        echo "Opening shell in app container..."
        $COMPOSE exec app bash
        ;;
    status)
        $COMPOSE ps
        ;;
    restart)
        echo "Restarting app service..."
        $COMPOSE restart app
        ;;
    init-db)
        echo "Initializing HighFold tables in host PostgreSQL..."
        PGHOST="${DB_HOST:-127.0.0.1}"
        PGPORT="${DB_PORT:-5432}"
        PGUSER="${DB_USER:-admin}"
        PGDB="${DB_NAME:-mydatabase}"
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDB" \
            -f ../database/init_highfold_tables.sql
        echo "Done."
        ;;
    *)
        echo "HighFold-C2C Docker Management"
        echo ""
        echo "Prerequisites:"
        echo "  - PostgreSQL running on host (default port 5432)"
        echo "  - SeaweedFS running on host (default port 8888)"
        echo "  - NVIDIA Container Toolkit for GPU support"
        echo ""
        echo "Usage: $0 <command> [flags]"
        echo ""
        echo "Commands:"
        echo "  build     Build Docker image"
        echo "  up        Start app service"
        echo "  down      Stop app service"
        echo "  logs      View service logs"
        echo "  shell     Open shell in app container"
        echo "  status    Show running containers"
        echo "  restart   Restart the app service"
        echo "  init-db   Initialize highfold tables in host PostgreSQL"
        echo ""
        echo "Flags:"
        echo "  --dev       Use development overrides (hot-reload)"
        echo "  --follow    Follow log output (with 'logs')"
        ;;
esac
