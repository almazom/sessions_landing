# Profile

## Context Handoff

Use this file as the `why` layer.

After this file, read:

- `docs/product/HIGH_LEVEL_EXPECTATIONS.md` -> what a good product result should look like
- `AURA.md` -> how the system should be built

Rule:

- do not treat `PROFILE.md` as the full product spec
- use it to anchor purpose and priority
- use `docs/product/HIGH_LEVEL_EXPECTATIONS.md` to fill product-shape context for UI, UX, and detail-page decisions

## Why This Project Exists

This project exists to reduce the chaos of working across many AI session providers, agents, and model subscriptions.

The user is one person only. He runs many agent sessions across tools such as Codex, Gemini, Claude Code, Qwen, Kimi, Pi, and provider-mixed setups inside other agents. Those sessions produce many files, many paths, and many overlapping conversations. Without a single system, it becomes hard to answer the basic operational questions that matter:

- which session is the right one
- where the exact source file lives
- what the user was trying to do in that session
- which session should be handed off to another agent next

The project exists to make those answers fast and reliable.

Its purpose is not only to list sessions, but to make them identifiable, transferable, and usable as working artifacts. A session file should become something the user can recognize, summarize, inspect, pass to another agent, and later turn into a deeper view or a dedicated landing page.

At the product level, this is a private operational system for one user managing AI work across fragmented providers.
