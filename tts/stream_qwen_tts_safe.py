#!/usr/bin/env python3
import os
import re
import sys
import time
import shlex
import subprocess
import threading

import requests


QWEN_CMD = os.environ.get("QWEN_CMD", "/home/linaro/Qwen/run_qwen3vl_stream.sh")
TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8010/speak")
MAX_CHARS = int(os.environ.get("MAX_SENTENCE_CHARS", "80"))


def now():
    return time.strftime("%F %T")


def log(tag, msg):
    print(f"[{now()}][{tag}] {msg}", file=sys.stderr, flush=True)


def clean_text(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"^\s*[-*+]\s*", "", s)
    s = re.sub(r"^\s*\d+[.)、]\s*", "", s)
    s = s.replace("```", "")
    s = s.replace("#", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def split_feed(buf: str):
    out = []
    cur = ""

    for ch in buf:
        cur += ch
        if ch in "。！？!?；;\n" or len(cur) >= MAX_CHARS:
            s = clean_text(cur)
            if s:
                out.append(s)
            cur = ""

    return out, cur


def normalize_tts_url(url: str) -> str:
    url = url.strip()
    if url.endswith("/synthesize"):
        return url[:-len("/synthesize")] + "/speak"
    if url.endswith("/speak"):
        return url
    return url.rstrip("/") + "/speak"


def restart_tts_service():
    log("TTS", "restart MeloTTS service to reset RKNN runtime")

    subprocess.run(
        ["bash", "/home/linaro/Qwen/tts/voice_stack.sh", "stop"],
        check=False,
    )

    time.sleep(1.0)

    subprocess.run(
        ["bash", "/home/linaro/Qwen/tts/voice_stack.sh", "start"],
        check=True,
    )

    time.sleep(1.0)


def tts_speak(idx: int, text: str):
    url = normalize_tts_url(TTS_URL)

    payload = {
        "text": text,
        "play": True,
        "split": False,
    }

    log("TTS", f"POST idx={idx}, chars={len(text)}")
    log("TTS", f"url={url}")
    log("TTS", f"text={text}")

    t0 = time.perf_counter()

    r = requests.post(
        url,
        json=payload,
        timeout=600,
    )

    dt = time.perf_counter() - t0

    log("TTS", f"status={r.status_code}, elapsed={dt:.3f}s")
    log("TTS", f"resp={r.text[:500]}")

    r.raise_for_status()


def main():
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        prompt = "<image>请用一句话描述这张图片，不超过30个字。"

    cmd = shlex.split(QWEN_CMD) + [prompt]

    log("CONFIG", f"QWEN_CMD={QWEN_CMD}")
    log("CONFIG", f"TTS_URL={TTS_URL}")
    log("MODE", "SAFE: Qwen runs first, TTS starts after Qwen exits to avoid NPU contention")
    log("QWEN", "cmd=" + " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
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

    print("助手：", end="", flush=True)

    sentences = []
    buf = ""
    qwen_t0 = time.perf_counter()
    first = True

    for line in proc.stdout:
        if first:
            log("QWEN", f"first stdout after {time.perf_counter() - qwen_t0:.3f}s")
            first = False

        print(line, end="", flush=True)

        buf += line
        parts, buf = split_feed(buf)

        for s in parts:
            sentences.append(s)
            log("QUEUE", f"cache sentence idx={len(sentences)}, chars={len(s)}")

    rc = proc.wait()
    qwen_elapsed = time.perf_counter() - qwen_t0

    tail = clean_text(buf)
    if tail:
        sentences.append(tail)
        log("QUEUE", f"cache final idx={len(sentences)}, chars={len(tail)}")

    print()
    log("QWEN", f"finished rc={rc}, elapsed={qwen_elapsed:.3f}s, sentences={len(sentences)}")

    if rc != 0:
        raise SystemExit(rc)

    if not sentences:
        log("TTS", "no sentence to speak")
        return

    delay = float(os.environ.get("QWEN_TTS_DELAY", "3"))
    log("TTS", f"wait {delay:.1f}s before speaking to let NPU resources settle")
    time.sleep(delay)

    if os.environ.get("RESTART_TTS_AFTER_QWEN", "0").lower() in ("1", "true", "yes", "on"):
        restart_tts_service()

    log("TTS", "start speaking after Qwen finished")

    for i, s in enumerate(sentences, 1):
        tts_speak(i, s)

    log("TTS", "all done")


if __name__ == "__main__":
    main()
