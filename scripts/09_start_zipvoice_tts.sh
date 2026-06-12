#!/usr/bin/env bash
set -euo pipefail

BASE="/home/linaro/Qwen/tts"
TTS_DIR="$BASE/02_rk3588_zipvoice_onnx_tts_deploy_project"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/zipvoice_tts_service.log"
PID_FILE="$LOG_DIR/zipvoice_tts_service.pid"
URL="${ZIPVOICE_TTS_HEALTH_URL:-http://127.0.0.1:8012/health}"

mkdir -p "$LOG_DIR"

if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "[OK] ZipVoice TTS already running: $URL"
    exit 0
fi

echo "[INFO] starting ZipVoice TTS service..."
echo "[INFO] log: $LOG_FILE"

(
    cd "$TTS_DIR"
    exec bash scripts/03_start_api.sh
) >"$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

for _ in $(seq 1 120); do
    if curl -fsS "$URL" >/dev/null 2>&1; then
        echo "[OK] ZipVoice TTS ready: $URL"
        exit 0
    fi
    sleep 1
done

echo "[ERR] ZipVoice TTS did not become ready"
tail -n 160 "$LOG_FILE" || true
exit 1
