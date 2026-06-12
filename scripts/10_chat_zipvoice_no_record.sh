#!/usr/bin/env bash
set -euo pipefail

BRIDGE_DIR="/home/linaro/Qwen/tts/03_rk3588_qwen35_sherpa_onnx_voice_bridge_project"

export QWEN_CMD="/home/linaro/Qwen/scripts/run_qwen3vl_stream.sh"
export TTS_API_BASE="http://127.0.0.1:8012"

bash /home/linaro/Qwen/scripts/09_start_zipvoice_tts.sh

cd "$BRIDGE_DIR"
if [ "$#" -eq 0 ]; then
    exec bash scripts/09_run_pipeline_voice_chat.sh "<image>请详细描述这张图片，分成5句话，每句话不超过25个字。"
fi

exec bash scripts/09_run_pipeline_voice_chat.sh "$@"
