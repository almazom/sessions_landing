#!/bin/bash

set -e

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$PROJECT_ROOT/config/runtime.sh"
load_runtime_config

PUBLIC_URL=${1:-$NEXUS_PUBLIC_URL}

cd "$PROJECT_ROOT/frontend"
NEXUS_PUBLIC_URL="$PUBLIC_URL" \
NEXUS_PLAYWRIGHT_TIMEOUT_MS="$NEXUS_PLAYWRIGHT_TIMEOUT_MS" \
NEXUS_PLAYWRIGHT_HYDRATION_WAIT_MS="$NEXUS_PLAYWRIGHT_HYDRATION_WAIT_MS" \
node scripts/check-published-url.mjs "$PUBLIC_URL"
