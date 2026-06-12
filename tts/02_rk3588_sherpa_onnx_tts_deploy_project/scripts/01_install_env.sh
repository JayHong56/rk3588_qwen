#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl wget bzip2 alsa-utils libsndfile1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install sherpa-onnx soundfile numpy fastapi uvicorn pydantic requests
