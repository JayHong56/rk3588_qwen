#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
sudo cp systemd/qwen-melotts-bridge.service /etc/systemd/system/qwen-melotts-bridge.service
sudo sed -i "s#@@PROJECT_DIR@@#$PROJECT_DIR#g" /etc/systemd/system/qwen-melotts-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now qwen-melotts-bridge
sudo systemctl status qwen-melotts-bridge --no-pager || true
