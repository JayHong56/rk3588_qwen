#!/usr/bin/env bash
set -euo pipefail
curl -X POST http://127.0.0.1:8020/chat_speak \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"请用两句话介绍本地语音助手。","speak":true}'
