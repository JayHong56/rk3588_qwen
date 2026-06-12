#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip setuptools wheel
python -m pip install fastapi uvicorn requests soundfile onnxruntime

if [ ! -d "/home/linaro/Qwen/tts/ZipVoice" ]; then
    git clone https://github.com/k2-fsa/ZipVoice.git /home/linaro/Qwen/tts/ZipVoice
fi

cd /home/linaro/Qwen/tts/ZipVoice
python -m pip install -r requirements.txt

site_packages="$(python - <<'PY'
import site
paths = site.getsitepackages()
print(paths[0])
PY
)"
echo "/home/linaro/Qwen/tts/ZipVoice" > "$site_packages/zipvoice_repo.pth"

echo "[OK] ZipVoice environment installed"
echo "[OK] Added ZipVoice repo to PYTHONPATH via $site_packages/zipvoice_repo.pth"
