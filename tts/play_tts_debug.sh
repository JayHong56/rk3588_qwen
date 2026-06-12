#!/usr/bin/env bash
set -euo pipefail

WAV="${1:-}"
LOG="/home/linaro/Qwen/tts/logs/tts_play_debug.log"

mkdir -p /home/linaro/Qwen/tts/logs

{
    echo
    echo "========== $(date '+%F %T') =========="
    echo "[PLAY-DEBUG] wav=$WAV"
    echo "[PLAY-DEBUG] user=$(whoami)"
    echo "[PLAY-DEBUG] PULSE_SERVER=${PULSE_SERVER:-}"
    echo "[PLAY-DEBUG] DISPLAY=${DISPLAY:-}"
    echo "[PLAY-DEBUG] XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}"

    if [ ! -f "$WAV" ]; then
        echo "[PLAY-DEBUG][ERR] wav not found"
        exit 1
    fi

    ls -lh "$WAV"

    echo "[PLAY-DEBUG] pactl info:"
    pactl info 2>&1 || true

    echo "[PLAY-DEBUG] sinks:"
    pactl list short sinks 2>&1 || true

    echo "[PLAY-DEBUG] default sink:"
    pactl get-default-sink 2>&1 || true

    # 优先走 PulseAudio，方便 monitor 看到输出
    if command -v paplay >/dev/null 2>&1; then
        echo "[PLAY-DEBUG] try paplay..."
        PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}" paplay "$WAV"
        RC=$?
        echo "[PLAY-DEBUG] paplay rc=$RC"
        exit "$RC"
    fi

    # fallback: ALSA
    if command -v aplay >/dev/null 2>&1; then
        echo "[PLAY-DEBUG] try aplay..."
        aplay "$WAV"
        RC=$?
        echo "[PLAY-DEBUG] aplay rc=$RC"
        exit "$RC"
    fi

    echo "[PLAY-DEBUG][ERR] no paplay/aplay found"
    exit 1

} 2>&1 | tee -a "$LOG"
