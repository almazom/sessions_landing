#!/bin/bash
# Agent Nexus - Start Daemon
# Запускает сервер в фоне с nohup

set -e

cd /home/pets/temp/sessions_landing

source /home/pets/temp/sessions_landing/config/runtime.sh
load_runtime_config

HEALTHCHECK_HOST=$NEXUS_HOST
if [ "$HEALTHCHECK_HOST" = "0.0.0.0" ]; then
    HEALTHCHECK_HOST=127.0.0.1
fi

# Остановить старые процессы
pkill -f "uvicorn backend.api.main:app" 2>/dev/null || true
sleep "$NEXUS_PROCESS_STOP_WAIT_SECONDS"

# Проверить порт
PORT=${NEXUS_BACKEND_PORT}
if lsof -i:$PORT >/dev/null 2>&1; then
    echo "❌ Порт $PORT занят"
    lsof -i:$PORT
    exit 1
fi

echo "🚀 Agent Nexus"
echo "   Backend: http://0.0.0.0:$PORT"
echo "   Public:  $NEXUS_PUBLIC_URL"
echo "   Password: ✅ Set from .env"
echo ""

# Запуск с nohup
nohup python3 -m uvicorn backend.api.main:app \
    --host "$NEXUS_HOST" \
    --port $PORT \
    > /tmp/nexus.log 2>&1 &

NEXUS_PID=$!
echo "PID: $NEXUS_PID"

# Сохранить PID
echo $NEXUS_PID > /tmp/nexus.pid

sleep "$NEXUS_HEALTHCHECK_WAIT_SECONDS"

# Проверка
if curl -s "http://$HEALTHCHECK_HOST:$PORT/health" >/dev/null 2>&1; then
    echo "✅ Server running!"
    echo ""
    echo "🌐 URLs:"
    echo "   Backend: http://$HEALTHCHECK_HOST:$PORT"
    echo "   Public:  $NEXUS_PUBLIC_URL"
    echo "   API:     $NEXUS_PUBLIC_URL/api/docs"
    echo ""
    echo "📝 Logs: tail -f /tmp/nexus.log"
else
    echo "❌ Server failed to start"
    echo ""
    cat /tmp/nexus.log
fi
