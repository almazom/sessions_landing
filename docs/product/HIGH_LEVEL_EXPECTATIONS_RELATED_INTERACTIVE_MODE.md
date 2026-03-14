# High Level Expectations Related Interactive Mode

## Purpose

This document clarifies the intended product shape for the browser interactive mode.

The interactive mode is not a landing page, not a dossier summary, and not a report-first shell.

The target is a browser continuation experience that stays very close to the terminal experience of Codex CLI and Kimi Code CLI:

- a large live agent activity window
- a simple prompt input anchored at the bottom
- visible motion when the agent is thinking, acting, editing, or waiting
- obvious continuity between terminal session and browser session
- obvious continuity with the shared session artifact on disk

This document complements:

- [HIGH_LEVEL_EXPECTATIONS.md](./HIGH_LEVEL_EXPECTATIONS.md)
- [ssot_kanban_20260313_062127.json](../plans/ssot_kanban_20260313_062127.json)

## Product Correction

The current browser interactive shell direction is too close to a status-heavy dossier page:

- too much large header/report framing
- too many explanatory cards competing with the main flow
- composer visually reduced to a small secondary control
- agent motion presented as a report, not as the main surface

That direction is not the intended product.

The intended product is:

- open a Codex session in terminal
- send a message
- see the agent move
- open the same session in browser
- see almost the same flow in browser
- send the next message from browser
- see the same session continue
- inspect the same JSONL artifact and confirm that terminal, browser, and artifact stay aligned

Short rule:

- terminal continuation first
- dossier/report second

The dossier page and evidence panels are still useful, but they belong to the session detail surface, not to the main interactive continuation surface.

## Core UX Expectation

Interactive mode should feel like "Codex CLI in the browser".

The browser route should preserve these terminal qualities:

- one dominant live transcript/activity surface
- obvious progression turn by turn
- visible tool/action movement
- visible waiting, running, completed, failed, and reconnecting states
- bottom prompt input for the next user message
- minimal friction between reading the agent stream and sending the next prompt
- the feeling that browser and terminal are two views over one session, not two separate apps

The browser route should not feel like:

- a marketing page
- a dashboard card collection
- a read-only report with a tiny input tacked on
- a separate product unrelated to the terminal session

## Layout Expectation

The default interactive layout should be structurally simple.

### Primary region

The largest region on screen should be the live activity window.

It should show:

- replayed session continuation
- live agent events
- tool activity
- state changes
- prompt/response progression
- reconnect and resume markers
- enough of the real tail that the user can compare it against the terminal and the JSONL artifact

This region should dominate both desktop and mobile.

### Composer

The composer should sit at the bottom as the obvious next-step control.

It should be:

- always easy to find
- visually secondary to the live stream, but not hidden
- wide enough to feel like the main way to continue the session
- sticky or anchored so the user does not hunt for it

### Secondary information

Supporting metadata should be present but subordinate.

Examples:

- transport details
- runtime identity
- cwd
- session id
- replay boundary
- safety notes

These should move into:

- compact status strip
- collapsible side panel
- drawer
- expandable details section

They should not displace the live transcript from the center of the experience.

## Session Behavior Expectation

The browser interactive route should behave like a continuation shell, not like a fake simulator.

Expected flow:

1. Open an existing Codex session.
2. Replay enough history to orient the user.
3. Attach to live runtime or show an explicit blocked reason.
4. Keep the activity surface visible as the main UI.
5. Let the user send the next prompt from the bottom composer.
6. Show the resulting session movement in the same main surface.
7. Preserve reconnect behavior on reload.
8. Preserve shared truth with the session JSONL artifact.

Important:

- resume must stay explicit
- failure must stay honest
- but honest failure should still preserve the shell shape instead of collapsing into a generic error landing page when avoidable

## Mobile Expectation

Mobile is not optional.

The same core mental model must survive on mobile:

- large scrollable activity surface
- bottom input
- compact status treatment
- no tiny-composer anti-pattern
- no giant header that pushes the real session off-screen

The first meaningful viewport on mobile should show the active session stream, not only decorative framing.

## Information Architecture Rule

Two surfaces must stay distinct:

### Session detail

This is where richer evidence belongs:

- dossier
- artifact timeline
- files
- commits
- summaries
- safety framing
- analytical sections

### Interactive route

This is where live continuation belongs:

- replay
- attach
- stream
- prompt
- reconnect

Interactive route may link back to detail, but it must not visually collapse into detail-page behavior.

## Non-Goals For Interactive Mode

The interactive route should not optimize for:

- report density
- explanatory prose density
- large hero blocks
- card dashboards
- replacing the terminal with a static artifact summary

If a UI choice improves reporting but weakens the feeling of live continuation, it belongs on the detail page instead.

## BDD-Level Acceptance

The intended behavior should be testable in browser terms.

### Desktop

Given a resumable or live Codex session,
when the user opens the interactive route,
then the dominant visual surface is the session movement window and the bottom composer is immediately recognizable.

Given the user sends a prompt,
when the system accepts it,
then the main activity surface visibly changes, the underlying session artifact grows, and the route still feels like the same live session.

Given the page reloads,
when reconnect completes,
then the activity surface and composer restore without degrading into a report shell.

### Mobile

Given the same session on a narrow viewport,
when the user opens the interactive route,
then the first meaningful viewport still prioritizes the activity surface and bottom composer over status cards and headers.

## Engineering Implication

The interactive frontend should be treated as a thin browser shell over a real event-driven continuation flow.

That implies:

- event stream and replay matter more than decorative framing
- runtime attach state must be visible inside the stream experience
- prompt submit must mutate the same live timeline
- browser proof must focus on "session feels live" rather than "status cards render"

## Source Alignment

This direction is aligned with the repo plan and external references:

- our SSOT already defined `open route, replay tail, live attach, prompt submit, reconnect` as the core browser path
- Kimi Code documents the Web UI as a browser-based interactive interface for the same CLI flow
- Kimi Code documents `kimi term` as a dedicated terminal UI rather than a report page
- Codex CLI is explicitly terminal-first and session-resume-oriented
- Codex SDK documents `run()`, `runStreamed()`, and `resumeThread()` as continuation over one persisted thread rather than as a report surface

## Reality Check Scenario

The simplest honest test for this mode is not a design review. It is a parity walkthrough:

1. Create a fresh Codex session in terminal with a tiny prompt such as `1 + 2`.
2. Identify the exact `rollout-*.jsonl` file for that session.
3. Open the matching browser interactive route.
4. Compare the browser tail with the terminal result and the JSONL tail.
5. Send the next arithmetic prompt from browser.
6. Confirm that the same JSONL artifact changes.
7. Resume the same session from terminal.
8. Reload browser and confirm the same session continued again.

If this walkthrough fails, the product is not yet "Codex CLI in the browser", even if the route looks polished.

## Immediate Design Consequence For This Repo

For this repository, the interactive route should move toward:

- full-height transcript/activity-first layout
- minimized top chrome
- bottom-anchored composer
- compact, collapsible operational metadata
- fewer dossier-like cards inside the interactive route
- stronger visual resemblance to terminal continuation

Short product verdict:

If the route looks like a dossier with a small text box, it is going in the wrong direction.

If the route looks like a browser shell for the live Codex session, it is going in the right direction.
