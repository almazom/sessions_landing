from __future__ import annotations

import unittest

from backend.api.interactive_events import normalize_thread_event


class Task027CoreEventNormalizationTests(unittest.TestCase):
    def test_green_normalizes_codex_thread_events_to_browser_model(self) -> None:
        command_event = normalize_thread_event(
            {
                "type": "item.completed",
                "item": {
                    "id": "cmd-1",
                    "type": "command_execution",
                    "command": "pytest -q",
                    "aggregated_output": "2 passed",
                    "exit_code": 0,
                    "status": "completed",
                },
            }
        )
        message_event = normalize_thread_event(
            {
                "type": "item.completed",
                "item": {
                    "id": "msg-1",
                    "type": "agent_message",
                    "text": "Build succeeded.",
                },
            }
        )
        todo_event = normalize_thread_event(
            {
                "type": "item.updated",
                "item": {
                    "id": "todo-1",
                    "type": "todo_list",
                    "items": [
                        {"text": "ship backend", "completed": True},
                        {"text": "ship frontend", "completed": False},
                    ],
                },
            }
        )

        self.assertEqual(command_event["kind"], "command")
        self.assertEqual(command_event["status"], "completed")
        self.assertEqual(command_event["summary"], "pytest -q")
        self.assertEqual(command_event["payload"]["exit_code"], 0)

        self.assertEqual(message_event["kind"], "agent_message")
        self.assertEqual(message_event["status"], "completed")
        self.assertEqual(message_event["summary"], "Build succeeded.")

        self.assertEqual(todo_event["kind"], "todo_list")
        self.assertEqual(todo_event["status"], "updated")
        self.assertEqual(todo_event["payload"]["completed_count"], 1)
        self.assertEqual(todo_event["payload"]["total_count"], 2)

    def test_red_rejects_unknown_thread_item_type(self) -> None:
        with self.assertRaises(ValueError):
            normalize_thread_event(
                {
                    "type": "item.started",
                    "item": {
                        "id": "mystery-1",
                        "type": "mystery_item",
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
