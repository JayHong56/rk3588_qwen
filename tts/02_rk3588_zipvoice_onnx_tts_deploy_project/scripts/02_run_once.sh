#!/usr/bin/env bash
set -euo pipefail

TEXT="${1:-你好，这是 ZipVoice ONNX 语音合成测试。}"
OUT="${2:-output/test_zipvoice.wav}"

cd "$(dirname "$0")/.."
source config/zipvoice.env
source .venv/bin/activate
export PYTHONPATH="${ZIPVOICE_REPO_DIR}:${PYTHONPATH:-}"

python3 -m zipvoice.bin.infer_zipvoice_onnx \
  --onnx-int8 "$ZIPVOICE_ONNX_INT8" \
  --model-name "$ZIPVOICE_MODEL_NAME" \
  --prompt-wav "$ZIPVOICE_PROMPT_WAV" \
  --prompt-text "$ZIPVOICE_PROMPT_TEXT" \
  --text "$TEXT" \
  --res-wav-path "$OUT" \
  --num-thread "$ZIPVOICE_NUM_THREAD" \
  --num-step "$ZIPVOICE_NUM_STEP" \
  --tokenizer "$ZIPVOICE_TOKENIZER" \
  --lang "$ZIPVOICE_LANG" \
  --speed "$ZIPVOICE_SPEED" \
  --remove-long-sil "$ZIPVOICE_REMOVE_LONG_SIL"

echo "[OK] wav: $OUT"
