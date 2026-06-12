#!/usr/bin/env python3
import argparse
import array
import math
import shutil
import signal
import subprocess
import sys
import time
import wave
from pathlib import Path


STOP = False


def on_signal(signum, frame):
    global STOP
    STOP = True


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


def pick_monitor(user_source):
    sources = list_sources()
    if user_source:
        if user_source in sources:
            return user_source
        raise SystemExit(f"source not found: {user_source}\navailable:\n  " + "\n  ".join(sources))

    default_sink = run_cmd(["pactl", "get-default-sink"]).strip()
    if default_sink:
        candidate = default_sink + ".monitor"
        if candidate in sources:
            return candidate

    for source in sources:
        if "monitor" in source.lower() and "usb" in source.lower():
            return source

    for source in sources:
        if "monitor" in source.lower():
            return source

    raise SystemExit("no PulseAudio monitor source found")


def dbfs(value):
    if value <= 1e-12:
        return -120.0
    return 20.0 * math.log10(value)


def meter(data):
    if len(data) % 2:
        data = data[:-1]
    samples = array.array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return -120.0, -120.0

    peak = 0
    total = 0.0
    for sample in samples:
        a = abs(sample)
        peak = max(peak, a)
        total += sample * sample
    rms = math.sqrt(total / len(samples))
    return dbfs(rms / 32768.0), dbfs(peak / 32768.0)


def bar(rms_db, width=40):
    level = max(0.0, min(1.0, (rms_db + 60.0) / 60.0))
    filled = int(level * width)
    return "#" * filled + " " * (width - filled)


def main():
    parser = argparse.ArgumentParser(description="Record current system audio output from PulseAudio monitor to WAV.")
    parser.add_argument("-o", "--output", default="", help="Output wav path. Default: recordings/system_output_YYYYmmdd_HHMMSS.wav")
    parser.add_argument("-d", "--duration", type=float, default=0.0, help="Duration seconds. 0 means record until Ctrl+C.")
    parser.add_argument("--source", default="", help="PulseAudio monitor source name.")
    parser.add_argument("--rate", type=int, default=48000)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument("--list", action="store_true", help="List PulseAudio sources and exit.")
    args = parser.parse_args()

    if args.list:
        for source in list_sources():
            print(source)
        return

    if not shutil.which("pactl"):
        raise SystemExit("pactl not found")
    if not shutil.which("parec"):
        raise SystemExit("parec not found; install pulseaudio-utils")

    source = pick_monitor(args.source)
    if args.output:
        output = Path(args.output)
    else:
        output = Path("/home/linaro/Qwen/tts/recordings") / f"system_output_{time.strftime('%Y%m%d_%H%M%S')}.wav"
    output.parent.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    chunk_frames = max(1, int(args.rate * args.chunk_ms / 1000.0))
    chunk_bytes = chunk_frames * args.channels * 2

    cmd = [
        "parec",
        "-d",
        source,
        "--format=s16le",
        f"--rate={args.rate}",
        f"--channels={args.channels}",
        "--latency-msec=20",
    ]

    print(f"[REC] source   : {source}")
    print(f"[REC] output   : {output}")
    print(f"[REC] format   : s16le {args.channels}ch {args.rate}Hz")
    print("[REC] stop     : Ctrl+C" if args.duration <= 0 else f"[REC] duration : {args.duration:.2f}s")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None

    start = time.perf_counter()
    bytes_written = 0
    max_peak = -120.0

    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(args.channels)
        wav.setsampwidth(2)
        wav.setframerate(args.rate)

        while not STOP:
            if args.duration > 0 and time.perf_counter() - start >= args.duration:
                break

            data = proc.stdout.read(chunk_bytes)
            if not data:
                if proc.poll() is not None:
                    break
                time.sleep(0.01)
                continue

            wav.writeframes(data)
            bytes_written += len(data)

            rms_db, peak_db = meter(data)
            max_peak = max(max_peak, peak_db)
            elapsed = time.perf_counter() - start
            print(
                f"\r[REC] {elapsed:8.2f}s RMS {rms_db:7.1f} dBFS "
                f"PEAK {peak_db:7.1f} dBFS MAX {max_peak:7.1f} dBFS "
                f"[{bar(rms_db)}]",
                end="",
                flush=True,
            )

    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()

    elapsed = max(time.perf_counter() - start, 1e-6)
    print()
    print(f"[OK] saved: {output}")
    print(f"[OK] duration: {elapsed:.2f}s, data: {bytes_written / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
