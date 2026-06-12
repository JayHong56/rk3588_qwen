#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

journalctl -u qwen25-rkllm-cli -f
