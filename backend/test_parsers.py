#!/usr/bin/env python3
"""Test script for session parsers.

Run with: python backend/test_parsers.py
"""

import sys
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.parsers.codex_parser import CodexParser
from backend.parsers.kimi_parser import KimiParser
from backend.parsers.qwen_parser import QwenParser
from backend.parsers.claude_parser import ClaudeParser
from backend.summarizer.summarizer import SessionSummarizer


def test_codex_parser():
    """Test Codex parser with real session file."""
    print("\n" + "="*60)
    print("Testing Codex Parser")
    print("="*60)

    parser = CodexParser()

    # Find a recent Codex session
    codex_path = Path.home() / ".codex" / "sessions" / "2026" / "03" / "09"
    if not codex_path.exists():
        print("No Codex sessions found for today")
        return None

    session_files = list(codex_path.glob("rollout-*.jsonl"))
    if not session_files:
        print("No session files found")
        return None

    test_file = session_files[0]
    print(f"Parsing: {test_file.name}")

    summary = parser.parse_file(test_file)

    print(f"\nSession ID: {summary.session_id}")
    print(f"Agent: {summary.agent_name}")
    print(f"CWD: {summary.cwd}")
    print(f"Status: {summary.status.value}")
    print(f"Intent: {summary.user_intent[:100]}..." if summary.user_intent else "Intent: (none)")
    print(f"Tool calls: {summary.tool_calls[:5]}")
    print(f"Tokens: {summary.token_usage.get('total_tokens', 0)}")
    print(f"Timeline events: {len(summary.timeline)}")

    # Check size
    summarizer = SessionSummarizer()
    json_size = summarizer.check_size(summary)
    print(f"JSON size: {json_size} bytes ({'OK' if json_size < 1024 else 'TOO LARGE'})")

    return summary


def test_kimi_parser():
    """Test Kimi parser with real session file."""
    print("\n" + "="*60)
    print("Testing Kimi Parser")
    print("="*60)

    parser = KimiParser()

    # Find a Kimi session
    kimi_path = Path.home() / ".kimi" / "sessions"
    if not kimi_path.exists():
        print("No Kimi sessions directory")
        return None

    # Find first session with context.jsonl
    for hash_dir in kimi_path.iterdir():
        if hash_dir.is_dir():
            for uuid_dir in hash_dir.iterdir():
                context_file = uuid_dir / "context.jsonl"
                if context_file.exists():
                    print(f"Parsing: {context_file.relative_to(Path.home())}")

                    summary = parser.parse_file(context_file)

                    print(f"\nSession ID: {summary.session_id}")
                    print(f"Agent: {summary.agent_name}")
                    print(f"Status: {summary.status.value}")
                    print(f"Intent: {summary.user_intent[:100]}..." if summary.user_intent else "Intent: (none)")
                    print(f"Tokens: {summary.token_usage.get('total_tokens', 0)}")

                    return summary

    print("No Kimi sessions found")
    return None


def test_qwen_parser():
    """Test Qwen parser with real session file."""
    print("\n" + "="*60)
    print("Testing Qwen Parser")
    print("="*60)

    parser = QwenParser()

    # Find a Qwen session
    qwen_path = Path.home() / ".qwen" / "projects"
    if not qwen_path.exists():
        print("No Qwen sessions directory")
        return None

    # Find first project with chats
    for project_dir in qwen_path.iterdir():
        if project_dir.is_dir():
            chats_dir = project_dir / "chats"
            if chats_dir.exists():
                for chat_file in chats_dir.glob("*.jsonl"):
                    print(f"Parsing: {chat_file.relative_to(Path.home())}")

                    summary = parser.parse_file(chat_file)

                    print(f"\nSession ID: {summary.session_id}")
                    print(f"Agent: {summary.agent_name}")
                    print(f"CWD: {summary.cwd}")
                    print(f"Status: {summary.status.value}")
                    print(f"Intent: {summary.user_intent[:100]}..." if summary.user_intent else "Intent: (none)")
                    print(f"Tool calls: {summary.tool_calls[:5]}")
                    print(f"Tokens: {summary.token_usage.get('total_tokens', 0)}")

                    return summary

    print("No Qwen sessions found")
    return None


def test_claude_parser():
    """Test Claude parser with real session file."""
    print("\n" + "="*60)
    print("Testing Claude Parser")
    print("="*60)

    parser = ClaudeParser()

    # Find a Claude session
    claude_path = Path.home() / ".claude" / "projects"
    if not claude_path.exists():
        print("No Claude sessions directory")
        return None

    # Find first project with session
    for project_dir in claude_path.iterdir():
        if project_dir.is_dir():
            for session_file in project_dir.glob("*.jsonl"):
                if session_file.name == "memory":
                    continue
                print(f"Parsing: {session_file.relative_to(Path.home())}")

                summary = parser.parse_file(session_file)

                print(f"\nSession ID: {summary.session_id}")
                print(f"Agent: {summary.agent_name}")
                print(f"CWD: {summary.cwd}")
                print(f"Status: {summary.status.value}")
                print(f"Intent: {summary.user_intent[:100]}..." if summary.user_intent else "Intent: (none)")
                print(f"Tool calls: {summary.tool_calls[:5]}")

                return summary

    print("No Claude sessions found")
    return None


def test_secret_masking():
    """Test secret masking functionality."""
    print("\n" + "="*60)
    print("Testing Secret Masking")
    print("="*60)


    test_cases = [
        ("sk-proj-abc123def456ghi789jkl012mno345pqr678", "OpenAI key"),
        ("ghp_1234567890abcdefghijklmnopqrstuvwxyz1234", "GitHub PAT"),
        ("xoxb-FAKE-SLACK-TOKEN-EXAMPLE-DEMO-TEST", "Slack token"),
        ("API_KEY=super_secret_key_12345", "API key in env"),
        ("https://user:password@example.com/api", "URL with credentials"),
        ("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "Bearer token"),
    ]

    summarizer = SessionSummarizer()

    for text, description in test_cases:
        masked = summarizer._mask_secrets(text)
        status = "✅ MASKED" if "***REDACTED***" in masked or "***:***@" in masked else "❌ NOT MASKED"
        print(f"\n{description}:")
        print(f"  Original: {text}")
        print(f"  Masked:   {masked}")
        print(f"  Status:   {status}")


def test_model_detection():
    """Test model detection in parsers."""
    print("\n" + "="*60)
    print("Testing Model Detection")
    print("="*60)

    # Test Claude with different models
    claude_path = Path.home() / ".claude" / "projects"
    if claude_path.exists():
        for project_dir in list(claude_path.iterdir())[:3]:
            if project_dir.is_dir():
                for session_file in project_dir.glob("*.jsonl"):
                    if session_file.name == "memory":
                        continue
                    with open(session_file, 'r') as f:
                        for line in f:
                            if '"model"' in line:
                                try:
                                    entry = json.loads(line)
                                    if entry.get("type") == "assistant":
                                        model = entry.get("message", {}).get("model", "")
                                        if model:
                                            print(f"\nFound model '{model}' in {session_file.name}")
                                except:
                                    pass


def main():
    """Run all tests."""
    print("\n" + "#"*60)
    print("# Agent Nexus - Parser Tests")
    print("#"*60)

    test_codex_parser()
    test_kimi_parser()
    test_qwen_parser()
    test_claude_parser()
    test_secret_masking()
    test_model_detection()

    print("\n" + "#"*60)
    print("# Tests Complete")
    print("#"*60 + "\n")


if __name__ == "__main__":
    main()
