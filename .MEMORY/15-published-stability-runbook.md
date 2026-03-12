# Memory Card: Published Stability Runbook

Use this card when:

- the published stack is stale, broken, or partly alive
- you need one command that restores the stack and proves it works
- you want diagnostics with Playwright screenshots and repeated confidence runs

Primary restore command:

```bash
make published-restore
```

What it does:

1. runs `./scripts/start_published.sh`
2. rebuilds and restarts the published stack
3. verifies backend, frontend, and public health through the existing startup flow
4. runs the headless visual smoke pipeline with `t2me` screenshots
5. runs repeated smoke confidence diagnostics
6. prints the newest smoke and confidence summary paths

Important files in the recovery chain:

- `scripts/start_published.sh`
- `scripts/restore_published_stability.sh`
- `frontend/scripts/e2e-smoke-pipeline.mjs`
- `frontend/scripts/e2e-confidence-runner.mjs`
- `scripts/keep_alive.sh`
- `scripts/install_published_watchdog.sh`

Operational model:

- `scripts/start_published.sh` is the immediate restore command
- `make published-restore` is the full restore + proof command
- `scripts/keep_alive.sh` is the minute-by-minute watchdog
- `scripts/install_published_watchdog.sh` installs the reboot + cron healing loop

Evidence locations:

- `tmp/e2e-smoke/run-*/summary.json`
- `tmp/e2e-confidence/*/summary.json`
- `/tmp/nexus-backend.log`
- `/tmp/nexus-frontend.log`
- `/tmp/nexus-frontend-build.log`
- `/tmp/nexus-caddy.log`

Project-specific reminder:

- keep `NEXUS_E2E_SEND_T2ME=1` when screenshots should reach the user
- use the confidence summary, not only one smoke pass, when you want a stronger stability claim
