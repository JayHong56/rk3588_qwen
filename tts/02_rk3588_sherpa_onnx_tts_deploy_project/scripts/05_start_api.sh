#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."; source config/sherpa_tts.env; source .venv/bin/activate
export SHERPA_TTS_ENV=config/sherpa_tts.env
exec uvicorn app.sherpa_tts_server:app --host "${TTS_HOST:-0.0.0.0}" --port "${TTS_PORT:-8011}"
