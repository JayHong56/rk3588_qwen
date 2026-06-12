#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/home/linaro/Qwen/tts/logs/zipvoice_tts_service.pid"

if [ -f "$PID_FILE" ]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "[INFO] stopping ZipVoice TTS pid=$pid"
        kill "$pid" 2>/dev/null || true
    fi
fi

for pid in $(ss -lntp | awk '/:8012 / {print $NF}' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u); do
    echo "[INFO] stopping process on 8012 pid=$pid"
    kill "$pid" 2>/dev/null || true
done

rm -f "$PID_FILE"
echo "[OK] stop requested"
