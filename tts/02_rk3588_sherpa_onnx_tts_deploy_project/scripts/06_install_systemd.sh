#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; tmp=$(mktemp)
sed "s#{{PROJECT_ROOT}}#$ROOT#g" "$ROOT/systemd/sherpa-onnx-tts.service" > "$tmp"
sudo cp "$tmp" /etc/systemd/system/sherpa-onnx-tts.service; rm -f "$tmp"
sudo systemctl daemon-reload; sudo systemctl enable sherpa-onnx-tts; sudo systemctl restart sherpa-onnx-tts
