#!/usr/bin/env python3
import argparse
import os
import queue
import sys
import threading
import time

from dotenv import load_dotenv

from app.qwen_client import QwenClient
from app.melotts_client import MeloTTSClient
from app.sentence_streamer import SentenceStreamer
from app.text_cleaner import clean_for_speech


STOP = object()


def now():
    return time.strftime("%F %T")


def log(tag, msg):
    print(f"[{now()}][{tag}] {msg}", file=sys.stderr, flush=True)


def tts_worker(tts_q: queue.Queue, tts: MeloTTSClient):
    while True:
        item = tts_q.get()

        try:
            if item is STOP:
                log("TTS-WORKER", "stop")
                return

            idx, sentence = item
            sentence = clean_for_speech(sentence).strip()

            if not sentence:
                continue

            log("TTS-WORKER", f"start idx={idx}, chars={len(sentence)}")
            log("TTS-WORKER", f"text={sentence}")

            t0 = time.perf_counter()
            resp = tts.speak(sentence)
            dt = time.perf_counter() - t0

            log("TTS-WORKER", f"done idx={idx}, elapsed={dt:.3f}s, resp={resp}")

        except Exception as e:
            log("TTS-WORKER", f"ERROR: {e}")

        finally:
            tts_q.task_done()


def main():
    load_dotenv("config/voice_bridge.env")

    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--no-speak", action="store_true")
    args = ap.parse_args()

    max_chars = int(os.getenv("MAX_SENTENCE_CHARS", "80"))
    min_chars = int(os.getenv("MIN_SPEAK_CHARS", "4"))

    qwen = QwenClient()
    tts = MeloTTSClient()

    splitter = SentenceStreamer(max_chars=max_chars, min_chars=min_chars)

    tts_q = queue.Queue()

    worker = None
    if not args.no_speak:
        worker = threading.Thread(target=tts_worker, args=(tts_q, tts), daemon=True)
        worker.start()

    print("助手：", end="", flush=True)

    sentence_idx = 0
    qwen_t0 = time.perf_counter()
    first_token_time = None

    try:
        for token in qwen.stream_chat(args.prompt):
            if first_token_time is None:
                first_token_time = time.perf_counter()
                log("QWEN-STREAM", f"first token after {first_token_time - qwen_t0:.3f}s")

            print(token, end="", flush=True)

            for sentence in splitter.feed(token):
                sentence = clean_for_speech(sentence).strip()
                if not sentence:
                    continue

                sentence_idx += 1
                log("STREAM", f"enqueue sentence idx={sentence_idx}, chars={len(sentence)}")

                if not args.no_speak:
                    tts_q.put((sentence_idx, sentence))

        for sentence in splitter.flush():
            sentence = clean_for_speech(sentence).strip()
            if not sentence:
                continue

            sentence_idx += 1
            log("STREAM", f"enqueue final sentence idx={sentence_idx}, chars={len(sentence)}")

            if not args.no_speak:
                tts_q.put((sentence_idx, sentence))

    finally:
        print()

        qwen_elapsed = time.perf_counter() - qwen_t0
        log("QWEN-STREAM", f"qwen stream finished, elapsed={qwen_elapsed:.3f}s, sentences={sentence_idx}")

        if not args.no_speak:
            log("STREAM", "waiting TTS queue drain...")
            tts_q.put(STOP)
            tts_q.join()
            log("STREAM", "all TTS done")


if __name__ == "__main__":
    main()
