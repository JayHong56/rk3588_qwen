#!/usr/bin/env python3
import argparse
import array
import math
import os
import shutil
import subprocess
import sys
import time


BAR_WIDTH = 50


def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""


def list_sources():
    out = run_cmd(["pactl", "list", "short", "sources"])
    sources = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sources.append(parts[1])
    return sources


def pick_monitor_source(user_source=None):
    sources = list_sources()

    if user_source:
        if user_source in sources:
            return user_source
        print(f"[ERR] 指定的 monitor source 不存在: {user_source}", file=sys.stderr)
        print("[INFO] available sources:")
        for s in sources:
            print("  " + s, file=sys.stderr)
        sys.exit(1)

    default_sink = run_cmd(["pactl", "get-default-sink"]).strip()
    if default_sink:
        candidate = default_sink + ".monitor"
        if candidate in sources:
            return candidate

    # 优先选 USB 声卡 monitor
    for s in sources:
        if "monitor" in s.lower() and "usb" in s.lower():
            return s

    # 再选任意 monitor
    for s in sources:
        if "monitor" in s.lower():
            return s

    print("[ERR] 没找到 PulseAudio monitor source", file=sys.stderr)
    print("[INFO] available sources:")
    for s in sources:
        print("  " + s, file=sys.stderr)
    sys.exit(1)


def dbfs(x):
    if x <= 1e-12:
        return -120.0
    return 20.0 * math.log10(x)


def make_bar(rms_db, peak_db):
    rms_level = max(0.0, min(1.0, (rms_db + 60.0) / 60.0))
    peak_level = max(0.0, min(1.0, (peak_db + 60.0) / 60.0))

    filled = int(rms_level * BAR_WIDTH)
    peak_pos = int(peak_level * BAR_WIDTH)

    chars = [" "] * BAR_WIDTH

    for i in range(filled):
        if i < BAR_WIDTH * 0.55:
            chars[i] = "#"
        elif i < BAR_WIDTH * 0.80:
            chars[i] = "="
        else:
            chars[i] = "!"

    if 0 <= peak_pos < BAR_WIDTH:
        chars[peak_pos] = "|"

    return "".join(chars)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.getenv("MONITOR_SOURCE", ""))
    parser.add_argument("--rate", type=int, default=int(os.getenv("RATE", "48000")))
    parser.add_argument("--channels", type=int, default=int(os.getenv("CHANNELS", "2")))
    parser.add_argument("--chunk-ms", type=int, default=int(os.getenv("CHUNK_MS", "50")))
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        print("Available PulseAudio sources:")
        for s in list_sources():
            print("  " + s)
        return

    if not shutil.which("pactl"):
        print("[ERR] pactl not found", file=sys.stderr)
        sys.exit(1)

    if not shutil.which("parec"):
        print("[ERR] parec not found. 需要 pulseaudio-utils", file=sys.stderr)
        sys.exit(1)

    source = pick_monitor_source(args.source)

    sample_width = 2
    chunk_frames = max(1, int(args.rate * args.chunk_ms / 1000.0))
    chunk_bytes = chunk_frames * args.channels * sample_width

    print(f"[INFO] monitor source : {source}")
    print(f"[INFO] rate           : {args.rate}")
    print(f"[INFO] channels       : {args.channels}")
    print(f"[INFO] chunk          : {args.chunk_ms} ms")
    print("[INFO] 开始实时监控系统输出声音大小，Ctrl+C 退出")
    print()

    cmd = [
        "parec",
        "-d", source,
        "--format=s16le",
        f"--rate={args.rate}",
        f"--channels={args.channels}",
        "--latency-msec=20",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert proc.stdout is not None

    t0 = time.perf_counter()
    max_peak_db = -120.0

    try:
        while True:
            data = proc.stdout.read(chunk_bytes)

            if not data:
                if proc.poll() is not None:
                    break
                time.sleep(0.01)
                continue

            if len(data) % 2:
                data = data[:-1]

            samples = array.array("h")
            samples.frombytes(data)

            if sys.byteorder != "little":
                samples.byteswap()

            if not samples:
                continue

            sum_sq = 0.0
            peak = 0

            for s in samples:
                a = abs(s)
                sum_sq += s * s
                if a > peak:
                    peak = a

            rms = math.sqrt(sum_sq / len(samples))

            rms_db = dbfs(rms / 32768.0)
            peak_db = dbfs(peak / 32768.0)

            if peak_db > max_peak_db:
                max_peak_db = peak_db

            bar = make_bar(rms_db, peak_db)
            elapsed = time.perf_counter() - t0
            clip = " CLIP!" if peak_db > -0.5 else ""

            print(
                f"\r[OUT] {elapsed:8.2f}s "
                f"RMS {rms_db:7.1f} dBFS "
                f"PEAK {peak_db:7.1f} dBFS "
                f"MAX {max_peak_db:7.1f} dBFS "
                f"[{bar}]{clip}",
                end="",
                flush=True,
            )

    except KeyboardInterrupt:
        print()
    finally:
        if proc.poll() is None:
            proc.terminate()

        try:
            _, err = proc.communicate(timeout=1)
        except Exception:
            err = b""

        if err:
            msg = err.decode(errors="ignore").strip()
            if msg and "write() 失败" not in msg and "Broken pipe" not in msg:
                print()
                print("[parec stderr]")
                print(msg)


if __name__ == "__main__":
    main()
