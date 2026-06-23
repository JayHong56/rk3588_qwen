#!/usr/bin/env bash
set -euo pipefail

export QWEN_MODEL_BACKEND="${QWEN_MODEL_BACKEND:-text}"
export TTS_API_BASE="${TTS_API_BASE:-http://127.0.0.1:8011}"
export INTERACTIVE_SHORT_REPLY="${INTERACTIVE_SHORT_REPLY:-0}"
export INTERACTIVE_TTS_MAX_CHARS="${INTERACTIVE_TTS_MAX_CHARS:-28}"
export INTERACTIVE_USE_IMAGE="${INTERACTIVE_USE_IMAGE:-0}"
export SHERPA_VOLUME="${SHERPA_VOLUME:-2.5}"
export TTS_SPEED="${TTS_SPEED:-0.95}"
export TTS_PAUSE_HARD="${TTS_PAUSE_HARD:-0.30}"     # pause after 。！？
export TTS_PAUSE_SOFT="${TTS_PAUSE_SOFT:-0.10}"     # pause after ，；：、
export TTS_RECORD_DIR="${TTS_RECORD_DIR:-/home/linaro/Qwen/tts/recordings}"
export VOICE_INPUT="${VOICE_INPUT:-1}"
export MIC_DEVICE="${MIC_DEVICE:-default}"
export VAD_THRESHOLD="${VAD_THRESHOLD:-0.5}"
export VAD_MIN_SILENCE_DUR="${VAD_MIN_SILENCE_DUR:-0.5}"
export VAD_MIN_SPEECH_DUR="${VAD_MIN_SPEECH_DUR:-0.25}"
export VAD_MAX_SPEECH_DUR="${VAD_MAX_SPEECH_DUR:-20.0}"
export VAD_MAX_WAIT="${VAD_MAX_WAIT:-60}"
export VAD_PRE_GAIN="${VAD_PRE_GAIN:-100.0}"
export AUDIO_FORWARD="${AUDIO_FORWARD:-0}"               # set to 0 to disable
export AUDIO_FORWARD_HOST="${AUDIO_FORWARD_HOST:-}"       # auto from SSH_CLIENT
export AUDIO_FORWARD_PORT="${AUDIO_FORWARD_PORT:-9876}"
export SYSTEM_RECORD="${SYSTEM_RECORD:-}"                 # set to 0 to disable system audio recording

PY="/home/linaro/Qwen/tts/03_rk3588_qwen35_sherpa_onnx_voice_bridge_project/.venv/bin/python"
if [ ! -x "$PY" ]; then
    PY="python3"
fi

echo "[INFO] interactive persistent Qwen + TTS"
echo "[INFO] QWEN_MODEL_BACKEND=$QWEN_MODEL_BACKEND"
echo "[INFO] TTS_API_BASE=$TTS_API_BASE"
echo "[INFO] VOICE_INPUT=$VOICE_INPUT"
echo "[INFO] INTERACTIVE_USE_IMAGE=$INTERACTIVE_USE_IMAGE"
echo "[INFO] INTERACTIVE_SHORT_REPLY=$INTERACTIVE_SHORT_REPLY"
echo "[INFO] INTERACTIVE_TTS_MAX_CHARS=$INTERACTIVE_TTS_MAX_CHARS"
[ "$VOICE_INPUT" = "1" ] && echo "[INFO] MIC_DEVICE=$MIC_DEVICE VAD(min_silence=${VAD_MIN_SILENCE_DUR}s threshold=${VAD_THRESHOLD})"
if [ -n "${SSH_CLIENT:-}" ] && [ "${AUDIO_FORWARD:-}" != "0" ]; then
    FW_HOST="${AUDIO_FORWARD_HOST:-${SSH_CLIENT%% *}}"
    FW_PORT="${AUDIO_FORWARD_PORT:-9876}"
    echo "[INFO] 音频转发 → ${FW_HOST}:${FW_PORT}（PC 端: python pc_audio_receiver.py ${FW_PORT}）"
fi
echo

if ! curl -fsS "$TTS_API_BASE/health" >/dev/null; then
    echo "[INFO] Piper TTS service is not ready, starting it in background..."
    /home/linaro/Qwen/scripts/00_start_sherpa_tts.sh
fi

if ! curl -fsS "$TTS_API_BASE/health" >/dev/null; then
    echo "[ERROR] Piper TTS service is still not ready: $TTS_API_BASE" >&2
    echo "[HINT] 查看日志：" >&2
    echo "       tail -n 120 /home/linaro/Qwen/tts/logs/sherpa_tts_service.log" >&2
    echo "[HINT] 如果后台启动不稳定，再用前台方式排错：" >&2
    echo "       /home/linaro/Qwen/scripts/21_start_8011_tts_foreground.sh" >&2
    exit 1
fi

# ── System audio recording via PulseAudio monitor ─────────────────────────
cleanup_record() {
    # Kill all child parec/sox processes (not just the pipeline-leader PID)
    pkill -P $$ -x parec 2>/dev/null || true
    pkill -P $$ -x sox   2>/dev/null || true
    # Also kill the tracked job if still alive
    if [ -n "${_RECORD_PID:-}" ] && kill -0 "$_RECORD_PID" 2>/dev/null; then
        kill "$_RECORD_PID" 2>/dev/null || true
        wait "$_RECORD_PID" 2>/dev/null || true
    fi
    echo "[INFO] 录音已停止 → ${REC_OUTFILE:-}"
}
trap cleanup_record EXIT

# Auto-enable system recording when not forwarding audio
if [ "${AUDIO_FORWARD:-}" = "0" ] && [ "${SYSTEM_RECORD:-}" != "0" ]; then
    REC_DIR="${TTS_RECORD_DIR:-/home/linaro/Qwen/tts/recordings}"
    mkdir -p "$REC_DIR"
    REC_TS="$(date +%Y%m%d_%H%M%S)"
    REC_OUTFILE="$REC_DIR/system_audio_$REC_TS.wav"

    DEFAULT_SINK="$(LC_ALL=C pactl info 2>/dev/null | awk '/Default Sink:/{print $3}')"
    MONITOR="${DEFAULT_SINK:+${DEFAULT_SINK}.monitor}"
    MONITOR="${MONITOR:-$(pactl list sources short 2>/dev/null | grep monitor | head -1 | awk '{print $2}')}"

    if [ -n "$MONITOR" ]; then
        echo "[INFO] 系统录音 → $REC_OUTFILE"
        parec -d "$MONITOR" --format=s16le --rate=44100 --channels=1 2>/dev/null | \
            sox -t raw -r 44100 -e signed -b 16 -c 1 - "$REC_OUTFILE" &
        _RECORD_PID=$!
    else
        echo "[WARN] 未找到 PulseAudio monitor 设备，跳过系统录音"
    fi
fi

"$PY" /home/linaro/Qwen/scripts/23_interactive_piper_persistent_qwen.py
