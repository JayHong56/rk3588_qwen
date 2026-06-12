#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a
[[ -f config/voice_bridge.env ]] && source config/voice_bridge.env
set +a
python - <<'PYEOF'
from app.qwen_client import QwenClient
q=QwenClient()
print("backend:", q.backend, "model:", q.model)
text=""
for tok in q.stream_chat("请只回答：Qwen接口正常。"):
    print(tok, end="", flush=True)
    text += tok
    if len(text) > 120:
        break
print("\n[OK] chars:", len(text))
PYEOF
