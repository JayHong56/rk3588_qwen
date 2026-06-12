#!/usr/bin/env bash
set -euo pipefail

BRIDGE_DIR="/home/linaro/Qwen/tts/03_rk3588_qwen35_sherpa_onnx_voice_bridge_project"

export QWEN_CMD="/home/linaro/Qwen/scripts/run_qwen3vl_stream.sh"
export TTS_API_BASE="http://127.0.0.1:8012"

bash /home/linaro/Qwen/scripts/09_start_zipvoice_tts.sh

cd "$BRIDGE_DIR"

echo "交互式 Qwen3-VL + ZipVoice 已启动。"
echo "输入问题后回车；输入 exit / quit / q 退出。"
echo "如果问题涉及图片，可以直接说“请描述这张图片”，脚本会自动补 <image>。"
echo

while true; do
    printf "你："
    IFS= read -r prompt || break

    prompt="$(printf '%s' "$prompt" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [ -z "$prompt" ]; then
        continue
    fi

    case "$prompt" in
        exit|quit|q|退出)
            echo "退出。"
            break
            ;;
    esac

    bash scripts/09_run_pipeline_voice_chat.sh "$prompt"
    echo
done
