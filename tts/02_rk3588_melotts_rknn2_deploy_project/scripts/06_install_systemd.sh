#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
sudo cp systemd/melotts-rknn2.service /etc/systemd/system/melotts-rknn2.service
sudo sed -i "s#@@PROJECT_DIR@@#$PROJECT_DIR#g" /etc/systemd/system/melotts-rknn2.service
sudo systemctl daemon-reload
sudo systemctl enable --now melotts-rknn2
sudo systemctl status melotts-rknn2 --no-pager || true
