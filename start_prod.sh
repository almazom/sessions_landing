#!/bin/bash
# Agent Nexus - Production Start
# Usage: ./start_prod.sh [PASSWORD]

set -e

cd /home/pets/temp/sessions_landing
source /home/pets/temp/sessions_landing/config/runtime.sh
load_runtime_config

# Порт из конфига или аргумент
PORT=${NEXUS_BACKEND_PORT}
PASSWORD=${1:-${NEXUS_PASSWORD:-""}}

export NEXUS_PASSWORD="$PASSWORD"
export NEXUS_IP_WHITELIST=""

echo "🚀 Agent Nexus"
echo "   Port: $PORT"
echo "   Password: ${PASSWORD:+✅ Set} ${PASSWORD:-❌ No password!}"
echo ""

# Остановить старый процесс
pkill -f "uvicorn backend.api.main:app" 2>/dev/null || true
sleep "$NEXUS_PROCESS_STOP_WAIT_SECONDS"

# Запуск
exec python3 -m uvicorn backend.api.main:app --host "$NEXUS_HOST" --port "$PORT"
