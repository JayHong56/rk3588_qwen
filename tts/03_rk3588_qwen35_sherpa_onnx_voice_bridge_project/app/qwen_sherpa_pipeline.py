#!/usr/bin/env python3
import argparse
import json
import os
import queue
import shutil
import subprocess
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


def synthesize(text, sid, speed, wav_dir, index):
    base = os.environ.get("TTS_API_BASE", "http://127.0.0.1:8011").rstrip("/")
    output = str((wav_dir / f"tts_{index:03d}_{int(time.time() * 1000)}.wav").resolve())
    payload = {
        "text": text,
        "play": False,
        "sid": sid,
        "speed": speed,
        "output": output,
    }
    t0 = time.perf_counter()
    r = requests.post(base + "/synthesize", json=payload, timeout=300)
    wall = time.perf_counter() - t0
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text}
    if r.status_code >= 400:
        raise RuntimeError(f"TTS HTTP {r.status_code}: {body}")
    return wall, body


def play_wav(path):
    wav = Path(path)
    if not wav.exists():
        raise FileNotFoundError(wav)

    player = os.environ.get("TTS_AUDIO_PLAYER") or os.environ.get("AUDIO_PLAYER", "aplay")
    device = os.environ.get("TTS_AUDIO_DEVICE") or os.environ.get("AUDIO_DEVICE", "")

    if player == "aplay":
        cmd = ["aplay", "-q"]
        if device:
            cmd += ["-D", device]
        cmd.append(str(wav))
    elif player == "paplay":
        cmd = ["paplay", str(wav)]
    elif player == "ffplay":
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(wav)]
    elif player == "pw-play":
        cmd = ["pw-play", str(wav)]
    else:
        cmd = [player, str(wav)]

    if not shutil.which(cmd[0]) and "/" not in cmd[0]:
        raise FileNotFoundError(f"audio player not found: {cmd[0]}")

    subprocess.run(cmd, check=True)


def synth_worker(synth_q, play_cond, play_slots, metrics, start_time, sid, speed, wav_dir):
    while True:
        item = synth_q.get()
        try:
            if item is STOP:
                log("SYNTH-WORKER", "stop")
                with play_cond:
                    play_slots["stopped"] = True
                    play_cond.notify_all()
                return

            index, text, ready_s = item
            start_s = time.perf_counter() - start_time
            log("SYNTH-WORKER", f"start idx={index} queued_at={ready_s:.3f}s start_at={start_s:.3f}s chars={len(text)}")
            log("SYNTH-WORKER", f"text={text}")

            try:
                wall, body = synthesize(text, sid, speed, wav_dir, index)
                done_s = time.perf_counter() - start_time
                engine_s = body.get("elapsed_sec")
                audio_s = body.get("duration_sec")
                rtf = body.get("rtf")
                output = body.get("output")
                log(
                    "TIME][SYNTH",
                    (
                        f"idx={index} wall={wall:.3f}s engine={engine_s if engine_s is not None else 'NA'}s "
                        f"audio={audio_s if audio_s is not None else 'NA'}s rtf={rtf if rtf is not None else 'NA'} "
                        f"done_at={done_s:.3f}s"
                    ),
                )
                result = {
                    "index": index,
                    "text": text,
                    "chars": len(text),
                    "qwen_sentence_ready_s": ready_s,
                    "synth_start_s": start_s,
                    "synth_done_s": done_s,
                    "synth_queue_wait_s": start_s - ready_s,
                    "synth_http_wall_s": wall,
                    "sherpa_engine_elapsed_s": engine_s,
                    "audio_duration_s": audio_s,
                    "sherpa_rtf": rtf,
                    "output": output,
                }
            except Exception as exc:
                done_s = time.perf_counter() - start_time
                log("ERROR][SYNTH", f"idx={index} {exc}")
                result = {
                    "index": index,
                    "text": text,
                    "chars": len(text),
                    "qwen_sentence_ready_s": ready_s,
                    "synth_start_s": start_s,
                    "synth_done_s": done_s,
                    "synth_queue_wait_s": start_s - ready_s,
                    "error": repr(exc),
                }

            with play_cond:
                play_slots[index] = result
                play_cond.notify_all()
            metrics.append(result)
        finally:
            synth_q.task_done()


def play_worker(play_cond, play_slots, metrics, start_time):
    next_index = 1
    while True:
        with play_cond:
            while next_index not in play_slots and not play_slots.get("stopped"):
                play_cond.wait()
            if next_index not in play_slots and play_slots.get("stopped"):
                log("PLAY-WORKER", "stop")
                return
            item = play_slots.pop(next_index)

        if "error" in item:
            log("PLAY-WORKER", f"skip idx={next_index} because synth failed")
            next_index += 1
            continue

        output = item.get("output")
        start_s = time.perf_counter() - start_time
        log("PLAY-WORKER", f"start idx={next_index} start_at={start_s:.3f}s wav={output}")
        try:
            t0 = time.perf_counter()
            play_wav(output)
            wall = time.perf_counter() - t0
            done_s = time.perf_counter() - start_time
            log("TIME][PLAY", f"idx={next_index} wall={wall:.3f}s done_at={done_s:.3f}s")
            item["play_start_s"] = start_s
            item["play_done_s"] = done_s
            item["play_wall_s"] = wall
        except Exception as exc:
            done_s = time.perf_counter() - start_time
            log("ERROR][PLAY", f"idx={next_index} {exc}")
            item["play_start_s"] = start_s
            item["play_done_s"] = done_s
            item["play_error"] = repr(exc)
        next_index += 1


def main():
    ap = argparse.ArgumentParser(description="Pipeline Qwen generation, sherpa synthesis, and audio playback.")
    ap.add_argument("prompt")
    ap.add_argument("--env", default="config/voice_bridge.env")
    ap.add_argument("--out-dir", default="pipeline_runs")
    ap.add_argument("--no-play", action="store_true")
    ap.add_argument("--sid", type=int, default=None)
    ap.add_argument("--speed", type=float, default=None)
    args = ap.parse_args()

    load_env(args.env)
    sid = int(os.environ.get("TTS_SID", "0")) if args.sid is None else args.sid
    speed = float(os.environ.get("TTS_SPEED", "1.0")) if args.speed is None else args.speed

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_dir = out_dir / f"wavs_{stamp}"
    wav_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / f"pipeline_{stamp}.json"
    answer_path = out_dir / f"answer_{stamp}.txt"

    log("CONFIG", f"QWEN_BACKEND={os.environ.get('QWEN_BACKEND', 'openai')}")
    log("CONFIG", f"QWEN_CMD={os.environ.get('QWEN_CMD', '')}")
    log("CONFIG", f"TTS_API_BASE={os.environ.get('TTS_API_BASE', 'http://127.0.0.1:8011')}")
    log("CONFIG", f"AUDIO_PLAYER={os.environ.get('TTS_AUDIO_PLAYER') or os.environ.get('AUDIO_PLAYER', 'aplay')}")
    log("MODE", "PIPELINE: Qwen -> synth queue -> ordered playback queue")
    log("OUTPUT", f"metrics={metrics_path}")

    start = time.perf_counter()
    synth_q = queue.Queue()
    play_cond = threading.Condition()
    play_slots = {}
    metrics = []

    synth_thread = threading.Thread(
        target=synth_worker,
        args=(synth_q, play_cond, play_slots, metrics, start, sid, speed, wav_dir),
        daemon=True,
    )
    synth_thread.start()

    if not args.no_play:
        play_thread = threading.Thread(target=play_worker, args=(play_cond, play_slots, metrics, start), daemon=True)
        play_thread.start()

    first_chunk_s = None
    sent_idx = 0
    pending = ""
    answer_parts = []

    print("助手：", end="", flush=True)
    try:
        for chunk in qwen_stream(args.prompt):
            if first_chunk_s is None:
                first_chunk_s = time.perf_counter() - start
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
                synth_q.put((sent_idx, sentence, ready_s))

        final = normalize_for_tts(pending)
        if final:
            sent_idx += 1
            ready_s = time.perf_counter() - start
            log("STREAM", f"enqueue final idx={sent_idx} ready_at={ready_s:.3f}s chars={len(final)}")
            synth_q.put((sent_idx, final, ready_s))
    finally:
        print()
        qwen_done_s = time.perf_counter() - start
        log("TIME][QWEN", f"done={qwen_done_s:.3f}s first_chunk={first_chunk_s if first_chunk_s is not None else 'NA'}s sentences={sent_idx}")
        log("STREAM", "waiting for synth queue drain")
        synth_q.put(STOP)
        synth_q.join()
        if not args.no_play:
            with play_cond:
                play_slots["stopped"] = True
                play_cond.notify_all()

    # Give the playback worker a short chance to finish after synth queue is empty.
    if not args.no_play:
        while True:
            played = [m for m in metrics if "play_done_s" in m or "play_error" in m or "error" in m]
            if len(played) >= len(metrics):
                break
            time.sleep(0.05)

    total_s = time.perf_counter() - start
    answer = "".join(answer_parts)
    answer_path.write_text(answer, encoding="utf-8")

    ok = [m for m in metrics if "error" not in m]
    engine_total = sum(float(m.get("sherpa_engine_elapsed_s") or 0.0) for m in ok)
    audio_total = sum(float(m.get("audio_duration_s") or 0.0) for m in ok)
    synth_wall_total = sum(float(m.get("synth_http_wall_s") or 0.0) for m in ok)
    play_wall_total = sum(float(m.get("play_wall_s") or 0.0) for m in ok)

    summary = {
        "prompt": args.prompt,
        "qwen_first_chunk_s": first_chunk_s,
        "qwen_done_s": qwen_done_s,
        "total_done_s": total_s,
        "answer_chars": len(answer),
        "sentence_count": sent_idx,
        "tts_success_count": len(ok),
        "synth_http_wall_total_s": synth_wall_total,
        "sherpa_engine_total_s": engine_total,
        "audio_total_s": audio_total,
        "play_wall_total_s": play_wall_total,
        "avg_engine_rtf": engine_total / audio_total if audio_total > 0 else None,
        "play": not args.no_play,
    }
    metrics_path.write_text(
        json.dumps({"summary": summary, "sentences": sorted(metrics, key=lambda x: x["index"])}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log("TIME][SUMMARY", f"qwen_done={qwen_done_s:.3f}s total_done={total_s:.3f}s tts_ok={len(ok)} avg_rtf={summary['avg_engine_rtf']}")
    log("OUTPUT", f"metrics saved: {metrics_path}")
    log("OUTPUT", f"answer saved: {answer_path}")


if __name__ == "__main__":
    main()
