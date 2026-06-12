#!/usr/bin/env bash
set -euo pipefail

exec python3 /home/linaro/Qwen/tts/record_system_output.py "$@"
