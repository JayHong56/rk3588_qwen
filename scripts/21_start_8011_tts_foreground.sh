#!/usr/bin/env bash
set -euo pipefail

TTS_DIR="/home/linaro/Qwen/tts/02_rk3588_sherpa_onnx_tts_deploy_project"

cd "$TTS_DIR"

echo "[INFO] foreground 8011 TTS service"
echo "[INFO] config:"
grep -E '^(TTS_ENGINE|PIPER_BIN|PIPER_MODEL|PIPER_CONFIG|SHERPA_MODEL_DIR|TTS_PORT)=' config/sherpa_tts.env || true
echo
echo "[INFO] Keep this terminal open. Stop with Ctrl+C."
echo

exec bash scripts/05_start_api.sh

