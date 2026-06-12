#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."; source config/voice_bridge.env; source .venv/bin/activate
if [[ "${DOWNLOAD_QWEN:-false}" == "true" ]]; then python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$QWEN_MODEL_ID', local_dir='$QWEN_LOCAL_DIR', local_dir_use_symlinks=False, resume_download=True)"; else echo '[INFO] skip Qwen download'; fi
if [[ "${DOWNLOAD_SHERPA_TTS:-false}" == "true" ]]; then mkdir -p "$(dirname "$SHERPA_MODEL_DIR")"; tmp=$(mktemp -d); curl -L --retry 5 -o "$tmp/model.tar.bz2" "$SHERPA_MODEL_URL"; tar xf "$tmp/model.tar.bz2" -C "$(dirname "$SHERPA_MODEL_DIR")"; rm -rf "$tmp"; else echo '[INFO] skip sherpa TTS download'; fi
