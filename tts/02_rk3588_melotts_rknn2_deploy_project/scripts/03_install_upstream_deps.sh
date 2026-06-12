#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-${MELOTTS_DIR:-/home/rock/MeloTTS-RKNN2}}"
cd "$(dirname "$0")/.."
source .venv/bin/activate
[[ -f "$ROOT/requirements.txt" ]] || { echo "[ERR] missing $ROOT/requirements.txt"; exit 1; }
python -m pip install -r "$ROOT/requirements.txt"
python -m pip install rknn-toolkit-lite2 || true
