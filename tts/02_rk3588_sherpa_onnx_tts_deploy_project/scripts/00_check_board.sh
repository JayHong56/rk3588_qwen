#!/usr/bin/env bash
set -euo pipefail
uname -a
python3 --version || true
command -v aplay >/dev/null && aplay -l || echo '[WARN] aplay not found or no sound card'
[[ -d /sys/class/rknpu ]] && echo '[INFO] RKNPU exists; sherpa TTS CPU mode does not require it' || true
