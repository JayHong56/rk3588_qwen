#!/usr/bin/env bash
set -euo pipefail

BASE="/home/linaro/Qwen"
TTS_BASE="$BASE/tts"
RUN_DIR="$TTS_BASE/sherpa_fast_verify/verify_$(date '+%Y%m%d_%H%M%S')"
TEXT_FILE="$RUN_DIR/texts.txt"
SUMMARY_JSON="$RUN_DIR/summary.json"
SHERPA_DIR="$TTS_BASE/02_rk3588_sherpa_onnx_tts_deploy_project"

mkdir -p "$RUN_DIR"

cat > "$TEXT_FILE" <<'EOF'
好的。
我明白了，正在处理。
这是 RK3588 上的快速语音合成测试。
如果这句话能很快播放，说明本地轻量 TTS 路线可行。
Qwen 输出文本后，sherpa-onnx 负责低延迟播报。
EOF

cd "$SHERPA_DIR"
source .venv/bin/activate

python3 - "$TEXT_FILE" "$RUN_DIR" "$SUMMARY_JSON" <<'PY'
import json
import os
import sys
import time
from pathlib import Path

from app.sherpa_tts_engine import SherpaTtsEngine, config_from_env

text_file = Path(sys.argv[1])
run_dir = Path(sys.argv[2])
summary_json = Path(sys.argv[3])

env_file = Path("config/sherpa_tts.env")
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, os.path.expandvars(v))

items = []
texts = [x.strip() for x in text_file.read_text(encoding="utf-8").splitlines() if x.strip()]

print(f"[INFO] output={run_dir}")
print(f"[INFO] model_dir={os.environ.get('SHERPA_MODEL_DIR')}")
print(f"[INFO] threads={os.environ.get('SHERPA_NUM_THREADS', '4')}")

t0 = time.perf_counter()
engine = SherpaTtsEngine(config_from_env())
load_sec = time.perf_counter() - t0
print(f"[INFO] engine_load={load_sec:.3f}s")

for i, text in enumerate(texts, 1):
    out = run_dir / f"tts_{i:02d}.wav"
    t0 = time.perf_counter()
    data = engine.synthesize(text, str(out))
    wall = time.perf_counter() - t0

    elapsed = float(data.get("elapsed_sec", wall))
    duration = float(data.get("duration_sec", 0.0))
    rtf = float(data.get("rtf", elapsed / duration if duration > 0 else 0.0))
    size = out.stat().st_size if out.exists() else 0

    item = {
        "idx": i,
        "text": text,
        "chars": len(text),
        "wall_sec": wall,
        "engine_sec": elapsed,
        "audio_sec": duration,
        "rtf": rtf,
        "wav": str(out),
        "bytes": size,
    }
    items.append(item)

    print(
        f"[TTS] idx={i} chars={len(text)} wall={wall:.3f}s "
        f"engine={elapsed:.3f}s audio={duration:.3f}s rtf={rtf:.3f} wav={out}"
    )

avg_rtf = sum(x["rtf"] for x in items) / len(items)
avg_engine = sum(x["engine_sec"] for x in items) / len(items)
avg_wall = sum(x["wall_sec"] for x in items) / len(items)

summary = {
    "run_dir": str(run_dir),
    "model_dir": os.environ.get("SHERPA_MODEL_DIR"),
    "engine_load_sec": load_sec,
    "count": len(items),
    "avg_wall_sec": avg_wall,
    "avg_engine_sec": avg_engine,
    "avg_rtf": avg_rtf,
    "items": items,
}

summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print()
print(f"[SUMMARY] count={len(items)} avg_wall={avg_wall:.3f}s avg_engine={avg_engine:.3f}s avg_rtf={avg_rtf:.3f}")
if avg_rtf < 0.5:
    print("[JUDGE] 很适合语音助手：合成明显快于播放。")
elif avg_rtf < 1.0:
    print("[JUDGE] 可用于语音助手：基本能跟上实时播放。")
else:
    print("[JUDGE] 偏慢：需要换更轻模型、减少线程争抢或改用固定缓存。")
print(f"[OUTPUT] {summary_json}")
PY

echo
echo "[INFO] play first sample"
FIRST_WAV="$(find "$RUN_DIR" -name 'tts_01.wav' | head -n 1)"
if [ -n "$FIRST_WAV" ]; then
    aplay -q "$FIRST_WAV" || true
fi
