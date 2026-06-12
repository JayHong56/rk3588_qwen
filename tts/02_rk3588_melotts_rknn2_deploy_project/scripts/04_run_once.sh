#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a
[[ -f config/melotts.env ]] && source config/melotts.env
set +a
TEXT="${1:-你好，这是 RK3588 MeloTTS-RKNN2 测试。}"
OUT="${2:-output/test.wav}"
mkdir -p "$(dirname "$OUT")"
python -m app.tts_cli "$TEXT" --out "$OUT"
ls -lh "$OUT"
