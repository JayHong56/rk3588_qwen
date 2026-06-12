#!/usr/bin/env python3
import argparse
import json
import os
import time
from pathlib import Path

import requests

from app.qwen_client import qwen_stream
from app.sentence_splitter import split_ready_sentences
from app.text_normalizer import normalize_for_tts


def load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = os.path.expandvars(value)


def now_text():
    return time.strftime("%F %T")


def log(tag, message):
    print(f"[{now_text()}][{tag}] {message}", flush=True)


def post_tts(text, play, sid, speed, output_dir, index):
    base = os.environ.get("TTS_API_BASE", "http://127.0.0.1:8011").rstrip("/")
    endpoint = "/speak" if play else "/synthesize"
    output = str(output_dir / f"tts_{index:03d}_{int(time.time() * 1000)}.wav")
    payload = {
        "text": text,
        "play": play,
        "sid": sid,
        "speed": speed,
        "output": output,
    }

    t0 = time.perf_counter()
    response = requests.post(base + endpoint, json=payload, timeout=300)
    wall = time.perf_counter() - t0

    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}

    if response.status_code >= 400:
        raise RuntimeError(f"TTS HTTP {response.status_code}: {body}")

    return {
        "http_status": response.status_code,
        "http_wall_s": wall,
        "endpoint": endpoint,
        "response": body,
    }


def main():
    parser = argparse.ArgumentParser(description="Profile local Qwen stream and sherpa-onnx TTS timings.")
    parser.add_argument("prompt", help="Qwen prompt. For Qwen-VL include <image>, or rely on your wrapper.")
    parser.add_argument("--env", default="config/voice_bridge.env")
    parser.add_argument("--out-dir", default="profile_runs")
    parser.add_argument("--play", action="store_true", help="Use /speak and play audio. Default uses /synthesize only.")
    parser.add_argument("--sid", type=int, default=None)
    parser.add_argument("--speed", type=float, default=None)
    args = parser.parse_args()

    load_env(args.env)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    wav_dir = out_dir / f"wavs_{stamp}"
    wav_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / f"profile_{stamp}.json"
    answer_path = out_dir / f"answer_{stamp}.txt"

    sid = int(os.environ.get("TTS_SID", "0")) if args.sid is None else args.sid
    speed = float(os.environ.get("TTS_SPEED", "1.0")) if args.speed is None else args.speed

    log("CONFIG", f"QWEN_BACKEND={os.environ.get('QWEN_BACKEND', 'openai')}")
    log("CONFIG", f"QWEN_CMD={os.environ.get('QWEN_CMD', '')}")
    log("CONFIG", f"TTS_API_BASE={os.environ.get('TTS_API_BASE', 'http://127.0.0.1:8011')}")
    log("CONFIG", f"TTS mode={'/speak with playback' if args.play else '/synthesize without playback'}")
    log("OUTPUT", f"metrics={metrics_path}")
    log("OUTPUT", f"answer={answer_path}")

    qwen_start = time.perf_counter()
    first_chunk_s = None
    answer_parts = []
    pending = ""
    sentence_metrics = []
    sentence_index = 0

    print("助手：", end="", flush=True)

    for chunk in qwen_stream(args.prompt):
        t_now = time.perf_counter()
        if first_chunk_s is None:
            first_chunk_s = t_now - qwen_start
            log("TIME][QWEN", f"first_chunk={first_chunk_s:.3f}s")

        print(chunk, end="", flush=True)
        answer_parts.append(chunk)

        normalized = normalize_for_tts(chunk)
        if not normalized:
            continue

        pending += normalized
        ready, pending = split_ready_sentences(pending)

        for sentence in ready:
            sentence_index += 1
            qwen_ready_s = time.perf_counter() - qwen_start
            chars = len(sentence)
            log("SENTENCE", f"idx={sentence_index} ready_at={qwen_ready_s:.3f}s chars={chars} text={sentence}")

            try:
                tts = post_tts(sentence, args.play, sid, speed, wav_dir, sentence_index)
                resp = tts["response"]
                engine_s = resp.get("elapsed_sec")
                audio_s = resp.get("duration_sec")
                rtf = resp.get("rtf")
                output = resp.get("output")
                log(
                    "TIME][TTS",
                    (
                        f"idx={sentence_index} wall={tts['http_wall_s']:.3f}s "
                        f"engine={engine_s if engine_s is not None else 'NA'}s "
                        f"audio={audio_s if audio_s is not None else 'NA'}s "
                        f"rtf={rtf if rtf is not None else 'NA'} chars={chars}"
                    ),
                )
                sentence_metrics.append(
                    {
                        "index": sentence_index,
                        "text": sentence,
                        "chars": chars,
                        "qwen_sentence_ready_s": qwen_ready_s,
                        "tts_http_wall_s": tts["http_wall_s"],
                        "tts_engine_elapsed_s": engine_s,
                        "tts_audio_duration_s": audio_s,
                        "tts_rtf": rtf,
                        "tts_output": output,
                        "tts_endpoint": tts["endpoint"],
                        "tts_played": bool(resp.get("played", args.play)),
                    }
                )
            except Exception as exc:
                log("ERROR][TTS", f"idx={sentence_index} {exc}")
                sentence_metrics.append(
                    {
                        "index": sentence_index,
                        "text": sentence,
                        "chars": chars,
                        "qwen_sentence_ready_s": qwen_ready_s,
                        "error": repr(exc),
                    }
                )

    final = normalize_for_tts(pending)
    if final:
        sentence_index += 1
        qwen_ready_s = time.perf_counter() - qwen_start
        chars = len(final)
        log("SENTENCE", f"idx={sentence_index} final_at={qwen_ready_s:.3f}s chars={chars} text={final}")
        try:
            tts = post_tts(final, args.play, sid, speed, wav_dir, sentence_index)
            resp = tts["response"]
            engine_s = resp.get("elapsed_sec")
            audio_s = resp.get("duration_sec")
            rtf = resp.get("rtf")
            log(
                "TIME][TTS",
                (
                    f"idx={sentence_index} wall={tts['http_wall_s']:.3f}s "
                    f"engine={engine_s if engine_s is not None else 'NA'}s "
                    f"audio={audio_s if audio_s is not None else 'NA'}s "
                    f"rtf={rtf if rtf is not None else 'NA'} chars={chars}"
                ),
            )
            sentence_metrics.append(
                {
                    "index": sentence_index,
                    "text": final,
                    "chars": chars,
                    "qwen_sentence_ready_s": qwen_ready_s,
                    "tts_http_wall_s": tts["http_wall_s"],
                    "tts_engine_elapsed_s": engine_s,
                    "tts_audio_duration_s": audio_s,
                    "tts_rtf": rtf,
                    "tts_output": resp.get("output"),
                    "tts_endpoint": tts["endpoint"],
                    "tts_played": bool(resp.get("played", args.play)),
                }
            )
        except Exception as exc:
            log("ERROR][TTS", f"idx={sentence_index} {exc}")
            sentence_metrics.append(
                {
                    "index": sentence_index,
                    "text": final,
                    "chars": chars,
                    "qwen_sentence_ready_s": qwen_ready_s,
                    "error": repr(exc),
                }
            )

    print()
    qwen_total_s = time.perf_counter() - qwen_start
    answer = "".join(answer_parts)
    answer_path.write_text(answer, encoding="utf-8")

    tts_ok = [x for x in sentence_metrics if "error" not in x]
    tts_wall_total = sum(float(x.get("tts_http_wall_s") or 0.0) for x in tts_ok)
    tts_engine_total = sum(float(x.get("tts_engine_elapsed_s") or 0.0) for x in tts_ok)
    audio_total = sum(float(x.get("tts_audio_duration_s") or 0.0) for x in tts_ok)
    avg_rtf = (tts_engine_total / audio_total) if audio_total > 0 else None

    summary = {
        "prompt": args.prompt,
        "qwen_first_chunk_s": first_chunk_s,
        "qwen_total_s": qwen_total_s,
        "qwen_answer_chars": len(answer),
        "sentence_count": len(sentence_metrics),
        "tts_success_count": len(tts_ok),
        "tts_http_wall_total_s": tts_wall_total,
        "tts_engine_total_s": tts_engine_total,
        "tts_audio_total_s": audio_total,
        "tts_avg_engine_rtf": avg_rtf,
        "play": args.play,
    }

    metrics = {
        "summary": summary,
        "sentences": sentence_metrics,
        "env": {
            "QWEN_BACKEND": os.environ.get("QWEN_BACKEND"),
            "QWEN_CMD": os.environ.get("QWEN_CMD"),
            "TTS_API_BASE": os.environ.get("TTS_API_BASE"),
            "TTS_SID": sid,
            "TTS_SPEED": speed,
        },
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    log(
        "TIME][QWEN",
        f"total={qwen_total_s:.3f}s first_chunk={first_chunk_s if first_chunk_s is not None else 'NA'}s chars={len(answer)}",
    )
    log(
        "TIME][SUMMARY",
        (
            f"sentences={len(sentence_metrics)} tts_ok={len(tts_ok)} "
            f"tts_wall_total={tts_wall_total:.3f}s tts_engine_total={tts_engine_total:.3f}s "
            f"audio_total={audio_total:.3f}s avg_engine_rtf={avg_rtf if avg_rtf is not None else 'NA'}"
        ),
    )
    log("OUTPUT", f"metrics saved: {metrics_path}")
    log("OUTPUT", f"answer saved: {answer_path}")


if __name__ == "__main__":
    main()
