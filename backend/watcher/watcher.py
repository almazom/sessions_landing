"""File watcher using watchdog to monitor agent session directories.

Monitors:
- ~/.codex/sessions
- ~/.kimi/sessions
- ~/.gemini/tmp
- ~/.qwen/projects
- ~/.claude/projects
"""

import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
import threading
import queue

from ..parsers import CodexParser, KimiParser, GeminiParser, QwenParser, ClaudeParser


@dataclass
class WatcherConfig:
    """Configuration for the session watcher."""
    polling_interval: float = 1.0  # seconds
    debounce_ms: int = 500  # milliseconds to wait before processing
    max_events_per_batch: int = 100
    watch_paths: Dict[str, List[str]] = field(default_factory=lambda: {
        "codex": ["~/.codex/sessions"],
        "kimi": ["~/.kimi/sessions"],
        "gemini": ["~/.gemini/tmp"],
        "qwen": ["~/.qwen/projects"],
        "claude": ["~/.claude/projects"],
    })


class SessionEventHandler(FileSystemEventHandler):
    """Handles file system events for session files."""

    def __init__(self, agent_type: str, callback: Callable, debounce_ms: int = 500):
        super().__init__()
        self.agent_type = agent_type
        self.callback = callback
        self.debounce_ms = debounce_ms
        self._pending: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._debounce_thread: Optional[threading.Thread] = None
        self._running = True

        # Start debounce thread
        self._debounce_thread = threading.Thread(target=self._process_pending, daemon=True)
        self._debounce_thread.start()

    def on_modified(self, event: FileModifiedEvent):
        """Handle file modification events."""
        if event.is_directory:
            return
        if not self._is_session_file(event.src_path):
            return
        self._queue_event(event.src_path)

    def on_created(self, event: FileCreatedEvent):
        """Handle file creation events."""
        if event.is_directory:
            return
        if not self._is_session_file(event.src_path):
            return
        self._queue_event(event.src_path)

    def _is_session_file(self, path: str) -> bool:
        """Check if file is a session file we care about."""
        path_lower = path.lower()
        return (
            path_lower.endswith('.jsonl') or
            path_lower.endswith('logs.json') or
            'context.jsonl' in path_lower
        )

    def _queue_event(self, path: str):
        """Queue an event for debounced processing."""
        with self._lock:
            self._pending[path] = time.time()

    def _process_pending(self):
        """Process pending events after debounce period."""
        while self._running:
            time.sleep(0.1)  # Check every 100ms

            now = time.time()
            to_process = []

            with self._lock:
                for path, event_time in list(self._pending.items()):
                    if (now - event_time) * 1000 >= self.debounce_ms:
                        to_process.append(path)
                        del self._pending[path]

            for path in to_process:
                try:
                    self.callback(self.agent_type, path)
                except Exception as e:
                    print(f"Error processing {path}: {e}")

    def stop(self):
        """Stop the debounce thread."""
        self._running = False


class SessionWatcher:
    """Watches agent session directories for changes."""

    def __init__(self, config: Optional[WatcherConfig] = None):
        self.config = config or WatcherConfig()
        self.observers: List[Observer] = []
        self.handlers: List[SessionEventHandler] = []
        self.event_queue: queue.Queue = queue.Queue()
        self._running = False
        self._callbacks: List[Callable] = []

        # Initialize parsers
        self.parsers = {
            "codex": CodexParser(),
            "kimi": KimiParser(),
            "gemini": GeminiParser(),
            "qwen": QwenParser(),
            "claude": ClaudeParser(),
        }

    def on_session_update(self, callback: Callable):
        """Register a callback for session updates."""
        self._callbacks.append(callback)

    def _handle_file_change(self, agent_type: str, file_path: str):
        """Handle a file change event."""
        self.event_queue.put({
            "agent_type": agent_type,
            "file_path": file_path,
            "timestamp": time.time(),
        })

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(agent_type, file_path)
            except Exception as e:
                print(f"Callback error: {e}")

    def start(self):
        """Start watching all configured directories."""
        if self._running:
            return

        self._running = True

        for agent_type, paths in self.config.watch_paths.items():
            for watch_path in paths:
                expanded_path = Path(watch_path).expanduser()

                if not expanded_path.exists():
                    print(f"Watch path does not exist: {expanded_path}")
                    continue

                handler = SessionEventHandler(
                    agent_type=agent_type,
                    callback=self._handle_file_change,
                    debounce_ms=self.config.debounce_ms,
                )
                self.handlers.append(handler)

                observer = Observer()
                observer.schedule(handler, str(expanded_path), recursive=True)
                observer.start()
                self.observers.append(observer)

                print(f"Watching {agent_type}: {expanded_path}")

    def stop(self):
        """Stop all watchers."""
        self._running = False

        for handler in self.handlers:
            handler.stop()

        for observer in self.observers:
            observer.stop()
            observer.join()

        self.observers.clear()
        self.handlers.clear()

    def scan_existing(self) -> Dict[str, List[str]]:
        """Scan existing session files in all watched directories.

        Returns:
            Dict mapping agent_type to list of file paths
        """
        existing: Dict[str, List[str]] = {}

        for agent_type, paths in self.config.watch_paths.items():
            existing[agent_type] = []

            for watch_path in paths:
                expanded_path = Path(watch_path).expanduser()

                if not expanded_path.exists():
                    continue

                # Find all session files
                for pattern in ["**/*.jsonl", "**/logs.json"]:
                    for file_path in expanded_path.glob(pattern):
                        if file_path.is_file():
                            existing[agent_type].append(str(file_path))

        return existing

    def get_pending_events(self, max_count: int = 100) -> List[Dict]:
        """Get pending events from the queue."""
        events = []
        try:
            while len(events) < max_count:
                event = self.event_queue.get_nowait()
                events.append(event)
        except queue.Empty:
            pass
        return events

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
