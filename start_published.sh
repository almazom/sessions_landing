#!/bin/bash
# Agent Nexus - Start published URL stack
# Publishes the app through Caddy on http://107.174.231.22:8888

set -euo pipefail

PROJECT_ROOT=/home/pets/temp/sessions_landing

cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/config/runtime.sh"
load_runtime_config
BACKEND_PORT=${NEXUS_BACKEND_PORT}
PYTHON_BIN=${PYTHON_BIN:-/usr/bin/python3}
FRONTEND_STANDALONE_SERVER="$PROJECT_ROOT/frontend/.next/standalone/server.js"
CADDY_LOG_FILE=/tmp/nexus-caddy.log

wait_for_url() {
    local url=$1
    local attempts=$2
    local delay_seconds=$3

    for _ in $(seq 1 "$attempts"); do
        if curl -fsS "$url" >/dev/null; then
            return 0
        fi
        sleep "$delay_seconds"
    done

    return 1
}

stop_pid_file() {
    local pid_file=$1

    if [ ! -f "$pid_file" ]; then
        return 0
    fi

    local pid
    pid=$(cat "$pid_file" 2>/dev/null || true)

    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$pid_file"
}

ensure_caddy() {
    if ! command -v caddy >/dev/null 2>&1; then
        echo "❌ Caddy is required for the published stack but is not installed."
        return 1
    fi

    caddy validate --config "$PROJECT_ROOT/Caddyfile" >/dev/null

    if caddy reload --config "$PROJECT_ROOT/Caddyfile" >"$CADDY_LOG_FILE" 2>&1; then
        echo "↻ Caddy reloaded"
        return 0
    fi

    caddy start --config "$PROJECT_ROOT/Caddyfile" >"$CADDY_LOG_FILE" 2>&1
    echo "▶ Caddy started"
}

echo "🚀 Agent Nexus published stack"
echo "   Public:  $NEXUS_PUBLIC_URL"
echo "   Frontend: $NEXUS_FRONTEND_URL"
echo "   Backend:  $NEXUS_BACKEND_URL"
echo ""

echo "🏗️ Building frontend"
(
    cd frontend
    npm run build >/tmp/nexus-frontend-build.log 2>&1
    rm -rf .next/standalone/.next/static
    mkdir -p .next/standalone/.next
    cp -a .next/static .next/standalone/.next/static

    if [ -d public ]; then
        rm -rf .next/standalone/public
        mkdir -p .next/standalone/public
        cp -a public/. .next/standalone/public/
    fi
)

# Stop only the local project processes we own once the next build is ready.
stop_pid_file /tmp/nexus-backend.pid
stop_pid_file /tmp/nexus-frontend.pid
pkill -f "uvicorn backend.api.main:app" 2>/dev/null || true
pkill -f "$FRONTEND_STANDALONE_SERVER" 2>/dev/null || true
pkill -f "/home/pets/temp/sessions_landing/frontend/node_modules/.bin/next start" 2>/dev/null || true
pkill -f "/home/pets/temp/sessions_landing/frontend/node_modules/.bin/next dev" 2>/dev/null || true
fuser -k "${BACKEND_PORT}/tcp" >/dev/null 2>&1 || true
fuser -k "${NEXUS_FRONTEND_PORT}/tcp" >/dev/null 2>&1 || true
sleep "$NEXUS_PROCESS_STOP_WAIT_SECONDS"

setsid "$PYTHON_BIN" -m uvicorn backend.api.main:app \
    --host "$NEXUS_HOST" \
    --port "$BACKEND_PORT" \
    > /tmp/nexus-backend.log 2>&1 < /dev/null &

BACKEND_PID=$!

(
    cd frontend
    HOSTNAME="$NEXUS_HOST" PORT="$NEXUS_FRONTEND_PORT" \
    setsid node "$FRONTEND_STANDALONE_SERVER" \
        > /tmp/nexus-frontend.log 2>&1 < /dev/null &
    echo $! > /tmp/nexus-frontend.pid
)

echo "$BACKEND_PID" > /tmp/nexus-backend.pid

sleep "$NEXUS_STACK_READY_WAIT_SECONDS"
ensure_caddy

echo "🔎 Health checks"
wait_for_url "$NEXUS_BACKEND_URL/health" 20 1
wait_for_url "$NEXUS_FRONTEND_URL/" 20 1
wait_for_url "http://127.0.0.1:${NEXUS_PUBLIC_PORT}/health" 20 1

if [ "$NEXUS_PLAYWRIGHT_CHECK_ENABLED" = "1" ]; then
    echo "🎭 Playwright published URL check"
    "$PROJECT_ROOT/deploy/check_published_url.sh" "$NEXUS_PUBLIC_URL"
fi

echo "✅ Published stack is up"
echo "   Public: $NEXUS_PUBLIC_URL"
echo "   Logs:"
echo "   tail -f /tmp/nexus-frontend-build.log"
echo "   tail -f /tmp/nexus-backend.log"
echo "   tail -f /tmp/nexus-frontend.log"
echo "   tail -f $CADDY_LOG_FILE"
