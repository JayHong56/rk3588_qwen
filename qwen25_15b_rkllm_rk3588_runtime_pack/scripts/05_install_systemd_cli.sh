#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

SERVICE=/etc/systemd/system/qwen25-rkllm-cli.service
sudo sed \
  -e "s|__APP_DIR__|$APP_DIR|g" \
  -e "s|__RUN_USER__|$RUN_USER|g" \
  -e "s|__MODEL_FILE__|$MODEL_FILE|g" \
  -e "s|__MAX_NEW_TOKENS__|$MAX_NEW_TOKENS|g" \
  -e "s|__MAX_CONTEXT_LEN__|$MAX_CONTEXT_LEN|g" \
  -e "s|__RKLLM_LOG_LEVEL__|$RKLLM_LOG_LEVEL|g" \
  "$ROOT_DIR/systemd/qwen25-rkllm-cli.service.template" | sudo tee "$SERVICE" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable qwen25-rkllm-cli.service

echo "Installed service: $SERVICE"
echo "启动：sudo systemctl start qwen25-rkllm-cli"
echo "日志：journalctl -u qwen25-rkllm-cli -f"
echo "注意：这是交互 demo 的 systemd 包装，更适合自检；生产建议写常驻 RKLLM API 服务。"
