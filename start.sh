#!/bin/bash
# Agent Nexus - Startup Script

set -e

cd /home/pets/temp/sessions_landing
source /home/pets/temp/sessions_landing/config/runtime.sh
load_runtime_config

echo "🚀 Запуск Agent Nexus..."

# Backend
echo "📦 Backend..."
cd backend
python3 -m uvicorn api.main:app --host "$NEXUS_HOST" --port "$NEXUS_DEV_BACKEND_PORT" --reload &
BACKEND_PID=$!
cd ..

# Frontend (если установлен)
if [ -d "frontend/node_modules" ]; then
    echo "🎨 Frontend..."
    cd frontend
    HOSTNAME="$NEXUS_HOST" PORT="$NEXUS_FRONTEND_PORT" NEXT_PUBLIC_API_URL="$NEXUS_DEV_API_URL" npm run dev &
    FRONTEND_PID=$!
    cd ..
fi

echo "✅ Agent Nexus запущен!"
echo "   Backend:  http://localhost:$NEXUS_DEV_BACKEND_PORT"
echo "   Frontend: http://localhost:$NEXUS_FRONTEND_PORT"
echo ""
echo "Нажмите Ctrl+C для остановки"

# Wait
trap "kill $BACKEND_PID ${FRONTEND_PID:-} 2>/dev/null" EXIT
wait
