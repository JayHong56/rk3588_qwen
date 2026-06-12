#!/usr/bin/env bash
set -euo pipefail

TTS_DIR="/home/linaro/Qwen/tts/02_rk3588_sherpa_onnx_tts_deploy_project"
VENV_PY="$TTS_DIR/.venv/bin/python"
LOCAL_WHEEL_DIR="${LOCAL_WHEEL_DIR:-/home/linaro/Qwen/offline_assets/zipvoice/wheels}"
INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
TORCH_ONLY_DIR="/home/linaro/Qwen/tts/torch_only_site"
FAST_FRONTEND_DIR="/home/linaro/Qwen/tts/piper_fast_frontend"
ZIPVOICE_PY="/home/linaro/Qwen/tts/02_rk3588_zipvoice_onnx_tts_deploy_project/.venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
    echo "[ERR] venv python not found: $VENV_PY"
    exit 1
fi

echo "[INFO] install local piper_phonemize wheel if present"
if ls "$LOCAL_WHEEL_DIR"/piper_phonemize-*.whl >/dev/null 2>&1; then
    "$VENV_PY" -m pip install "$LOCAL_WHEEL_DIR"/piper_phonemize-*.whl
else
    echo "[WARN] local piper_phonemize wheel not found: $LOCAL_WHEEL_DIR"
fi

echo "[INFO] install piper-tts"
"$VENV_PY" -m pip install piper-tts -i "$INDEX_URL"

echo "[INFO] install Chinese Piper frontend dependency: g2pw"
"$VENV_PY" -m pip install g2pw -i "$INDEX_URL"

echo "[INFO] install Chinese Piper frontend dependency: unicode-rbnf"
"$VENV_PY" -m pip install unicode-rbnf -i "$INDEX_URL"

echo "[INFO] prepare torch-only PYTHONPATH for g2pw"
if [ -x "$ZIPVOICE_PY" ]; then
    ZIP_SP="$("$ZIPVOICE_PY" - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"
    mkdir -p "$TORCH_ONLY_DIR"
    for name in torch torchgen functorch; do
        if [ -e "$ZIP_SP/$name" ] && [ ! -e "$TORCH_ONLY_DIR/$name" ]; then
            ln -s "$ZIP_SP/$name" "$TORCH_ONLY_DIR/$name"
        fi
    done
else
    echo "[WARN] ZipVoice python not found, torch-only PYTHONPATH not prepared"
fi

echo "[INFO] prepare lightweight pypinyin g2pw shim"
if [ -x "$ZIPVOICE_PY" ]; then
    ZIP_SP="$("$ZIPVOICE_PY" - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"
    mkdir -p "$FAST_FRONTEND_DIR/g2pw"
    if [ -e "$ZIP_SP/pypinyin" ] && [ ! -e "$FAST_FRONTEND_DIR/pypinyin" ]; then
        ln -s "$ZIP_SP/pypinyin" "$FAST_FRONTEND_DIR/pypinyin"
    fi
    cat > "$FAST_FRONTEND_DIR/g2pw/__init__.py" <<'PY'
from .api import G2PWConverter
PY
    cat > "$FAST_FRONTEND_DIR/g2pw/api.py" <<'PY'
import re
from pypinyin import Style, lazy_pinyin

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

class G2PWConverter:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, text):
        out = []
        for ch in text:
            if _CJK_RE.match(ch):
                py = lazy_pinyin(ch, style=Style.TONE3, neutral_tone_with_five=True, errors="ignore")
                out.append(py[0] if py else None)
            else:
                out.append(None)
        return [out]
PY
else
    echo "[WARN] ZipVoice python not found, pypinyin shim not prepared"
fi

echo "[INFO] install lightweight sentence_stream compatibility module"
cat > "$TTS_DIR/.venv/lib/python3.9/site-packages/sentence_stream.py" <<'PY'
def stream_to_sentences(chunks):
    buf = ""
    ends = set("。！？!?；;\n")
    for chunk in chunks:
        for ch in str(chunk):
            buf += ch
            if ch in ends:
                s = buf.strip()
                if s:
                    yield s
                buf = ""
    s = buf.strip()
    if s:
        yield s
PY

echo
echo "[INFO] check piper command"
if command -v piper >/dev/null 2>&1; then
    command -v piper
elif [ -x "$TTS_DIR/.venv/bin/piper" ]; then
    echo "$TTS_DIR/.venv/bin/piper"
else
    echo "[ERR] piper command not found after installation"
    exit 1
fi

echo
echo "[OK] piper backend dependencies installed"
