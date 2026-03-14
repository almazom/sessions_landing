import json
import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import User
from backend.api.routes import websocket as websocket_routes


class FakeWebSocket:
    def __init__(self, connection_id: str):
        self.accepted = False
        self.sent_messages: list[dict] = []
        self.state = types.SimpleNamespace(connection_id=connection_id)
        self.client = types.SimpleNamespace(host="127.0.0.1")

    async def accept(self):
        self.accepted = True

    async def send_text(self, message: str):
        self.sent_messages.append(json.loads(message))


class WebSocketRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def test_interactive_subscription_broadcasts_only_to_matching_route(self) -> None:
        manager = websocket_routes.ConnectionManager()
        first_socket = FakeWebSocket("ws-1")
        second_socket = FakeWebSocket("ws-2")

        await manager.connect(first_socket)
        await manager.connect(second_socket)
        await manager.subscribe_interactive(first_socket, harness="codex", route_id="rollout-a.jsonl")
        await manager.subscribe_interactive(second_socket, harness="codex", route_id="rollout-b.jsonl")

        await manager.broadcast_interactive_event(
            harness="codex",
            route_id="rollout-a.jsonl",
            event={
                "event_id": "turn-started",
                "kind": "turn",
                "status": "started",
                "summary": "Turn started",
                "payload": {},
            },
        )

        first_types = [message["type"] for message in first_socket.sent_messages]
        second_types = [message["type"] for message in second_socket.sent_messages]
        self.assertIn("interactive_subscribed", first_types)
        self.assertIn("interactive_event", first_types)
        self.assertIn("interactive_subscribed", second_types)
        self.assertNotIn("interactive_event", second_types)

    def test_interactive_rejects_subscription_without_route_identity(self) -> None:
        app = FastAPI()
        app.include_router(websocket_routes.router)

        async def fake_user(_websocket):
            return User(username="admin", is_authenticated=True, auth_method="test")

        with patch.object(websocket_routes, "get_current_websocket_user", side_effect=fake_user):
            with TestClient(app) as client:
                with client.websocket_connect("/ws") as websocket:
                    connected_message = json.loads(websocket.receive_text())
                    self.assertEqual(connected_message["type"], "connected")

                    websocket.send_text(json.dumps({
                        "type": "subscribe_interactive",
                        "data": {
                            "harness": "codex",
                        },
                    }))
                    error_message = json.loads(websocket.receive_text())
                    self.assertEqual(error_message["type"], "error")
                    self.assertIn("requires harness and route_id", error_message["data"]["message"])
