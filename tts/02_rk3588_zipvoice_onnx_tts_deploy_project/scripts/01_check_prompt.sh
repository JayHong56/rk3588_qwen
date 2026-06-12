#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source config/zipvoice.env

echo "ZIPVOICE_PROMPT_WAV=$ZIPVOICE_PROMPT_WAV"
echo "ZIPVOICE_PROMPT_TEXT=$ZIPVOICE_PROMPT_TEXT"

test -f "$ZIPVOICE_PROMPT_WAV" || {
  echo "[ERR] prompt wav not found: $ZIPVOICE_PROMPT_WAV"
  exit 1
}

if [ "$ZIPVOICE_PROMPT_TEXT" = "这里填写参考音频对应的文字。" ]; then
  echo "[ERR] Please edit config/zipvoice.env and set ZIPVOICE_PROMPT_TEXT"
  exit 1
fi

echo "[OK] prompt configured"
