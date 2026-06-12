#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; tmp=$(mktemp)
sed "s#{{PROJECT_ROOT}}#$ROOT#g" "$ROOT/systemd/qwen-sherpa-voice-bridge.service" > "$tmp"
sudo cp "$tmp" /etc/systemd/system/qwen-sherpa-voice-bridge.service; rm -f "$tmp"
sudo systemctl daemon-reload; sudo systemctl enable qwen-sherpa-voice-bridge; sudo systemctl restart qwen-sherpa-voice-bridge
