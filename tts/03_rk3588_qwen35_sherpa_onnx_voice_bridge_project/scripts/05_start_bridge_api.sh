#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."; source config/voice_bridge.env; source .venv/bin/activate
export VOICE_BRIDGE_ENV=config/voice_bridge.env
exec uvicorn app.bridge_api:app --host "${BRIDGE_HOST:-0.0.0.0}" --port "${BRIDGE_PORT:-8021}"
