#!/usr/bin/env bash
set -euo pipefail

export QWEN_CMD="${QWEN_CMD:-/home/linaro/Qwen/scripts/run_qwen3vl_stream.sh}"
export TTS_API_BASE="${TTS_API_BASE:-http://127.0.0.1:8011}"
export INTERACTIVE_SHORT_REPLY="${INTERACTIVE_SHORT_REPLY:-1}"
export INTERACTIVE_TTS_MAX_CHARS="${INTERACTIVE_TTS_MAX_CHARS:-32}"

PY="/home/linaro/Qwen/tts/03_rk3588_qwen35_sherpa_onnx_voice_bridge_project/.venv/bin/python"
if [ ! -x "$PY" ]; then
    PY="python3"
fi

echo "[INFO] interactive Qwen + Piper"
echo "[INFO] QWEN_CMD=$QWEN_CMD"
echo "[INFO] TTS_API_BASE=$TTS_API_BASE"
echo "[INFO] INTERACTIVE_USE_IMAGE=${INTERACTIVE_USE_IMAGE:-0}"
echo

exec "$PY" /home/linaro/Qwen/scripts/22_interactive_piper_qwen.py

