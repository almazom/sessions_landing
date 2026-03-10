#!/bin/bash
# Agent Nexus - Published stack watchdog
# Запускать через cron каждую минуту:
# * * * * * /home/pets/temp/sessions_landing/keep_alive.sh

set -euo pipefail

PROJECT_ROOT=/home/pets/temp/sessions_landing
LOCK_FILE=/tmp/nexus-watchdog.lock
LOG_FILE=/tmp/nexus-watchdog.log

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    exit 0
fi

cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/config/runtime.sh"
load_runtime_config

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" >> "$LOG_FILE"
}

pid_is_alive() {
    local pid_file=$1

    if [ ! -f "$pid_file" ]; then
        return 1
    fi

    local pid
    pid=$(cat "$pid_file" 2>/dev/null || true)

    if [ -z "$pid" ]; then
        return 1
    fi

    kill -0 "$pid" 2>/dev/null
}

url_is_healthy() {
    local url=$1
    curl -fsS --max-time 10 "$url" >/dev/null
}

backend_ok=true
frontend_ok=true
public_ok=true

pid_is_alive /tmp/nexus-backend.pid || backend_ok=false
pid_is_alive /tmp/nexus-frontend.pid || frontend_ok=false
url_is_healthy "$NEXUS_BACKEND_URL/health" || backend_ok=false
url_is_healthy "$NEXUS_FRONTEND_URL/" || frontend_ok=false
url_is_healthy "$NEXUS_PUBLIC_URL/api/metrics" || public_ok=false

if [ "$backend_ok" = true ] && [ "$frontend_ok" = true ] && [ "$public_ok" = true ]; then
    exit 0
fi

log "Detected unhealthy published stack: backend=$backend_ok frontend=$frontend_ok public=$public_ok"

if NEXUS_PLAYWRIGHT_CHECK_ENABLED="${NEXUS_PLAYWRIGHT_CHECK_ENABLED:-1}" "$PROJECT_ROOT/start_published.sh" >> "$LOG_FILE" 2>&1; then
    log "Published stack restarted successfully"
else
    log "Published stack restart failed"
    exit 1
fi
