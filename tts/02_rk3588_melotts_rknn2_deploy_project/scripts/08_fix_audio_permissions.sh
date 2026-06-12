#!/usr/bin/env bash
set -euo pipefail
sudo usermod -aG audio "$USER" || true
sudo usermod -aG video "$USER" || true
sudo usermod -aG render "$USER" || true
echo "已加入 audio/video/render 组，可能需要重新登录。"
