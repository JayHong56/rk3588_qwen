#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libsndfile1 alsa-utils git git-lfs curl
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-rk3588.txt
python -m pip install rknn-toolkit-lite2 || true
echo "[OK] rk3588 env ready"
