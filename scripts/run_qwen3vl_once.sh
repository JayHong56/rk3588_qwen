#!/usr/bin/env bash
set -euo pipefail

PROMPT="$*"

LOG_DIR="${QWEN_LOG_DIR:-/home/linaro/Qwen/tts/logs}"
mkdir -p "$LOG_DIR"

RUN_ID="$(date '+%Y%m%d_%H%M%S')"
RAW_OUT="$LOG_DIR/qwen3vl_${RUN_ID}.raw_stdout.log"
ERR_LOG="$LOG_DIR/qwen3vl_${RUN_ID}.stderr.log"
CLEAN_OUT="$LOG_DIR/qwen3vl_${RUN_ID}.clean_answer.log"

log() {
    echo "[$(date '+%F %T')][QWEN-WRAPPER] $*" >&2
    echo "[$(date '+%F %T')][QWEN-WRAPPER] $*" >> "$ERR_LOG"
}

log "start"
log "prompt=$PROMPT"
log "raw stdout log=$RAW_OUT"
log "stderr log=$ERR_LOG"
log "clean answer log=$CLEAN_OUT"

cd /home/linaro/rkllm_qwen3vl4b/demo_Linux_aarch64

export LD_LIBRARY_PATH="$PWD/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL="${RKLLM_LOG_LEVEL:-1}"

log "cwd=$PWD"
log "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
log "check files"

ls -lh \
  ./demo \
  ./qwen3-vl_vision_rk3588.rknn \
  ./qwen3-vl-4b-instruct_w8a8_rk3588.rkllm \
  /home/linaro/test.jpg >&2 || true

CMD=(
  ./demo
  /home/linaro/test.jpg
  ./qwen3-vl_vision_rk3588.rknn
  ./qwen3-vl-4b-instruct_w8a8_rk3588.rkllm
  512
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
    printf "%s\n" "$PROMPT"
    sleep 0.2
    printf "exit\n"
} | "${CMD[@]}" \
    > >(while IFS= read -r line; do
            echo "$line" >> "$RAW_OUT"
            echo "[$(date '+%F %T')][QWEN-DEMO-OUT] $line" >&2
        done) \
    2> >(while IFS= read -r line; do
            echo "[$(date '+%F %T')][QWEN-DEMO-ERR] $line" >&2
            echo "[$(date '+%F %T')][QWEN-DEMO-ERR] $line" >> "$ERR_LOG"
        done)

rc=${PIPESTATUS[1]}

set -e

sleep 0.2

log "demo exit code=$rc"

python3 - "$RAW_OUT" "$PROMPT" "$CLEAN_OUT" <<'PY'
import re
import sys
from pathlib import Path

raw_path = Path(sys.argv[1])
prompt = sys.argv[2]
clean_path = Path(sys.argv[3])

raw = raw_path.read_text(encoding="utf-8", errors="ignore")
raw = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw)
raw = raw.replace("\r", "\n")

# 如果存在明显的回答标记，优先截取最后一个标记之后的内容
markers = [
    "Assistant:",
    "assistant:",
    "ASSISTANT:",
    "助手：",
    "助手:",
    "回答：",
    "回答:",
    "robot:",
    "Robot:",
]

best_pos = -1
best_marker = ""
lower_raw = raw.lower()
for m in markers:
    pos = lower_raw.rfind(m.lower())
    if pos > best_pos:
        best_pos = pos
        best_marker = m

if best_pos >= 0:
    raw = raw[best_pos + len(best_marker):]

noise_patterns = [
    r"^\s*[IWE]\s+rkllm:",
    r"^\s*[IWE]\s+RKNN:",
    r"rkllm-r?untime version",
    r"rknpu driver version",
    r"loading rkllm",
    r"rkllm-toolkit version",
    r"max_context_limit",
    r"target_platform",
    r"model_dtype",
    r"Enabled cpus",
    r"Using mrope",
    r"rkllm init success",
    r"LLM Model loaded",
    r"===the core num",
    r"model input num",
    r"input tensor",
    r"output tensor",
    r"index=\d+",
    r"name=pixel",
    r"n_dims=",
    r"dims=\[",
    r"n_elems=",
    r"fmt=",
    r"size=",
    r"main:",
    r"Warning: Your rknpu driver",
    r"failed to submit",
    r"update to the latest toolkit",
    r"file storage",
]

clean_lines = []

for line in raw.splitlines():
    s = line.strip()
    if not s:
        continue

    if prompt in s:
        continue

    if s.lower() in {"exit", "quit", "q"}:
        continue

    drop = False
    for pat in noise_patterns:
        if re.search(pat, s, flags=re.I):
            drop = True
            break
    if drop:
        continue

    s = re.sub(r"^(assistant|Assistant|ASSISTANT|robot|Robot|助手|回答)\s*[:：]\s*", "", s)
    s = s.strip()

    if s:
        clean_lines.append(s)

answer = "\n".join(clean_lines).strip()
answer = answer.replace(prompt, "").strip()
answer = re.sub(r"\n{3,}", "\n\n", answer)

# 如果清洗后仍然全是英文诊断信息，就认为没拿到回答
bad_words = ["rkllm", "rknn", "tensor", "runtime version", "driver version", "model loaded"]
if answer and sum(w.lower() in answer.lower() for w in bad_words) >= 2:
    answer = ""

if not answer:
    answer = "抱歉，我没有从视觉模型中获取到有效回答。请检查 Qwen 日志。"

clean_path.write_text(answer + "\n", encoding="utf-8")
print(answer, flush=True)
PY

log "clean answer:"
cat "$CLEAN_OUT" >&2

exit "$rc"
