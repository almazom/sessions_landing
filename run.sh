#!/bin/bash
# Agent Nexus - Production Start
# Usage: ./run.sh

set -e

cd /home/pets/temp/sessions_landing
source /home/pets/temp/sessions_landing/config/runtime.sh
load_runtime_config

# Вывод конфигурации (без пароля!)
echo "🚀 Agent Nexus"
echo "   Host: ${NEXUS_HOST}"
echo "   Port: ${NEXUS_BACKEND_PORT}"
echo "   Password: ${NEXUS_PASSWORD:+✅ Установлен}"
echo "   DB: ${NEXUS_DB_PATH:-~/.nexus/nexus.db}"
echo ""

# Остановить старый процесс
pkill -f "uvicorn backend.api.main:app" 2>/dev/null || true
sleep "$NEXUS_PROCESS_STOP_WAIT_SECONDS"

# Запуск
exec python3 -m uvicorn backend.api.main:app \
    --host "$NEXUS_HOST" \
    --port "$NEXUS_BACKEND_PORT"
