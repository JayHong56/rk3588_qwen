#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a
[[ -f config/voice_bridge.env ]] && source config/voice_bridge.env
set +a
python - <<'PYEOF'
from app.melotts_client import MeloTTSClient
c=MeloTTSClient()
print("tts url:", c.url)
print(c.speak("你好，TTS 接口正常。"))
PYEOF
