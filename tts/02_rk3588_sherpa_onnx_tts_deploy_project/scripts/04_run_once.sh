#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
TEXT="${1:-你好，这是 RK3588 上的 sherpa-onnx TTS 测试。}"; OUT="${2:-output/test.wav}"
source .venv/bin/activate
python -m app.sherpa_tts_cli --env config/sherpa_tts.env --text "$TEXT" --output "$OUT"
