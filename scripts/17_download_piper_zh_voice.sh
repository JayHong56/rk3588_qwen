#!/usr/bin/env bash
set -euo pipefail

# Available zh_CN voices in rhasspy/piper-voices:
#   chaowen / huayan / xiao_ya
# Usage:
#   ./17_download_piper_zh_voice.sh
#   ./17_download_piper_zh_voice.sh huayan
#   HF_ENDPOINT=https://hf-mirror.com ./17_download_piper_zh_voice.sh xiao_ya

VOICE="${1:-xiao_ya}"
QUALITY="${PIPER_QUALITY:-medium}"
HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"
REPO="rhasspy/piper-voices"
BASE_DIR="/home/linaro/Qwen/tts/models/piper_zh_${VOICE}_${QUALITY}"

case "$VOICE" in
    chaowen|huayan|xiao_ya)
        ;;
    *)
        echo "[ERR] unsupported voice: $VOICE"
        echo "      choose one of: chaowen, huayan, xiao_ya"
        exit 1
        ;;
esac

MODEL="zh_CN-${VOICE}-${QUALITY}.onnx"
CONFIG="${MODEL}.json"
REMOTE_DIR="$HF_ENDPOINT/$REPO/resolve/main/zh/zh_CN/$VOICE/$QUALITY"

mkdir -p "$BASE_DIR"

download_one() {
    local name="$1"
    local url="$REMOTE_DIR/$name"
    local out="$BASE_DIR/$name"

    if [ -s "$out" ]; then
        echo "[OK] exists: $out"
        return
    fi

    echo "[INFO] download: $url"
    if command -v wget >/dev/null 2>&1; then
        wget -O "$out.tmp" "$url"
    else
        curl -L --fail -o "$out.tmp" "$url"
    fi
    mv "$out.tmp" "$out"
}

download_one "$MODEL"
download_one "$CONFIG"

echo
echo "[OK] Piper voice downloaded"
echo "     voice  : $VOICE"
echo "     quality: $QUALITY"
echo "     dir    : $BASE_DIR"
ls -lh "$BASE_DIR"

cat > "$BASE_DIR/README.txt" <<EOF
Piper zh_CN voice

VOICE=$VOICE
QUALITY=$QUALITY
MODEL=$BASE_DIR/$MODEL
CONFIG=$BASE_DIR/$CONFIG

Source:
$HF_ENDPOINT/$REPO/tree/main/zh/zh_CN/$VOICE/$QUALITY
EOF

