#!/usr/bin/env bash
set -euo pipefail

BASE="/home/linaro/Qwen"
TTS_DIR="$BASE/tts/02_rk3588_sherpa_onnx_tts_deploy_project"
ENV_FILE="$TTS_DIR/config/sherpa_tts.env"
MODEL_DIR="${PIPER_MODEL_DIR:-$BASE/tts/models/piper_zh_xiao_ya_medium}"
MODEL="${PIPER_MODEL:-$MODEL_DIR/zh_CN-xiao_ya-medium.onnx}"
CONFIG="${PIPER_CONFIG:-$MODEL_DIR/zh_CN-xiao_ya-medium.onnx.json}"

if [ ! -f "$MODEL" ]; then
    echo "[ERR] Piper model not found: $MODEL"
    echo "      Run: $BASE/scripts/17_download_piper_zh_voice.sh"
    exit 1
fi
if [ ! -f "$CONFIG" ]; then
    echo "[ERR] Piper config not found: $CONFIG"
    exit 1
fi

set_kv() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s#^${key}=.*#${key}=${value}#" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

set_kv TTS_ENGINE piper
set_kv PIPER_MODEL "$MODEL"
set_kv PIPER_CONFIG "$CONFIG"

PIPER_BIN_VALUE="${PIPER_BIN:-}"
if [ -z "$PIPER_BIN_VALUE" ]; then
    if [ -x "$TTS_DIR/.venv/bin/piper" ]; then
        PIPER_BIN_VALUE="$TTS_DIR/.venv/bin/piper"
    else
        PIPER_BIN_VALUE="piper"
    fi
fi
set_kv PIPER_BIN "$PIPER_BIN_VALUE"

echo "[INFO] switch 8011 backend to piper"
grep -E '^(TTS_ENGINE|PIPER_BIN|PIPER_MODEL|PIPER_CONFIG)=' "$ENV_FILE"

echo "[INFO] direct piper backend smoke test"
(
    cd "$TTS_DIR"
    .venv/bin/python - <<'PY'
import os
from pathlib import Path

env = Path("config/sherpa_tts.env")
for line in env.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, os.path.expandvars(v))

from app.piper_tts_engine import PiperTtsEngine, piper_config_from_env

engine = PiperTtsEngine(piper_config_from_env())
result = engine.synthesize("你好，这是 Piper 本地后端测试。", "/tmp/piper_direct_test.wav")
print(result)
PY
)

"$BASE/scripts/08_stop_sherpa_tts.sh" || true

echo "[INFO] start 8011 service"
"$BASE/scripts/00_start_sherpa_tts.sh"

echo "[INFO] health"
curl -s http://127.0.0.1:8011/health | python3 -m json.tool

OUT="/tmp/piper_8011_test.wav"
echo "[INFO] synthesize test"
curl -s -X POST http://127.0.0.1:8011/synthesize \
    -H 'Content-Type: application/json' \
    -d "{\"text\":\"你好，这是 Piper 中文语音测试。\",\"play\":false,\"output\":\"$OUT\"}" \
    | python3 -m json.tool

ls -lh "$OUT"
echo "[OK] output: $OUT"
