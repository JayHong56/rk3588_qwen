#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source config/zipvoice.env
source .venv/bin/activate

export ZIPVOICE_ENV=config/zipvoice.env
export PYTHONPATH="${ZIPVOICE_REPO_DIR}:${PYTHONPATH:-}"
exec uvicorn app.zipvoice_onnx_server:app --host "${ZIPVOICE_HOST:-0.0.0.0}" --port "${ZIPVOICE_PORT:-8012}"
