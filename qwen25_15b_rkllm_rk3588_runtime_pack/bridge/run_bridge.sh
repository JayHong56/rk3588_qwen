#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export LD_LIBRARY_PATH="$ROOT_DIR/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL="${RKLLM_LOG_LEVEL:-1}"
export MODEL_FILE="${MODEL_FILE:-Qwen2.5-1.5B-Instruct_W8A8_RK3588.rkllm}"
export MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-128}"
export MAX_CONTEXT_LEN="${MAX_CONTEXT_LEN:-4096}"
export BRIDGE_HOST="${BRIDGE_HOST:-0.0.0.0}"
export BRIDGE_PORT="${BRIDGE_PORT:-18080}"
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi
PYTHON_BIN=python3
if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/venv/bin/python"
fi
"$PYTHON_BIN" bridge/demo_bridge_api.py
