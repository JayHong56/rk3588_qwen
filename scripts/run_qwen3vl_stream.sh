#!/usr/bin/env bash
set -euo pipefail

USER_PROMPT="$*"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FILTER_SCRIPT="$SCRIPT_DIR/qwen3vl_stream_filter.py"

if [[ "$USER_PROMPT" == *"<image>"* ]]; then
    SEND_PROMPT="$USER_PROMPT"
else
    SEND_PROMPT="<image>${USER_PROMPT}"
fi

LOG_DIR="${QWEN_LOG_DIR:-/home/linaro/Qwen/tts/logs}"
mkdir -p "$LOG_DIR"

RUN_ID="$(date '+%Y%m%d_%H%M%S')"
RAW_OUT="$LOG_DIR/qwen3vl_stream_${RUN_ID}.raw_stdout.log"
ERR_LOG="$LOG_DIR/qwen3vl_stream_${RUN_ID}.stderr.log"
CLEAN_OUT="$LOG_DIR/qwen3vl_stream_${RUN_ID}.clean_stream.log"

log() {
    echo "[$(date '+%F %T')][QWEN-STREAM-WRAPPER] $*" >&2
    echo "[$(date '+%F %T')][QWEN-STREAM-WRAPPER] $*" >> "$ERR_LOG"
}

log "start"
log "user_prompt=$USER_PROMPT"
log "send_prompt=$SEND_PROMPT"
log "raw stdout log=$RAW_OUT"
log "clean stream log=$CLEAN_OUT"

cd /home/linaro/rkllm_qwen3vl4b/demo_Linux_aarch64

export LD_LIBRARY_PATH="$PWD/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL="${RKLLM_LOG_LEVEL:-1}"

CMD=(
  ./demo
  /home/linaro/test.jpg
  ./qwen3-vl_vision_rk3588.rknn
  ./qwen3-vl-4b-instruct_w8a8_rk3588.rkllm
  256
  4096
  3
  "<|vision_start|>"
  "<|vision_end|>"
  "<|image_pad|>"
)

if command -v stdbuf >/dev/null 2>&1; then
    CMD=(stdbuf -oL -eL "${CMD[@]}")
fi

if command -v timeout >/dev/null 2>&1; then
    CMD=(timeout "${QWEN_CMD_TIMEOUT:-600}" "${CMD[@]}")
fi

log "launch demo"
log "cmd=${CMD[*]}"

set +e

{
    printf "%s\n" "$SEND_PROMPT"
    sleep 0.2
    printf "exit\n"
} | "${CMD[@]}" \
    2> >(while IFS= read -r line; do
            echo "[$(date '+%F %T')][QWEN-DEMO-ERR] $line" >&2
            echo "[$(date '+%F %T')][QWEN-DEMO-ERR] $line" >> "$ERR_LOG"
        done) \
    | python3 -u "$FILTER_SCRIPT" \
        "$RAW_OUT" \
        "$CLEAN_OUT" \
        "$USER_PROMPT" \
        "$SEND_PROMPT"

pipe_status=("${PIPESTATUS[@]}")

set -e

input_rc="${pipe_status[0]:-999}"
demo_rc="${pipe_status[1]:-999}"
filter_rc="${pipe_status[2]:-999}"

log "pipeline status: input=$input_rc demo=$demo_rc filter=$filter_rc"

if [ "$demo_rc" -ne 0 ]; then
    log "demo failed rc=$demo_rc"
    exit "$demo_rc"
fi

if [ "$filter_rc" -ne 0 ]; then
    log "filter failed rc=$filter_rc"
    exit "$filter_rc"
fi

log "done"
