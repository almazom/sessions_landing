SHELL := /bin/bash

.PHONY: e2e-smoke e2e-login e2e-smoke-confidence e2e-login-confidence

e2e-smoke:
	cd frontend && npm run smoke:published:visual

e2e-login:
	cd frontend && npm run login:published:visual

e2e-smoke-confidence:
	cd frontend && NEXUS_E2E_PIPELINE_MODE=smoke npm run confidence:published:visual

e2e-login-confidence:
	cd frontend && NEXUS_E2E_PIPELINE_MODE=login npm run confidence:published:visual
