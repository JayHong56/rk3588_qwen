#!/usr/bin/env bash
set -euo pipefail
cat <<'EOF'
启动顺序：
1. 启动 Qwen3.5-2B 服务，例如 http://127.0.0.1:8000/v1
2. 启动 MeloTTS-RKNN2 服务：cd 02_rk3588_melotts_rknn2_deploy_project && bash scripts/05_start_api.sh
3. 检查桥接：bash scripts/01_check_qwen_api.sh && bash scripts/02_check_tts_api.sh
4. 运行：bash scripts/03_run_voice_chat.sh "你好，请介绍一下你自己。"
EOF
