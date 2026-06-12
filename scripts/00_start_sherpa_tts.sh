#!/usr/bin/env bash
set -euo pipefail

BASE="/home/linaro/Qwen/tts"
TTS_DIR="$BASE/02_rk3588_sherpa_onnx_tts_deploy_project"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/sherpa_tts_service.log"
PID_FILE="$LOG_DIR/sherpa_tts_service.pid"
URL="${SHERPA_TTS_HEALTH_URL:-http://127.0.0.1:8011/health}"

mkdir -p "$LOG_DIR"

if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "[OK] sherpa-onnx TTS already running: $URL"
    exit 0
fi

echo "[INFO] starting sherpa-onnx TTS service..."
echo "[INFO] log: $LOG_FILE"

if command -v setsid >/dev/null 2>&1; then
    (
        cd "$TTS_DIR"
        exec setsid nohup bash scripts/05_start_api.sh </dev/null >"$LOG_FILE" 2>&1
    ) &
else
    (
        cd "$TTS_DIR"
        exec nohup bash scripts/05_start_api.sh </dev/null >"$LOG_FILE" 2>&1
    ) &
fi

echo $! > "$PID_FILE"

for i in $(seq 1 60); do
    if curl -fsS "$URL" >/dev/null 2>&1; then
        echo "[OK] sherpa-onnx TTS ready: $URL"
        exit 0
    fi
    if [ "$i" = "1" ] || [ $((i % 5)) -eq 0 ]; then
        echo "[INFO] waiting for TTS health... ${i}s"
    fi
    sleep 1
done

echo "[ERR] sherpa-onnx TTS did not become ready"
tail -n 120 "$LOG_FILE" || true
exit 1
