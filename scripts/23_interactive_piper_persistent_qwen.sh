#!/usr/bin/env bash
set -euo pipefail

export TTS_API_BASE="${TTS_API_BASE:-http://127.0.0.1:8011}"
export INTERACTIVE_SHORT_REPLY="${INTERACTIVE_SHORT_REPLY:-1}"
export INTERACTIVE_TTS_MAX_CHARS="${INTERACTIVE_TTS_MAX_CHARS:-28}"
export INTERACTIVE_USE_IMAGE="${INTERACTIVE_USE_IMAGE:-0}"

PY="/home/linaro/Qwen/tts/03_rk3588_qwen35_sherpa_onnx_voice_bridge_project/.venv/bin/python"
if [ ! -x "$PY" ]; then
    PY="python3"
fi

echo "[INFO] interactive persistent Qwen + Piper"
echo "[INFO] TTS_API_BASE=$TTS_API_BASE"
echo "[INFO] INTERACTIVE_USE_IMAGE=$INTERACTIVE_USE_IMAGE"
echo "[INFO] INTERACTIVE_SHORT_REPLY=$INTERACTIVE_SHORT_REPLY"
echo "[INFO] INTERACTIVE_TTS_MAX_CHARS=$INTERACTIVE_TTS_MAX_CHARS"
echo

if ! curl -fsS "$TTS_API_BASE/health" >/dev/null; then
    echo "[INFO] Piper TTS service is not ready, starting it in background..."
    /home/linaro/Qwen/scripts/00_start_sherpa_tts.sh
fi

if ! curl -fsS "$TTS_API_BASE/health" >/dev/null; then
    echo "[ERROR] Piper TTS service is still not ready: $TTS_API_BASE" >&2
    echo "[HINT] 查看日志：" >&2
    echo "       tail -n 120 /home/linaro/Qwen/tts/logs/sherpa_tts_service.log" >&2
    echo "[HINT] 如果后台启动不稳定，再用前台方式排错：" >&2
    echo "       /home/linaro/Qwen/scripts/21_start_8011_tts_foreground.sh" >&2
    exit 1
fi

exec "$PY" /home/linaro/Qwen/scripts/23_interactive_piper_persistent_qwen.py
