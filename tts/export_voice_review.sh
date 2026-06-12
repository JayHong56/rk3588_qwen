#!/usr/bin/env bash
set -euo pipefail

BASE="/home/linaro/Qwen/tts"
BRIDGE_DIR="$BASE/03_rk3588_qwen35_melotts_voice_bridge_project"
OUT_DIR="$BASE/review_audio"

mkdir -p "$OUT_DIR"

PROMPT="${*:-请描述这张图片。}"
TS="$(date '+%Y%m%d_%H%M%S')"

ANSWER_TXT="$OUT_DIR/answer_${TS}.txt"
FULL_WAV="$OUT_DIR/answer_${TS}.wav"
RUN_LOG="$OUT_DIR/run_${TS}.log"
METRIC_JSON="$OUT_DIR/metric_${TS}.json"
SEG_DIR="$OUT_DIR/segments_${TS}"

mkdir -p "$SEG_DIR"

echo "[INFO] prompt      : $PROMPT"
echo "[INFO] answer txt  : $ANSWER_TXT"
echo "[INFO] full wav    : $FULL_WAV"
echo "[INFO] segment dir : $SEG_DIR"
echo "[INFO] run log     : $RUN_LOG"
echo "[INFO] metric json : $METRIC_JSON"

cd "$BASE"
./voice_stack.sh start

cd "$BRIDGE_DIR"
source .venv/bin/activate

PYTHONUNBUFFERED=1 VOICE_DEBUG=1 python - "$PROMPT" "$ANSWER_TXT" "$FULL_WAV" "$METRIC_JSON" "$SEG_DIR" <<'PY' 2>&1 | tee "$RUN_LOG"
import os
import re
import sys
import json
import time
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv

from app.qwen_client import QwenClient
from app.text_cleaner import clean_for_speech


def now():
    return time.strftime("%F %T")


def log(msg):
    print(f"[{now()}] {msg}", flush=True)


def wav_duration_sec(path: Path):
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception as e:
        log(f"[WARN] failed to read wav duration: {e}")
        return None


def split_sentences(text: str, max_chars: int = 80):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    out = []
    buf = ""

    for ch in text:
        buf += ch
        if ch in "。！？!?；;\n" or len(buf) >= max_chars:
            s = buf.strip()
            if s:
                out.append(s)
            buf = ""

    if buf.strip():
        out.append(buf.strip())

    return out


def concat_wavs(wav_files, out_wav: Path):
    if not wav_files:
        return False

    first = Path(wav_files[0])
    with wave.open(str(first), "rb") as wf:
        params = wf.getparams()

    with wave.open(str(out_wav), "wb") as out:
        out.setparams(params)

        for wav_file in wav_files:
            wav_file = Path(wav_file)
            with wave.open(str(wav_file), "rb") as wf:
                if wf.getparams()[:3] != params[:3]:
                    raise RuntimeError(
                        f"wav params mismatch: {wav_file}, "
                        f"{wf.getparams()} != {params}"
                    )
                out.writeframes(wf.readframes(wf.getnframes()))

    return True


prompt = sys.argv[1]
answer_txt = Path(sys.argv[2]).resolve()
full_wav = Path(sys.argv[3]).resolve()
metric_json = Path(sys.argv[4]).resolve()
seg_dir = Path(sys.argv[5]).resolve()

load_dotenv("config/voice_bridge.env")

total_t0 = time.perf_counter()

# =========================
# 1. Qwen 推理
# =========================
log(f"[EXPORT] prompt={prompt}")
log("[INFER][QWEN][1/1] start")

qwen = QwenClient()
qwen_t0 = time.perf_counter()

answer_parts = []
for token in qwen.stream_chat(prompt):
    print(token, end="", flush=True)
    answer_parts.append(token)

print()
qwen_elapsed = time.perf_counter() - qwen_t0

raw_answer = "".join(answer_parts)
clean_answer = clean_for_speech(raw_answer).strip()

if not clean_answer:
    clean_answer = "抱歉，没有获得有效回答。"

answer_txt.write_text(clean_answer + "\n", encoding="utf-8")

log(
    f"[INFER][QWEN][1/1] done "
    f"wall={qwen_elapsed:.3f}s "
    f"raw_chars={len(raw_answer)} "
    f"clean_chars={len(clean_answer)}"
)

log(f"[EXPORT] saved answer: {answer_txt}")
log("[EXPORT] answer content:")
print(clean_answer, flush=True)

# =========================
# 2. 按句切分，每句一次 TTS 推理
# =========================
max_chars = int(os.getenv("MAX_SENTENCE_CHARS", "80"))
sentences = split_sentences(clean_answer, max_chars=max_chars)

if not sentences:
    sentences = [clean_answer]

log(f"[EXPORT] split into {len(sentences)} TTS inference segment(s)")

tts_url = os.getenv("TTS_API_URL", "http://127.0.0.1:8010/speak")

if tts_url.endswith("/speak"):
    synth_url = tts_url[:-len("/speak")] + "/synthesize"
else:
    synth_url = tts_url

tts_metrics = []
seg_wavs = []

for idx, sentence in enumerate(sentences, start=1):
    seg_wav = seg_dir / f"seg_{idx:03d}.wav"

    payload = {
        "text": sentence,
        "play": False,
        "split": False,
        "out_wav": str(seg_wav),
    }

    log(f"[INFER][TTS][{idx}/{len(sentences)}] start")
    log(f"[INFER][TTS][{idx}/{len(sentences)}] text={sentence}")
    log(f"[INFER][TTS][{idx}/{len(sentences)}] chars={len(sentence)} wav={seg_wav}")

    tts_t0 = time.perf_counter()
    r = requests.post(synth_url, json=payload, timeout=600)
    tts_elapsed = time.perf_counter() - tts_t0

    log(f"[INFER][TTS][{idx}/{len(sentences)}] http_status={r.status_code}")
    r.raise_for_status()

    if not seg_wav.exists() or seg_wav.stat().st_size == 0:
        raise RuntimeError(f"TTS wav not generated: {seg_wav}")

    audio_dur = wav_duration_sec(seg_wav)
    wav_size = seg_wav.stat().st_size

    if audio_dur and audio_dur > 0:
        rtf = tts_elapsed / audio_dur
        log(
            f"[INFER][TTS][{idx}/{len(sentences)}] done "
            f"wall={tts_elapsed:.3f}s "
            f"audio={audio_dur:.3f}s "
            f"rtf={rtf:.3f} "
            f"chars={len(sentence)} "
            f"size={wav_size/1024:.1f}KB"
        )
    else:
        rtf = None
        log(
            f"[INFER][TTS][{idx}/{len(sentences)}] done "
            f"wall={tts_elapsed:.3f}s "
            f"audio=unknown "
            f"rtf=unknown "
            f"chars={len(sentence)} "
            f"size={wav_size/1024:.1f}KB"
        )

    seg_wavs.append(str(seg_wav))

    tts_metrics.append({
        "index": idx,
        "total": len(sentences),
        "text": sentence,
        "chars": len(sentence),
        "wall_time_s": tts_elapsed,
        "audio_duration_s": audio_dur,
        "rtf": rtf,
        "wav": str(seg_wav),
        "wav_size_bytes": wav_size,
    })

# =========================
# 3. 合并音频
# =========================
log("[EXPORT] concatenating segment wavs...")
concat_wavs(seg_wavs, full_wav)

full_audio_dur = wav_duration_sec(full_wav)
total_elapsed = time.perf_counter() - total_t0

tts_total_wall = sum(x["wall_time_s"] for x in tts_metrics)
tts_total_audio = sum((x["audio_duration_s"] or 0) for x in tts_metrics)
tts_avg_rtf = tts_total_wall / tts_total_audio if tts_total_audio > 0 else None

log(f"[TIME] Qwen wall time       : {qwen_elapsed:.3f}s")
log(f"[TIME] TTS total wall time  : {tts_total_wall:.3f}s")
log(f"[TIME] TTS total audio time : {tts_total_audio:.3f}s")

if tts_avg_rtf is not None:
    log(f"[TIME] TTS average RTF     : {tts_avg_rtf:.3f}")
else:
    log("[TIME] TTS average RTF     : unknown")

if full_audio_dur is not None:
    log(f"[TIME] Full wav duration   : {full_audio_dur:.3f}s")

log(f"[TIME] Total wall time      : {total_elapsed:.3f}s")

metric = {
    "prompt": prompt,
    "answer_txt": str(answer_txt),
    "full_wav": str(full_wav),
    "segment_dir": str(seg_dir),
    "qwen_inferences": [
        {
            "index": 1,
            "wall_time_s": qwen_elapsed,
            "raw_chars": len(raw_answer),
            "clean_chars": len(clean_answer),
        }
    ],
    "tts_inferences": tts_metrics,
    "summary": {
        "tts_count": len(tts_metrics),
        "qwen_wall_time_s": qwen_elapsed,
        "tts_total_wall_time_s": tts_total_wall,
        "tts_total_audio_time_s": tts_total_audio,
        "tts_average_rtf": tts_avg_rtf,
        "full_wav_duration_s": full_audio_dur,
        "total_wall_time_s": total_elapsed,
    },
}

metric_json.write_text(json.dumps(metric, ensure_ascii=False, indent=2), encoding="utf-8")

log(f"[EXPORT] full wav saved: {full_wav}")
log(f"[EXPORT] metric saved  : {metric_json}")
PY

echo
echo "[OK] export done"
echo "[OK] text       : $ANSWER_TXT"
echo "[OK] full wav   : $FULL_WAV"
echo "[OK] segment dir: $SEG_DIR"
echo "[OK] log        : $RUN_LOG"
echo "[OK] metric     : $METRIC_JSON"

echo
echo "========== Per Inference Timing =========="
grep -E "\[INFER\]\[QWEN\]|\[INFER\]\[TTS\].*done|\[TIME\]" "$RUN_LOG" || true

echo
ls -lh "$ANSWER_TXT" "$FULL_WAV" "$RUN_LOG" "$METRIC_JSON"
echo
ls -lh "$SEG_DIR"/*.wav 2>/dev/null || true
