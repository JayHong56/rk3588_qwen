#!/usr/bin/env bash
set -euo pipefail

HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"
DATA_DIR="${PIPER_DATA_DIR:-/home/linaro/Qwen/tts/piper_data}"
TARGET_DIR="$DATA_DIR/g2pW"
URL="$HF_ENDPOINT/datasets/rhasspy/piper-checkpoints/resolve/main/zh/zh_CN/_resources/g2pw.tar.gz"
TMP="/tmp/g2pw.tar.gz"

mkdir -p "$TARGET_DIR"

if [ -s "$TARGET_DIR/g2pw.onnx" ]; then
    echo "[OK] g2pW resource already exists: $TARGET_DIR/g2pw.onnx"
    exit 0
fi

echo "[INFO] download g2pW resource"
echo "       url: $URL"
echo "       dst: $TARGET_DIR"

if command -v wget >/dev/null 2>&1; then
    wget -O "$TMP" "$URL"
else
    curl -L --fail -o "$TMP" "$URL"
fi

tar -xzf "$TMP" -C "$TARGET_DIR"

if [ ! -s "$TARGET_DIR/g2pw.onnx" ]; then
    echo "[ERR] g2pw.onnx not found after extracting"
    echo "      extracted files:"
    find "$TARGET_DIR" -maxdepth 2 -type f | sed -n '1,80p'
    exit 1
fi

echo "[OK] g2pW resource ready: $TARGET_DIR/g2pw.onnx"
ls -lh "$TARGET_DIR" | sed -n '1,80p'

