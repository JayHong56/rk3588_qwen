#!/usr/bin/env bash
# Record system audio output (PulseAudio monitor)
# Usage: ./record_system_audio.sh [output_dir]
# Runs until Ctrl+C. Works alongside the TTS script.

set -euo pipefail
OUTDIR="${1:-/home/linaro/Qwen/tts/recordings}"
mkdir -p "$OUTDIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUTFILE="$OUTDIR/system_audio_$TS.wav"

# Find the monitor source for the default sink
DEFAULT_SINK="$(LC_ALL=C pactl info 2>/dev/null | awk '/Default Sink:/{print $3}')"
if [ -n "$DEFAULT_SINK" ]; then
    MONITOR="${DEFAULT_SINK}.monitor"
else
    MONITOR="$(pactl list sources short 2>/dev/null | grep monitor | head -1 | awk '{print $2}')"
fi

if [ -z "$MONITOR" ]; then
    echo "[ERROR] No PulseAudio monitor source found" >&2
    exit 1
fi

echo "Default sink : ${DEFAULT_SINK:-auto}"
echo "Monitor      : $MONITOR"
echo "Output       : $OUTFILE"
echo "Recording... (Ctrl+C to stop)"
echo

parec -d "$MONITOR" --format=s16le --rate=44100 --channels=1 2>/dev/null | \
    sox -t raw -r 44100 -e signed -b 16 -c 1 - "$OUTFILE"
