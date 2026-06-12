#!/usr/bin/env bash
set -euo pipefail

BASE="/home/linaro/Qwen/tts"
TTS_CFG="$BASE/02_rk3588_melotts_rknn2_deploy_project/config/melotts.env"

echo "========== ALSA cards =========="
cat /proc/asound/cards || true
echo
aplay -l || true
echo

USB_CARD="$(awk '
/USB-Audio/ {
    print $1
    exit
}
' /proc/asound/cards)"

if [ -z "${USB_CARD:-}" ]; then
    USB_CARD="$(aplay -l | awk '
/USB Audio|USB-Audio|Razer USB Sound Card/ {
    if ($1=="card") {
        gsub(":", "", $2)
        print $2
        exit
    }
}
')"
fi

if [ -z "${USB_CARD:-}" ]; then
    echo "[ERR] 没找到 USB 声卡。"
    exit 1
fi

DEVICE="plughw:${USB_CARD},0"

echo "[INFO] detected USB card: $USB_CARD"
echo "[INFO] ALSA device: $DEVICE"

echo "[INFO] stopping voice stack and old audio players..."
cd "$BASE"
./voice_stack.sh stop || true

pkill -f "aplay" || true
pkill -f "ffplay" || true
pkill -f "pw-play" || true
pkill -f "paplay" || true
pkill -f "melotts_rknn.py" || true
pkill -f "uvicorn app.tts_api" || true

sudo fuser -k "/dev/snd/pcmC${USB_CARD}D0p" 2>/dev/null || true

sleep 1

echo "[INFO] unmute mixer..."
amixer -c "$USB_CARD" sset Master 100% unmute >/dev/null 2>&1 || true
amixer -c "$USB_CARD" sset PCM 100% unmute >/dev/null 2>&1 || true
amixer -c "$USB_CARD" sset Speaker 100% unmute >/dev/null 2>&1 || true
amixer -c "$USB_CARD" sset Headphone 100% unmute >/dev/null 2>&1 || true

TEST_WAV="/tmp/test_usb_audio.wav"

python3 - "$TEST_WAV" <<'PY'
import sys, wave, math, struct

path = sys.argv[1]
rate = 44100
duration = 2
freq = 1000
amp = 16000

with wave.open(path, "w") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(rate)
    for i in range(rate * duration):
        v = int(amp * math.sin(2 * math.pi * freq * i / rate))
        w.writeframesraw(struct.pack("<hh", v, v))
PY

echo "[INFO] playing test tone on $DEVICE"
aplay -D "$DEVICE" "$TEST_WAV"

set_kv() {
    local key="$1"
    local val="$2"
    local file="$3"
    if grep -q "^${key}=" "$file"; then
        sed -i "s#^${key}=.*#${key}=${val}#" "$file"
    else
        echo "${key}=${val}" >> "$file"
    fi
}

echo "[INFO] updating $TTS_CFG"
set_kv "AUDIO_PLAYER" "aplay" "$TTS_CFG"
set_kv "AUDIO_DEVICE" "$DEVICE" "$TTS_CFG"

echo
echo "[OK] USB audio configured:"
grep -E "AUDIO_PLAYER|AUDIO_DEVICE" "$TTS_CFG"

echo
echo "Next:"
echo "  cd $BASE"
echo "  ./voice_stack.sh restart"
echo "  ./voice_stack.sh test-tts"
