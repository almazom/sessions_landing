"""WebSocket route for real-time session updates."""

import json
import secrets
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from backend.api.deps import get_current_websocket_user
from backend.api.logging_utils import get_logger, log_event
from backend.api.scanner import session_store, session_scanner


router = APIRouter(tags=["WebSocket"])
logger = get_logger("agent_nexus.websocket")


class WSMessage(BaseModel):
    """WebSocket message format."""
    type: str  # "session_update" | "metrics_update" | "ping" | "pong"
    data: Optional[Dict[str, Any]] = None
    timestamp: str = ""
    
    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()
        super().__init__(**data)


@dataclass
class ConnectionManager:
    """Manage WebSocket connections."""
    
    active_connections: List[WebSocket] = field(default_factory=list)
    
    async def connect(self, websocket: WebSocket):
        """Accept new connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        log_event(
            logger,
            "info",
            "websocket.connected",
            connection_id=getattr(websocket.state, "connection_id", ""),
            client_ip=websocket.client.host if websocket.client else "unknown",
            active_connections=len(self.active_connections),
        )
        
        # Отправляем приветствие
        await self.send_personal(websocket, WSMessage(
            type="connected",
            data={"message": "Подключено к Agent Nexus", "clients": len(self.active_connections)}
        ))
    
    def disconnect(self, websocket: WebSocket):
        """Remove connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        log_event(
            logger,
            "info",
            "websocket.disconnected",
            connection_id=getattr(websocket.state, "connection_id", ""),
            client_ip=websocket.client.host if websocket.client else "unknown",
            active_connections=len(self.active_connections),
        )
    
    async def send_personal(self, websocket: WebSocket, message: WSMessage):
        """Send message to specific client."""
        try:
            await websocket.send_text(message.model_dump_json())
        except Exception as e:
            log_event(
                logger,
                "error",
                "websocket.send_failed",
                connection_id=getattr(websocket.state, "connection_id", ""),
                message_type=message.type,
                error_type=type(e).__name__,
                error_message=str(e),
            )
    
    async def broadcast(self, message: WSMessage):
        """Broadcast to all connected clients."""
        if not self.active_connections:
            return
            
        message_json = message.model_dump_json()
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception:
                disconnected.append(connection)
        
        # Удаляем отключённые
        for conn in disconnected:
            self.disconnect(conn)

        log_event(
            logger,
            "info",
            "websocket.broadcast.completed",
            message_type=message.type,
            recipients=len(self.active_connections),
            disconnected=len(disconnected),
        )
    
    async def broadcast_session_update(self, session_data: dict):
        """Broadcast session update to all clients."""
        await self.broadcast(WSMessage(
            type="session_update",
            data=session_data
        ))
    
    async def broadcast_metrics(self, metrics: dict):
        """Broadcast metrics update to all clients."""
        await self.broadcast(WSMessage(
            type="metrics_update",
            data=metrics
        ))


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
):
    """
    🔌 WebSocket endpoint для real-time обновлений
    
    Протокол сообщений:
    
    Сервер → Клиент:
    - {"type": "connected", "data": {...}}
    - {"type": "session_update", "data": {...}}
    - {"type": "metrics_update", "data": {...}}
    - {"type": "pong", "timestamp": "..."}
    
    Клиент → Сервер:
    - {"type": "ping"} → pong
    - {"type": "subscribe", "data": {"session_id": "..."}} 
    - {"type": "rescan"}
    """
    websocket.state.connection_id = secrets.token_hex(6)

    try:
        await get_current_websocket_user(websocket)
    except Exception as error:
        if isinstance(error, WebSocketDisconnect):
            return
        log_event(
            logger,
            "warning",
            "websocket.auth_failed",
            connection_id=getattr(websocket.state, "connection_id", ""),
            client_ip=websocket.client.host if websocket.client else "unknown",
            error_type=type(error).__name__,
            error_message=str(error),
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    
    try:
        while True:
            # Получаем сообщение
            data = await websocket.receive_text()
            
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")
                log_event(
                    logger,
                    "info",
                    "websocket.message.received",
                    connection_id=getattr(websocket.state, "connection_id", ""),
                    message_type=msg_type,
                )
                
                # Ping-Pong
                if msg_type == "ping":
                    await manager.send_personal(websocket, WSMessage(type="pong"))
                
                # Запрос на пересканирование
                elif msg_type == "rescan":
                    session_store.sessions.clear()
                    count = session_scanner.scan_all()
                    await manager.send_personal(websocket, WSMessage(
                        type="rescan_complete",
                        data={"sessions_found": count}
                    ))
                    # Транслируем новые метрики
                    await manager.broadcast_metrics(session_store.metrics())
                
                # Подписка на сессию
                elif msg_type == "subscribe":
                    session_id = msg.get("data", {}).get("session_id")
                    if session_id:
                        session = session_store.get(session_id)
                        if session:
                            await manager.send_personal(websocket, WSMessage(
                                type="session_update",
                                data=session
                            ))
                        else:
                            await manager.send_personal(websocket, WSMessage(
                                type="error",
                                data={"message": f"Сессия {session_id} не найдена"}
                            ))
                
                # Неизвестный тип
                else:
                    await manager.send_personal(websocket, WSMessage(
                        type="error",
                        data={"message": f"Неизвестный тип: {msg_type}"}
                    ))
                    
            except json.JSONDecodeError:
                await manager.send_personal(websocket, WSMessage(
                    type="error",
                    data={"message": "Неверный JSON"}
                ))
                log_event(
                    logger,
                    "warning",
                    "websocket.message.invalid_json",
                    connection_id=getattr(websocket.state, "connection_id", ""),
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        log_event(
            logger,
            "error",
            "websocket.connection_failed",
            connection_id=getattr(websocket.state, "connection_id", ""),
            client_ip=websocket.client.host if websocket.client else "unknown",
            error_type=type(e).__name__,
            error_message=str(e),
        )
        manager.disconnect(websocket)


# Функция для внешнего использования (транслировать обновление сессии)
async def notify_session_update(session_data: dict):
    """Call this when a session is updated."""
    await manager.broadcast_session_update(session_data)


async def notify_metrics_update(metrics: dict):
    """Call this when metrics change."""
    await manager.broadcast_metrics(metrics)
