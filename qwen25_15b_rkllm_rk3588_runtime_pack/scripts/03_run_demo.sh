#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

cd "$ROOT_DIR"
if [[ -d "$APP_DIR" && -x "$APP_DIR/$DEMO_BIN" && -f "$APP_DIR/$MODEL_FILE" ]]; then
  cd "$APP_DIR"
fi

export LD_LIBRARY_PATH="$PWD/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL="$RKLLM_LOG_LEVEL"

echo "Running: ./$DEMO_BIN ./$MODEL_FILE $MAX_NEW_TOKENS $MAX_CONTEXT_LEN"
echo "输入 exit 退出；输入 clear 清 KV cache。"
./"$DEMO_BIN" "./$MODEL_FILE" "$MAX_NEW_TOKENS" "$MAX_CONTEXT_LEN"
