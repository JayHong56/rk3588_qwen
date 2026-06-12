#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."; source .venv/bin/activate
python -m app.qwen_sherpa_voice_chat --env config/voice_bridge.env "${1:-请用三句话介绍一下 RK3588。}"
