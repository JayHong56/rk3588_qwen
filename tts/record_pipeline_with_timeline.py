#!/usr/bin/env python3
import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


BASE = Path("/home/linaro/Qwen/tts")
BRIDGE_DIR = BASE / "03_rk3588_qwen35_sherpa_onnx_voice_bridge_project"
RECORDER = BASE / "record_system_output.py"


def now_stamp():
    return time.strftime("%Y%m%d_%H%M%S")


def log(msg):
    print(f"[{time.strftime('%F %T')}][REC-TIMELINE] {msg}", flush=True)


def run_dir_for(stamp):
    root = BASE / "recorded_timeline_runs"
    root.mkdir(parents=True, exist_ok=True)
    d = root / f"run_{stamp}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_event(events, at_s, kind, label, detail=None):
    item = {
        "audio_time_s": round(float(at_s), 3),
        "kind": kind,
        "label": label,
    }
    if detail:
        item["detail"] = detail
    events.append(item)


def load_pipeline_metrics(pipeline_dir):
    files = sorted(pipeline_dir.glob("pipeline_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"no pipeline_*.json found in {pipeline_dir}")
    p = files[-1]
    return p, json.loads(p.read_text(encoding="utf-8"))


def write_timeline_csv(path, events):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["audio_time_s", "kind", "label", "detail"])
        writer.writeheader()
        for e in events:
            writer.writerow(
                {
                    "audio_time_s": e["audio_time_s"],
                    "kind": e["kind"],
                    "label": e["label"],
                    "detail": json.dumps(e.get("detail", ""), ensure_ascii=False),
                }
            )


def write_timeline_txt(path, events):
    lines = []
    for e in events:
        detail = e.get("detail")
        if isinstance(detail, dict):
            detail_text = " ".join(f"{k}={v}" for k, v in detail.items())
        elif detail:
            detail_text = str(detail)
        else:
            detail_text = ""
        lines.append(f"{e['audio_time_s']:8.3f}s  {e['kind']:<16} {e['label']} {detail_text}".rstrip())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Record system audio and align Qwen/sherpa events to the WAV timeline.")
    ap.add_argument("prompt")
    ap.add_argument("--source", default="", help="PulseAudio monitor source. Empty means auto-pick.")
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--channels", type=int, default=2)
    ap.add_argument("--pre-roll", type=float, default=1.0, help="Seconds to record before starting Qwen.")
    ap.add_argument("--post-roll", type=float, default=1.0, help="Seconds to keep recording after pipeline finishes.")
    ap.add_argument("--no-play", action="store_true", help="Run pipeline without playback. Useful for timing only.")
    args = ap.parse_args()

    stamp = now_stamp()
    out_dir = run_dir_for(stamp)
    wav_path = out_dir / "system_output.wav"
    run_log = out_dir / "pipeline.log"
    pipeline_out = out_dir / "pipeline_metrics"
    timeline_json = out_dir / "timeline.json"
    timeline_csv = out_dir / "timeline.csv"
    timeline_txt = out_dir / "timeline.txt"
    pipeline_out.mkdir(parents=True, exist_ok=True)

    recorder_cmd = [
        sys.executable,
        str(RECORDER),
        "-o",
        str(wav_path),
        "--rate",
        str(args.rate),
        "--channels",
        str(args.channels),
    ]
    if args.source:
        recorder_cmd += ["--source", args.source]

    log(f"start recording: {wav_path}")
    record_t0 = time.perf_counter()
    recorder = subprocess.Popen(recorder_cmd, cwd=str(BASE))

    try:
        time.sleep(max(args.pre_roll, 0.0))
        qwen_start_offset = time.perf_counter() - record_t0

        pipeline_cmd = [
            "bash",
            "scripts/09_run_pipeline_voice_chat.sh",
            "--out-dir",
            str(pipeline_out),
        ]
        if args.no_play:
            pipeline_cmd.append("--no-play")
        pipeline_cmd.append(args.prompt)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        log(f"start Qwen+sherpa pipeline at audio {qwen_start_offset:.3f}s")
        with run_log.open("w", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                pipeline_cmd,
                cwd=str(BRIDGE_DIR),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="")
                log_file.write(line)
                log_file.flush()
            rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"pipeline failed rc={rc}")

        time.sleep(max(args.post_roll, 0.0))
    finally:
        if recorder.poll() is None:
            recorder.send_signal(signal.SIGINT)
            try:
                recorder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                recorder.terminate()
                recorder.wait(timeout=3)

    pipeline_json, metrics = load_pipeline_metrics(pipeline_out)
    summary = metrics["summary"]
    sentences = metrics["sentences"]

    events = []
    add_event(events, 0.0, "record", "录音开始", {"wav": str(wav_path)})
    add_event(events, qwen_start_offset, "qwen", "Qwen 进程启动", {"prompt": args.prompt})

    first = summary.get("qwen_first_chunk_s")
    if first is not None:
        add_event(events, qwen_start_offset + first, "qwen", "Qwen 首次输出", {"relative_to_qwen_s": round(first, 3)})

    qwen_done = summary.get("qwen_done_s")
    if qwen_done is not None:
        add_event(events, qwen_start_offset + qwen_done, "qwen", "Qwen 输出结束", {"relative_to_qwen_s": round(qwen_done, 3)})

    for s in sentences:
        idx = s["index"]
        text = s.get("text", "")
        ready = s.get("qwen_sentence_ready_s")
        if ready is not None:
            add_event(
                events,
                qwen_start_offset + ready,
                "qwen_sentence",
                f"Qwen 输出第 {idx} 句",
                {"text": text, "chars": s.get("chars")},
            )

        synth_start = s.get("synth_start_s")
        if synth_start is not None:
            add_event(
                events,
                qwen_start_offset + synth_start,
                "sherpa_synth",
                f"sherpa 开始合成第 {idx} 句",
                {"text": text},
            )

        synth_done = s.get("synth_done_s")
        if synth_done is not None:
            add_event(
                events,
                qwen_start_offset + synth_done,
                "sherpa_synth",
                f"sherpa 合成完成第 {idx} 句",
                {
                    "engine_s": s.get("sherpa_engine_elapsed_s"),
                    "audio_s": s.get("audio_duration_s"),
                    "rtf": s.get("sherpa_rtf"),
                    "wav": s.get("output"),
                },
            )

        play_start = s.get("play_start_s")
        if play_start is not None:
            add_event(
                events,
                qwen_start_offset + play_start,
                "audio_play",
                f"开始播放第 {idx} 句",
                {"text": text, "wav": s.get("output")},
            )

        play_done = s.get("play_done_s")
        if play_done is not None:
            add_event(
                events,
                qwen_start_offset + play_done,
                "audio_play",
                f"播放完成第 {idx} 句",
                {"play_wall_s": s.get("play_wall_s")},
            )

    events.sort(key=lambda x: x["audio_time_s"])
    result = {
        "recording": {
            "wav": str(wav_path),
            "rate": args.rate,
            "channels": args.channels,
            "pre_roll_s": args.pre_roll,
            "post_roll_s": args.post_roll,
        },
        "pipeline_metrics": str(pipeline_json),
        "pipeline_log": str(run_log),
        "qwen_start_audio_time_s": qwen_start_offset,
        "summary": summary,
        "events": events,
    }
    timeline_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_timeline_csv(timeline_csv, events)
    write_timeline_txt(timeline_txt, events)

    log(f"saved wav: {wav_path}")
    log(f"saved timeline json: {timeline_json}")
    log(f"saved timeline csv: {timeline_csv}")
    log(f"saved timeline txt: {timeline_txt}")

    print()
    print("==== timeline ====")
    print(timeline_txt.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
