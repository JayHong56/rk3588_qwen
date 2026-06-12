#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."; source config/sherpa_tts.env
for f in model.onnx lexicon.txt tokens.txt; do [[ -f "$SHERPA_MODEL_DIR/$f" ]] || { echo "missing $f"; exit 2; }; done
ls -lh "$SHERPA_MODEL_DIR" | sed -n '1,40p'
