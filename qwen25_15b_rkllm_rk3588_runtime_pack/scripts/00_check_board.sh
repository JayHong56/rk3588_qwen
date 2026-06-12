#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

echo "[1/8] Arch: $(uname -m)"
if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "WARN: 当前不是 aarch64，可能不是 RK3588 板端。"
fi

echo "[2/8] OS:"
cat /etc/os-release | sed -n '1,8p' || true

echo "[3/8] Memory:"
free -h || true

echo "[4/8] NPU driver version:"
if [[ -r /sys/kernel/debug/rknpu/version ]]; then
  sudo cat /sys/kernel/debug/rknpu/version || cat /sys/kernel/debug/rknpu/version
else
  echo "MISS /sys/kernel/debug/rknpu/version。请确认 debugfs、RKNPU 驱动和内核镜像。"
fi

echo "[5/8] NPU/DMA device nodes:"
ls -l /dev/dri 2>/dev/null || true
ls -l /dev/rknpu* 2>/dev/null || true

echo "[6/8] Thermal zones:"
for z in /sys/class/thermal/thermal_zone*/temp; do
  [[ -f "$z" ]] && echo "$z: $(cat "$z")"
done

echo "[7/8] Runtime files in current dir:"
ls -lh "$ROOT_DIR"/llm_demo 2>/dev/null || true
ls -lh "$ROOT_DIR"/lib/librkllmrt.so 2>/dev/null || true
ls -lh "$ROOT_DIR"/*.rkllm 2>/dev/null || true

echo "[8/8] Installed app dir: $APP_DIR"
ls -lh "$APP_DIR" 2>/dev/null || true
