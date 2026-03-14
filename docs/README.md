# Docs

This directory keeps product and operational documentation that sits beside the core repo entrypoints.

## Core Entry Points

These files stay in the repository root because they are part of the main bootstrap path:

- `PROFILE.md` -> why the project exists
- `AURA.md` -> how the system should be built
- `PROTOCOL.json` -> what exists and how tools/contracts are registered
- `AGENTS.md` -> how AI coding agents should work in this repository

## Product Docs

- `product/HIGH_LEVEL_EXPECTATIONS.md` -> what good product outcomes and UX behavior should look like
- `product/HIGH_LEVEL_EXPECTATIONS_RELATED_INTERACTIVE_MODE.md` -> terminal-like browser continuation expectations for the interactive mode
- `product/INTERACTIVE_TERMINAL_BROWSER_REPRODUCTION.md` -> step-by-step terminal-to-browser reproduction guide for one real Codex session
- `roadmap/SESSION_DETAIL_NEXT_STEP.md` -> next practical step for session detail evolution

## Organizing Rule

Use `docs/` for durable guidance that is important, but not part of the minimal root bootstrap set.

Good candidates for `docs/`:

- product expectations
- UX principles
- information architecture notes
- long-form design direction
- operator guides that are broader than one memory card
