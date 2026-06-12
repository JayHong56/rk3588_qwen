#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

if [[ ! -f "$ROOT_DIR/$DEMO_BIN" ]]; then
  echo "ERROR: 当前目录缺少 $DEMO_BIN。请先把 PC 端 demo_Linux_aarch64 内容拷贝/解压到本目录。" >&2
  exit 1
fi
if [[ ! -f "$ROOT_DIR/$MODEL_FILE" ]]; then
  echo "ERROR: 当前目录缺少 $MODEL_FILE。请把 .rkllm 模型放到本目录，或修改 .env MODEL_FILE。" >&2
  exit 1
fi
if [[ ! -f "$ROOT_DIR/lib/librkllmrt.so" ]]; then
  echo "ERROR: 当前目录缺少 lib/librkllmrt.so。请确认 PC 端 build-demo 输出完整。" >&2
  exit 1
fi

sudo mkdir -p "$APP_DIR"
sudo cp -a "$ROOT_DIR"/. "$APP_DIR"/
sudo chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"
chmod +x "$APP_DIR/$DEMO_BIN" || true

echo "Installed to $APP_DIR"
