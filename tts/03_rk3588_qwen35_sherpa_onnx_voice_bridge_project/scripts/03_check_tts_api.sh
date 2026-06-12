#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."; source config/voice_bridge.env
curl -sS "$TTS_API_BASE/health" | python3 -m json.tool
curl -sS -X POST "$TTS_API_BASE/speak" -H 'Content-Type: application/json' -d '{"text":"你好，这是桥接工程的 TTS 测试。","play":true}' | python3 -m json.tool
