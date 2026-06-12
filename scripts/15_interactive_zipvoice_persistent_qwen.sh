#!/usr/bin/env bash
set -euo pipefail

export TTS_API_BASE="http://127.0.0.1:8012"

bash /home/linaro/Qwen/scripts/09_start_zipvoice_tts.sh

exec python3 /home/linaro/Qwen/scripts/14_interactive_zipvoice_persistent_qwen.py
