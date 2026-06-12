#!/usr/bin/env bash
set -euo pipefail

echo "========== sherpa TTS =========="
curl -fsS http://127.0.0.1:8011/health 2>/dev/null || echo "DOWN: http://127.0.0.1:8011/health"
echo

echo "========== Qwen command =========="
grep -E '^QWEN_BACKEND=|^QWEN_CMD=|^TTS_API_BASE=' \
  /home/linaro/Qwen/tts/03_rk3588_qwen35_sherpa_onnx_voice_bridge_project/config/voice_bridge.env || true
echo

echo "========== ports =========="
ss -lntp | grep -E ':8011|:8021' || true
echo

echo "========== recent sherpa log =========="
tail -n 80 /home/linaro/Qwen/tts/logs/sherpa_tts_service.log 2>/dev/null || true
