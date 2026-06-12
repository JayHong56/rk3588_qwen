#!/usr/bin/env python3
import os
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests


QWEN_CMD = os.environ.get("QWEN_CMD", "/home/linaro/Qwen/scripts/run_qwen3vl_stream.sh")
TTS_API_BASE = os.environ.get("TTS_API_BASE", "http://127.0.0.1:8011").rstrip("/")
RUN_DIR = Path(os.environ.get("INTERACTIVE_RUN_DIR", "/home/linaro/Qwen/tts/interactive_piper_runs"))
MAX_SENTENCE_CHARS = int(os.environ.get("INTERACTIVE_TTS_MAX_CHARS", "32"))
MIN_SENTENCE_CHARS = int(os.environ.get("INTERACTIVE_TTS_MIN_CHARS", "4"))
USE_IMAGE = os.environ.get("INTERACTIVE_USE_IMAGE", "0").lower() in {"1", "true", "yes", "on"}
SHORT_REPLY = os.environ.get("INTERACTIVE_SHORT_REPLY", "1").lower() in {"1", "true", "yes", "on"}

STOP = object()


def now():
    return time.strftime("%F %T")


def log(tag, msg):
    print(f"[{now()}][{tag}] {msg}", file=sys.stderr, flush=True)


def clean_text(text):
    text = text.strip()
    if not text:
        return ""
    noise_prefixes = ("I rkllm:", "W rkllm:", "E rkllm:", "I RKNN:", "E RKNN:")
    if text.startswith(noise_prefixes):
        return ""
    text = text.replace("```", "")
    text = text.replace("**", "")
    text = text.replace("<image>", "")
    return text.strip()


def split_ready(buffer):
    ready = []
    start = 0
    endings = set("。！？!?；;\n")
    for i, ch in enumerate(buffer):
        if ch in endings or (i - start + 1) >= MAX_SENTENCE_CHARS:
            sent = buffer[start : i + 1].strip()
            start = i + 1
            sent = clean_text(sent)
            if len(sent) >= MIN_SENTENCE_CHARS:
                ready.append(sent)
    return ready, buffer[start:].strip()


def play_wav(path):
    player = os.environ.get("TTS_AUDIO_PLAYER") or os.environ.get("AUDIO_PLAYER", "aplay")
    device = os.environ.get("TTS_AUDIO_DEVICE") or os.environ.get("AUDIO_DEVICE", "")
    if player == "aplay":
        cmd = ["aplay", "-q"]
        if device:
            cmd += ["-D", device]
        cmd.append(path)
    elif player == "paplay":
        cmd = ["paplay", path]
    elif player == "ffplay":
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", path]
    elif player == "pw-play":
        cmd = ["pw-play", path]
    else:
        cmd = [player, path]
    if "/" not in cmd[0] and shutil.which(cmd[0]) is None:
        raise FileNotFoundError(f"audio player not found: {cmd[0]}")
    subprocess.run(cmd, check=True)


def tts_worker(tts_q):
    while True:
        item = tts_q.get()
        try:
            if item is STOP:
                log("TTS", "worker stop")
                return

            turn_id, idx, text = item
            wav_dir = RUN_DIR / f"turn_{turn_id:03d}"
            wav_dir.mkdir(parents=True, exist_ok=True)
            wav_path = wav_dir / f"tts_{idx:03d}_{int(time.time() * 1000)}.wav"

            log("TTS", f"start turn={turn_id} idx={idx} chars={len(text)} text={text}")
            t0 = time.perf_counter()
            r = requests.post(
                TTS_API_BASE + "/synthesize",
                json={"text": text, "play": False, "output": str(wav_path)},
                timeout=120,
            )
            synth_elapsed = time.perf_counter() - t0
            if r.status_code != 200:
                log("TTS", f"ERROR status={r.status_code} body={r.text[:500]}")
                continue
            data = r.json()
            log(
                "TTS",
                "synth turn={} idx={} wall={:.3f}s engine={} audio={} rtf={}".format(
                    turn_id,
                    idx,
                    synth_elapsed,
                    data.get("elapsed_sec"),
                    data.get("duration_sec"),
                    data.get("rtf"),
                ),
            )

            p0 = time.perf_counter()
            play_wav(str(wav_path))
            log("TTS", f"play turn={turn_id} idx={idx} elapsed={time.perf_counter() - p0:.3f}s")

        except Exception as e:
            log("TTS", f"ERROR {e}")
        finally:
            tts_q.task_done()


def qwen_stream(prompt):
    args = shlex.split(QWEN_CMD) + [prompt]
    log("QWEN", "start: " + " ".join(args))
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=os.environ.copy(),
    )

    def pump_stderr():
        assert proc.stderr is not None
        for line in proc.stderr:
            print(f"[{now()}][QWEN-STDERR] {line}", end="", file=sys.stderr, flush=True)

    threading.Thread(target=pump_stderr, daemon=True).start()

    assert proc.stdout is not None
    first = True
    for line in proc.stdout:
        if first:
            log("QWEN", f"first stdout after {time.perf_counter() - t0:.3f}s")
            first = False
        yield line

    rc = proc.wait()
    log("QWEN", f"finished rc={rc} elapsed={time.perf_counter() - t0:.3f}s")
    if rc != 0:
        raise RuntimeError(f"Qwen command failed: {rc}")


def build_prompt(user_prompt):
    prompt = user_prompt.strip()
    if USE_IMAGE and "<image>" not in prompt:
        prompt = "<image>" + prompt
    if SHORT_REPLY:
        prompt += " 请简短回答，最多三句话，每句话不超过二十个字。"
    return prompt


def check_tts():
    r = requests.get(TTS_API_BASE + "/health", timeout=5)
    r.raise_for_status()
    data = r.json()
    log("CONFIG", f"TTS health={data}")


def main():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    log("CONFIG", f"QWEN_CMD={QWEN_CMD}")
    log("CONFIG", f"TTS_API_BASE={TTS_API_BASE}")
    log("CONFIG", f"USE_IMAGE={USE_IMAGE} SHORT_REPLY={SHORT_REPLY} MAX_SENTENCE_CHARS={MAX_SENTENCE_CHARS}")
    check_tts()

    tts_q = queue.Queue()
    threading.Thread(target=tts_worker, args=(tts_q,), daemon=True).start()

    print("交互式 Qwen + Piper 已启动。输入 exit / quit / q / 退出 结束。", flush=True)
    print("需要看图时，用 INTERACTIVE_USE_IMAGE=1 启动，或直接在问题里写 <image>。", flush=True)

    turn_id = 0
    while True:
        try:
            user_prompt = input("你：").strip()
        except EOFError:
            break

        if not user_prompt:
            continue
        if user_prompt in {"exit", "quit", "q", "退出"}:
            break

        turn_id += 1
        prompt = build_prompt(user_prompt)
        print("助手：", end="", flush=True)
        buffer = ""
        sentence_idx = 0

        try:
            for chunk in qwen_stream(prompt):
                text = clean_text(chunk)
                if not text:
                    continue
                print(text, end="", flush=True)
                buffer += text
                ready, buffer = split_ready(buffer)
                for sent in ready:
                    sentence_idx += 1
                    tts_q.put((turn_id, sentence_idx, sent))

            tail = clean_text(buffer)
            if len(tail) >= MIN_SENTENCE_CHARS:
                sentence_idx += 1
                tts_q.put((turn_id, sentence_idx, tail))

        except Exception as e:
            log("ERROR", str(e))
        finally:
            print()
            log("TTS", "waiting current turn playback...")
            tts_q.join()

    tts_q.put(STOP)
    tts_q.join()
    print("退出。", flush=True)


if __name__ == "__main__":
    main()

