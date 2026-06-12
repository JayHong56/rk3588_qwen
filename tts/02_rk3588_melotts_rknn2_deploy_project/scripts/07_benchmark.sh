#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a
[[ -f config/melotts.env ]] && source config/melotts.env
set +a
python tools/benchmark.py --texts "你好。" "RK3588 本地语音合成测试。" "这是一个用于测试延迟的稍长中文句子。"
