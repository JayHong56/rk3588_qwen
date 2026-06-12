#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
PROMPT="${1:-请介绍一下 RK3588。}"
python -m app.voice_chat_cli "$PROMPT"
