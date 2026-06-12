#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a
[[ -f config/melotts.env ]] && source config/melotts.env
set +a
mkdir -p "${VOICE_OUTPUT_DIR:-output}"
exec uvicorn app.tts_api:app --host "${MELOTTS_HOST:-0.0.0.0}" --port "${MELOTTS_PORT:-8010}"
