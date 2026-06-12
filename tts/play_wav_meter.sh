#!/usr/bin/env bash
set -euo pipefail

WAV="${1:-}"

if [ -z "$WAV" ] || [ ! -f "$WAV" ]; then
    echo "[ERR] wav file not found: $WAV" >&2
    exit 1
fi

python3 - "$WAV" <<'PY'
import sys
import wave
import time
import math
import shutil
import struct
import subprocess
from pathlib import Path

wav_path = Path(sys.argv[1]).resolve()

BAR_WIDTH = 48
CHUNK_MS = 50


def meter_bar(rms_db, peak_db):
    # dBFS: 0 是满幅，-60 以下认为静音
    level = max(0.0, min(1.0, (rms_db + 60.0) / 60.0))
    peak_level = max(0.0, min(1.0, (peak_db + 60.0) / 60.0))

    filled = int(level * BAR_WIDTH)
    peak_pos = int(peak_level * BAR_WIDTH)

    chars = [" "] * BAR_WIDTH
    for i in range(filled):
        chars[i] = "#"

    if 0 <= peak_pos < BAR_WIDTH:
        chars[peak_pos] = "|"

    return "".join(chars)


def calc_level_s16le(data, channels):
    if not data:
        return -120.0, -120.0

    sample_count = len(data) // 2
    if sample_count <= 0:
        return -120.0, -120.0

    samples = struct.unpack("<" + "h" * sample_count, data)

    # 多声道直接合并算整体 RMS / peak
    sum_sq = 0.0
    peak = 0

    for s in samples:
        a = abs(s)
        sum_sq += s * s
        if a > peak:
            peak = a

    rms = math.sqrt(sum_sq / sample_count)

    if rms <= 1:
        rms_db = -120.0
    else:
        rms_db = 20.0 * math.log10(rms / 32768.0)

    if peak <= 1:
        peak_db = -120.0
    else:
        peak_db = 20.0 * math.log10(peak / 32768.0)

    return rms_db, peak_db


try:
    wf = wave.open(str(wav_path), "rb")
except Exception as e:
    print(f"[ERR] cannot open wav: {e}", file=sys.stderr)
    sys.exit(1)

channels = wf.getnchannels()
rate = wf.getframerate()
width = wf.getsampwidth()
frames = wf.getnframes()
duration = frames / float(rate) if rate > 0 else 0.0

if width != 2:
    print(f"[WARN] only 16-bit PCM is supported for meter, got sampwidth={width}", file=sys.stderr)

frames_per_chunk = max(1, int(rate * CHUNK_MS / 1000.0))

print(f"[AUDIO] playing: {wav_path}")
print(f"[AUDIO] rate={rate}Hz channels={channels} duration={duration:.2f}s")
print("[AUDIO] RMS bar, peak marker='|'")
print()

# 真正播放仍然交给 aplay
proc = subprocess.Popen(
    ["aplay", "-q", str(wav_path)],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    text=True,
)

start = time.perf_counter()
last_print = ""

try:
    idx = 0
    while True:
        data = wf.readframes(frames_per_chunk)
        if not data:
            break

        idx += 1
        rms_db, peak_db = calc_level_s16le(data, channels)

        bar = meter_bar(rms_db, peak_db)
        elapsed = time.perf_counter() - start

        line = (
            f"\r[VU] {elapsed:6.2f}/{duration:6.2f}s "
            f"RMS {rms_db:7.1f} dBFS "
            f"PEAK {peak_db:7.1f} dBFS "
            f"[{bar}]"
        )

        print(line, end="", flush=True)

        # 按音频时间推进，尽量和 aplay 同步
        target = idx * frames_per_chunk / float(rate)
        sleep_time = target - (time.perf_counter() - start)
        if sleep_time > 0:
            time.sleep(sleep_time)

    proc.wait()
    print()

    if proc.returncode != 0:
        err = proc.stderr.read() if proc.stderr else ""
        print(f"[ERR] aplay failed code={proc.returncode}", file=sys.stderr)
        if err:
            print(err, file=sys.stderr)
        sys.exit(proc.returncode)

except KeyboardInterrupt:
    proc.terminate()
    print()
    raise

finally:
    wf.close()
PY
