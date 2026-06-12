#!/usr/bin/env python3
import os
import re
import sys
import time
import queue
import shlex
import threading
import subprocess

import requests


QWEN_CMD = os.environ.get("QWEN_CMD", "/home/linaro/Qwen/run_qwen3vl_stream.sh")
TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8010/speak")

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


def tts_worker(q: queue.Queue):
    idx = 0
    while True:
        item = q.get()
        try:
            if item is STOP:
                log("TTS", "worker stop")
                return

            idx += 1
            text = clean_text(str(item))

            if not text:
                log("TTS", f"skip empty idx={idx}")
                continue

            payload = {
                "text": text,
                "play": True,
                "split": False,
            }

            log("TTS", f"POST idx={idx}, chars={len(text)}")
            log("TTS", f"text={text}")

            t0 = time.perf_counter()
            r = requests.post(TTS_URL, json=payload, timeout=600)
            dt = time.perf_counter() - t0

            log("TTS", f"status={r.status_code}, elapsed={dt:.3f}s")
            log("TTS", f"resp={r.text[:300]}")

            r.raise_for_status()

        except Exception as e:
            log("TTS", f"ERROR: {e}")
        finally:
            q.task_done()


def main():
    prompt = " ".join(sys.argv[1:]).strip() or "<image>请用一句话描述这张图片，不超过30个字。"

    cmd = shlex.split(QWEN_CMD) + [prompt]

    log("CONFIG", f"QWEN_CMD={QWEN_CMD}")
    log("CONFIG", f"TTS_URL={TTS_URL}")
    log("QWEN", "cmd=" + " ".join(cmd))

    q = queue.Queue()
    th = threading.Thread(target=tts_worker, args=(q,), daemon=True)
    th.start()

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

    got = 0
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue

        got += 1
        print(line, flush=True)

        log("STREAM", f"enqueue idx={got}, chars={len(line)}")
        q.put(line)

    rc = proc.wait()
    log("QWEN", f"finished rc={rc}, stdout_lines={got}")

    q.put(STOP)
    q.join()

    if rc != 0:
        raise SystemExit(rc)


if __name__ == "__main__":
    main()
