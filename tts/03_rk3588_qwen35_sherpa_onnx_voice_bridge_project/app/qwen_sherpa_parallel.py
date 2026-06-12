#!/usr/bin/env python3
import argparse
import json
import os
import queue
import threading
import time
from pathlib import Path

import requests

from app.qwen_client import qwen_stream
from app.sentence_splitter import split_ready_sentences
from app.text_normalizer import normalize_for_tts


STOP = object()


def load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, os.path.expandvars(v))


def now_text():
    return time.strftime("%F %T")


def log(tag, msg):
    print(f"[{now_text()}][{tag}] {msg}", flush=True)


def tts_url(play):
    base = os.environ.get("TTS_API_BASE", "http://127.0.0.1:8011").rstrip("/")
    return base + ("/speak" if play else "/synthesize")


def call_tts(text, play, sid, speed, out_dir, index):
    out = str(out_dir / f"tts_{index:03d}_{int(time.time() * 1000)}.wav")
    payload = {
        "text": text,
        "play": play,
        "sid": sid,
        "speed": speed,
        "output": out,
    }
    start = time.perf_counter()
    resp = requests.post(tts_url(play), json=payload, timeout=300)
    wall = time.perf_counter() - start
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    if resp.status_code >= 400:
        raise RuntimeError(f"TTS HTTP {resp.status_code}: {body}")
    return wall, body


def tts_worker(items, metrics, start_time, play, sid, speed, wav_dir):
    while True:
        item = items.get()
        try:
            if item is STOP:
                log("TTS-WORKER", "stop")
                return

            index, text, ready_s = item
            tts_start_s = time.perf_counter() - start_time
            log("TTS-WORKER", f"start idx={index} queued_at={ready_s:.3f}s start_at={tts_start_s:.3f}s chars={len(text)}")
            log("TTS-WORKER", f"text={text}")

            try:
                wall, body = call_tts(text, play, sid, speed, wav_dir, index)
                done_s = time.perf_counter() - start_time
                engine_s = body.get("elapsed_sec")
                audio_s = body.get("duration_sec")
                rtf = body.get("rtf")
                log(
                    "TIME][TTS",
                    (
                        f"idx={index} wall={wall:.3f}s engine={engine_s if engine_s is not None else 'NA'}s "
                        f"audio={audio_s if audio_s is not None else 'NA'}s rtf={rtf if rtf is not None else 'NA'} "
                        f"done_at={done_s:.3f}s"
                    ),
                )
                metrics.append(
                    {
                        "index": index,
                        "text": text,
                        "chars": len(text),
                        "qwen_sentence_ready_s": ready_s,
                        "tts_start_s": tts_start_s,
                        "tts_done_s": done_s,
                        "tts_queue_wait_s": tts_start_s - ready_s,
                        "tts_http_wall_s": wall,
                        "tts_engine_elapsed_s": engine_s,
                        "tts_audio_duration_s": audio_s,
                        "tts_rtf": rtf,
                        "tts_output": body.get("output"),
                        "tts_played": bool(body.get("played", play)),
                    }
                )
            except Exception as exc:
                done_s = time.perf_counter() - start_time
                log("ERROR][TTS", f"idx={index} {exc}")
                metrics.append(
                    {
                        "index": index,
                        "text": text,
                        "chars": len(text),
                        "qwen_sentence_ready_s": ready_s,
                        "tts_start_s": tts_start_s,
                        "tts_done_s": done_s,
                        "tts_queue_wait_s": tts_start_s - ready_s,
                        "error": repr(exc),
                    }
                )
        finally:
            items.task_done()


def main():
    ap = argparse.ArgumentParser(description="Run Qwen generation and sherpa-onnx TTS playback in parallel.")
    ap.add_argument("prompt")
    ap.add_argument("--env", default="config/voice_bridge.env")
    ap.add_argument("--out-dir", default="parallel_runs")
    ap.add_argument("--no-play", action="store_true", help="Use /synthesize instead of /speak.")
    ap.add_argument("--sid", type=int, default=None)
    ap.add_argument("--speed", type=float, default=None)
    args = ap.parse_args()

    load_env(args.env)
    play = not args.no_play
    sid = int(os.environ.get("TTS_SID", "0")) if args.sid is None else args.sid
    speed = float(os.environ.get("TTS_SPEED", "1.0")) if args.speed is None else args.speed

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_dir = out_dir / f"wavs_{stamp}"
    wav_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / f"parallel_{stamp}.json"
    answer_path = out_dir / f"answer_{stamp}.txt"

    log("CONFIG", f"QWEN_BACKEND={os.environ.get('QWEN_BACKEND', 'openai')}")
    log("CONFIG", f"QWEN_CMD={os.environ.get('QWEN_CMD', '')}")
    log("CONFIG", f"TTS_API_BASE={os.environ.get('TTS_API_BASE', 'http://127.0.0.1:8011')}")
    log("MODE", "PARALLEL: Qwen keeps generating while one TTS worker speaks queued sentences")
    log("OUTPUT", f"metrics={metrics_path}")

    q = queue.Queue()
    metrics = []
    start = time.perf_counter()
    worker = threading.Thread(target=tts_worker, args=(q, metrics, start, play, sid, speed, wav_dir), daemon=True)
    worker.start()

    first_chunk_s = None
    answer_parts = []
    pending = ""
    sent_idx = 0

    print("助手：", end="", flush=True)
    try:
        for chunk in qwen_stream(args.prompt):
            now = time.perf_counter()
            if first_chunk_s is None:
                first_chunk_s = now - start
                log("TIME][QWEN", f"first_chunk={first_chunk_s:.3f}s")

            print(chunk, end="", flush=True)
            answer_parts.append(chunk)

            normalized = normalize_for_tts(chunk)
            if not normalized:
                continue
            pending += normalized
            ready, pending = split_ready_sentences(pending)
            for sentence in ready:
                sent_idx += 1
                ready_s = time.perf_counter() - start
                log("STREAM", f"enqueue idx={sent_idx} ready_at={ready_s:.3f}s chars={len(sentence)}")
                q.put((sent_idx, sentence, ready_s))

        final = normalize_for_tts(pending)
        if final:
            sent_idx += 1
            ready_s = time.perf_counter() - start
            log("STREAM", f"enqueue final idx={sent_idx} ready_at={ready_s:.3f}s chars={len(final)}")
            q.put((sent_idx, final, ready_s))
    finally:
        print()
        qwen_done_s = time.perf_counter() - start
        log("TIME][QWEN", f"done={qwen_done_s:.3f}s first_chunk={first_chunk_s if first_chunk_s is not None else 'NA'}s sentences={sent_idx}")
        log("STREAM", "waiting for TTS queue drain")
        q.put(STOP)
        q.join()

    answer = "".join(answer_parts)
    answer_path.write_text(answer, encoding="utf-8")
    total_s = time.perf_counter() - start

    ok = [x for x in metrics if "error" not in x]
    engine_total = sum(float(x.get("tts_engine_elapsed_s") or 0.0) for x in ok)
    audio_total = sum(float(x.get("tts_audio_duration_s") or 0.0) for x in ok)
    wall_total = sum(float(x.get("tts_http_wall_s") or 0.0) for x in ok)
    summary = {
        "prompt": args.prompt,
        "qwen_first_chunk_s": first_chunk_s,
        "qwen_done_s": qwen_done_s,
        "total_done_s": total_s,
        "answer_chars": len(answer),
        "sentence_count": sent_idx,
        "tts_success_count": len(ok),
        "tts_http_wall_total_s": wall_total,
        "tts_engine_total_s": engine_total,
        "tts_audio_total_s": audio_total,
        "tts_avg_engine_rtf": engine_total / audio_total if audio_total > 0 else None,
        "play": play,
    }
    metrics_path.write_text(
        json.dumps({"summary": summary, "sentences": sorted(metrics, key=lambda x: x["index"])}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log("TIME][SUMMARY", f"qwen_done={qwen_done_s:.3f}s total_done={total_s:.3f}s tts_ok={len(ok)} avg_rtf={summary['tts_avg_engine_rtf']}")
    log("OUTPUT", f"metrics saved: {metrics_path}")
    log("OUTPUT", f"answer saved: {answer_path}")


if __name__ == "__main__":
    main()
