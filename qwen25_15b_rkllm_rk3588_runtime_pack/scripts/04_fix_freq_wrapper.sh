#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

cd "$ROOT_DIR"
if [[ -f ./fix_freq_rk3588.sh ]]; then
  chmod +x ./fix_freq_rk3588.sh
  sudo ./fix_freq_rk3588.sh
elif [[ -f "$APP_DIR/fix_freq_rk3588.sh" ]]; then
  chmod +x "$APP_DIR/fix_freq_rk3588.sh"
  sudo "$APP_DIR/fix_freq_rk3588.sh"
else
  echo "未找到 fix_freq_rk3588.sh。可从 rknn-llm/scripts 拷贝到本目录。"
fi
