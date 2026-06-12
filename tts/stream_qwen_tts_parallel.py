#!/usr/bin/env python3
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time

import requests


QWEN_CMD = os.environ.get("QWEN_CMD", "/home/linaro/Qwen/run_qwen3vl_stream.sh")
TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8010/speak")
MAX_CHARS = int(os.environ.get("MAX_SENTENCE_CHARS", "80"))
MIN_CHARS = int(os.environ.get("MIN_SPEAK_CHARS", "4"))
TTS_TIMEOUT = float(os.environ.get("TTS_TIMEOUT", "600"))

STOP = object()


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


def normalize_tts_url(url: str) -> str:
    url = url.strip()
    if url.endswith("/synthesize"):
        return url[:-len("/synthesize")] + "/speak"
    if url.endswith("/speak"):
        return url
    return url.rstrip("/") + "/speak"


def split_feed(buf: str):
    out = []
    cur = ""

    for ch in buf:
        cur += ch
        if ch in "。！？!?；;\n" or len(cur) >= MAX_CHARS:
            s = clean_text(cur)
            if len(s) >= MIN_CHARS:
                out.append(s)
            cur = ""

    return out, cur


def tts_worker(tts_q: queue.Queue):
    url = normalize_tts_url(TTS_URL)
    log("TTS-WORKER", f"start url={url}")

    while True:
        item = tts_q.get()
        try:
            if item is STOP:
                log("TTS-WORKER", "stop")
                return

            idx, text = item
            text = clean_text(text)
            if len(text) < MIN_CHARS:
                log("TTS-WORKER", f"skip idx={idx}, chars={len(text)}")
                continue

            payload = {
                "text": text,
                "play": True,
                "split": False,
            }

            log("TTS-WORKER", f"POST idx={idx}, chars={len(text)}")
            log("TTS-WORKER", f"text={text}")

            t0 = time.perf_counter()
            r = requests.post(url, json=payload, timeout=TTS_TIMEOUT)
            elapsed = time.perf_counter() - t0

            log("TTS-WORKER", f"status={r.status_code}, elapsed={elapsed:.3f}s")
            log("TTS-WORKER", f"resp={r.text[:300]}")
            r.raise_for_status()

        except Exception as exc:
            log("TTS-WORKER", f"ERROR item={item}: {exc}")
        finally:
            tts_q.task_done()


def main():
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        prompt = "<image>请用三句话描述这张图片，每句话不超过20个字。"

    cmd = shlex.split(QWEN_CMD) + [prompt]

    log("CONFIG", f"QWEN_CMD={QWEN_CMD}")
    log("CONFIG", f"TTS_URL={TTS_URL}")
    log("MODE", "PARALLEL: TTS starts as soon as a complete sentence is emitted")
    log("QWEN", "cmd=" + " ".join(cmd))

    tts_q = queue.Queue()
    worker = threading.Thread(target=tts_worker, args=(tts_q,), daemon=True)
    worker.start()

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

    buf = ""
    idx = 0
    qwen_t0 = time.perf_counter()
    first = True

    try:
        for line in proc.stdout:
            if first:
                log("QWEN", f"first stdout after {time.perf_counter() - qwen_t0:.3f}s")
                first = False

            print(line, end="", flush=True)
            buf += line

            parts, buf = split_feed(buf)
            for sentence in parts:
                idx += 1
                log("STREAM", f"enqueue idx={idx}, chars={len(sentence)}")
                tts_q.put((idx, sentence))

        rc = proc.wait()
        qwen_elapsed = time.perf_counter() - qwen_t0

        tail = clean_text(buf)
        if len(tail) >= MIN_CHARS:
            idx += 1
            log("STREAM", f"enqueue final idx={idx}, chars={len(tail)}")
            tts_q.put((idx, tail))

        print()
        log("QWEN", f"finished rc={rc}, elapsed={qwen_elapsed:.3f}s, tts_items={idx}")

        if rc != 0:
            raise SystemExit(rc)

    finally:
        log("STREAM", "waiting TTS queue drain...")
        tts_q.put(STOP)
        tts_q.join()
        log("STREAM", "all TTS done")


if __name__ == "__main__":
    main()
