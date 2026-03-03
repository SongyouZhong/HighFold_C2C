#!/usr/bin/env bash
# ============================================================
# HighFold-C2C Docker Management Script
# ============================================================
# Usage:
#   ./docker-manage.sh build           Build images
#   ./docker-manage.sh up              Start services
#   ./docker-manage.sh down            Stop services
#   ./docker-manage.sh logs [--follow] View logs
#   ./docker-manage.sh shell           Open shell in app container
#   ./docker-manage.sh status          Show running containers
#   ./docker-manage.sh restart         Restart app service
#
# Flags:
#   --dev       Use development overrides
#   --storage   Include SeaweedFS services
#   --follow    Follow log output (with 'logs')

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILES="-f docker-compose.yml"
COMPOSE_PROFILES=""

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --dev)
            COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.dev.yml"
            ;;
        --storage)
            COMPOSE_PROFILES="--profile storage"
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
        --dev|--storage|--follow) ;;
        *) ARGS+=("$arg") ;;
    esac
done

CMD="${ARGS[0]:-help}"
COMPOSE="docker compose $COMPOSE_FILES $COMPOSE_PROFILES"

case "$CMD" in
    build)
        echo "Building HighFold-C2C images..."
        $COMPOSE build
        ;;
    up)
        echo "Starting HighFold-C2C services..."
        $COMPOSE up -d
        echo "Services started. API available at http://localhost:8003"
        ;;
    down)
        echo "Stopping HighFold-C2C services..."
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
    *)
        echo "HighFold-C2C Docker Management"
        echo ""
        echo "Usage: $0 <command> [flags]"
        echo ""
        echo "Commands:"
        echo "  build     Build Docker images"
        echo "  up        Start all services"
        echo "  down      Stop all services"
        echo "  logs      View service logs"
        echo "  shell     Open shell in app container"
        echo "  status    Show running containers"
        echo "  restart   Restart the app service"
        echo ""
        echo "Flags:"
        echo "  --dev       Use development overrides (hot-reload)"
        echo "  --storage   Include SeaweedFS services"
        echo "  --follow    Follow log output (with 'logs')"
        ;;
esac
