#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source config/sherpa_tts.env
mkdir -p "$(dirname "$SHERPA_MODEL_DIR")"
if [[ -f "$SHERPA_MODEL_DIR/model.onnx" ]]; then echo '[OK] model exists'; exit 0; fi
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -L --retry 5 -o "$tmp/model.tar.bz2" "$SHERPA_MODEL_URL"
tar xf "$tmp/model.tar.bz2" -C "$(dirname "$SHERPA_MODEL_DIR")"
[[ -f "$SHERPA_MODEL_DIR/model.onnx" ]] || { echo "missing model.onnx under $SHERPA_MODEL_DIR"; exit 2; }
