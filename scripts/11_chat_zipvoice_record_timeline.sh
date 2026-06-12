#!/usr/bin/env bash
set -euo pipefail

export QWEN_CMD="/home/linaro/Qwen/scripts/run_qwen3vl_stream.sh"
export TTS_API_BASE="http://127.0.0.1:8012"

bash /home/linaro/Qwen/scripts/09_start_zipvoice_tts.sh

if [ "$#" -eq 0 ]; then
    exec /home/linaro/Qwen/tts/record_pipeline_with_timeline.sh "<image>请详细描述这张图片，分成5句话，每句话不超过25个字。"
fi

exec /home/linaro/Qwen/tts/record_pipeline_with_timeline.sh "$@"
