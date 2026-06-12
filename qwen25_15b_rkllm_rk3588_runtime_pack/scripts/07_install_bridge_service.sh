#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

if [[ ! -d "$APP_DIR" ]]; then
  echo "ERROR: $APP_DIR 不存在，请先执行 scripts/02_install_app.sh" >&2
  exit 1
fi
if [[ ! -f "$APP_DIR/bridge/requirements.txt" ]]; then
  echo "ERROR: $APP_DIR/bridge/requirements.txt 不存在，请确认 runtime_pack 已合并进应用目录。" >&2
  exit 1
fi

sudo python3 -m venv "$APP_DIR/venv"
sudo "$APP_DIR/venv/bin/python" -m pip install -U pip
sudo "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/bridge/requirements.txt"
sudo chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR/venv"

SERVICE=/etc/systemd/system/qwen25-rkllm-bridge.service
sudo sed \
  -e "s|__APP_DIR__|$APP_DIR|g" \
  -e "s|__RUN_USER__|$RUN_USER|g" \
  -e "s|__MODEL_FILE__|$MODEL_FILE|g" \
  -e "s|__MAX_NEW_TOKENS__|$MAX_NEW_TOKENS|g" \
  -e "s|__MAX_CONTEXT_LEN__|$MAX_CONTEXT_LEN|g" \
  -e "s|__RKLLM_LOG_LEVEL__|$RKLLM_LOG_LEVEL|g" \
  -e "s|__BRIDGE_HOST__|$BRIDGE_HOST|g" \
  -e "s|__BRIDGE_PORT__|$BRIDGE_PORT|g" \
  "$ROOT_DIR/systemd/qwen25-rkllm-bridge.service.template" | sudo tee "$SERVICE" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable qwen25-rkllm-bridge.service

echo "Installed service: $SERVICE"
echo "启动：sudo systemctl start qwen25-rkllm-bridge"
echo "测试：curl -s http://127.0.0.1:$BRIDGE_PORT/health"
echo "注意：bridge 只是验证包装，生产建议直接用 RKLLM C/C++ API 写常驻服务。"
