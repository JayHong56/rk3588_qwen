#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."; source config/voice_bridge.env
curl -sS -X POST "$QWEN_API_BASE/chat/completions" -H 'Content-Type: application/json' -H "Authorization: Bearer $QWEN_API_KEY" -d "{"model":"$QWEN_MODEL","messages":[{"role":"user","content":"用一句话回答：你能运行吗？"}],"stream":false,"max_tokens":64}" | python3 -m json.tool
