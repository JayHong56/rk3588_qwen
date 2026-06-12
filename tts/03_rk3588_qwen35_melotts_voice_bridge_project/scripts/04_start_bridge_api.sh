#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a
[[ -f config/voice_bridge.env ]] && source config/voice_bridge.env
set +a
exec uvicorn app.bridge_api:app --host "${BRIDGE_HOST:-0.0.0.0}" --port "${BRIDGE_PORT:-8020}"
