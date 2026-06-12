#!/usr/bin/env python3
import os
import queue
import re
import selectors
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests


DEMO_DIR = Path("/home/linaro/rkllm_qwen3vl4b/demo_Linux_aarch64")
IMAGE = "/home/linaro/test.jpg"
VISION_MODEL = "./qwen3-vl_vision_rk3588.rknn"
LLM_MODEL = "./qwen3-vl-4b-instruct_w8a8_rk3588.rkllm"
TTS_API_BASE = os.environ.get("TTS_API_BASE", "http://127.0.0.1:8011").rstrip("/")
STOP = object()


def now():
    return time.strftime("%F %T")


def log(tag, msg):
    print(f"[{now()}][{tag}] {msg}", file=sys.stderr, flush=True)


def check_tts():
    try:
        r = requests.get(TTS_API_BASE + "/health", timeout=5)
        r.raise_for_status()
        log("TTS", f"health={r.text[:500]}")
    except Exception as e:
        raise RuntimeError(
            "Piper TTS service is not ready at "
            f"{TTS_API_BASE}. 先在另一个终端运行："
            "/home/linaro/Qwen/scripts/21_start_8011_tts_foreground.sh"
        ) from e


NOISE_PATTERNS = [
    r"^\s*[IWE]\s+rkllm:",
    r"^\s*[IWE]\s+RKNN:",
    r"rkllm-runtime version",
    r"rknpu driver version",
    r"loading rkllm",
    r"rkllm-toolkit version",
    r"max_context_limit",
    r"target_platform",
    r"model_dtype",
    r"Enabled cpus",
    r"Using mrope",
    r"rkllm init success",
    r"LLM Model loaded",
    r"ImgEnc Model loaded",
    r"ImgEnc Model inference took",
    r"===the core num",
    r"model input num",
    r"input tensors",
    r"output tensors",
    r"index=\d+",
    r"name=pixel",
    r"n_dims=",
    r"dims=\[",
    r"n_elems=",
    r"fmt=",
    r"size=",
    r"main:",
    r"可输入以下问题对应序号",
    r"自定义输入",
    r"^\*{5,}",
    r"^\[0\]",
    r"^\[1\]",
    r"^user:\s*$",
]


def clean_line(line, user_prompt, send_prompt):
    s = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
    s = s.replace("\r", "").strip()
    if not s:
        return ""
    for pat in NOISE_PATTERNS:
        if re.search(pat, s, flags=re.I):
            return ""
    lower = s.lower()
    if user_prompt in s and "robot:" not in lower and "assistant:" not in lower:
        return ""
    if send_prompt in s and "robot:" not in lower and "assistant:" not in lower:
        return ""
    s = re.sub(r"^.*?\buser\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?\brobot\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?\bassistant\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?助手\s*[:：]\s*", "", s)
    s = re.sub(r"^.*?回答\s*[:：]\s*", "", s)
    s = s.replace(send_prompt, "").replace(user_prompt, "").replace("<image>", "")
    s = s.strip()
    return s


def split_sentences(text):
    out = []
    buf = ""
    max_chars = int(os.environ.get("INTERACTIVE_TTS_MAX_CHARS", "28"))
    for ch in text:
        buf += ch
        if ch in "。！？!?；;\n" or len(buf) >= max_chars:
            s = buf.strip()
            if len(s) >= 4:
                out.append(s)
            buf = ""
    return out, buf.strip()


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
    if "/" not in cmd[0] and not shutil.which(cmd[0]):
        raise FileNotFoundError(f"audio player not found: {cmd[0]}")
    subprocess.run(cmd, check=True)


def synth_worker(synth_q, play_q):
    while True:
        item = synth_q.get()
        try:
            if item is STOP:
                return
            idx, text = item
            log("SYNTH", f"start idx={idx} chars={len(text)} text={text}")
            t0 = time.perf_counter()
            output = f"/tmp/piper_interactive_{int(time.time() * 1000)}_{idx}.wav"
            r = requests.post(
                TTS_API_BASE + "/synthesize",
                json={"text": text, "play": False, "output": output},
                timeout=600,
            )
            synth_dt = time.perf_counter() - t0
            log("SYNTH", f"done idx={idx} status={r.status_code} elapsed={synth_dt:.3f}s wav={output}")
            r.raise_for_status()
            play_q.put((idx, output))
        except Exception as e:
            log("SYNTH-ERROR", repr(e))
        finally:
            synth_q.task_done()


def play_worker(play_q):
    while True:
        item = play_q.get()
        try:
            if item is STOP:
                return
            idx, output = item
            log("PLAY", f"start idx={idx} wav={output}")
            t1 = time.perf_counter()
            play_wav(output)
            play_dt = time.perf_counter() - t1
            log("PLAY", f"done idx={idx} elapsed={play_dt:.3f}s")
        except Exception as e:
            log("PLAY-ERROR", repr(e))
        finally:
            play_q.task_done()


class PersistentQwen:
    def __init__(self):
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = str(DEMO_DIR / "lib") + ":" + env.get("LD_LIBRARY_PATH", "")
        env.setdefault("RKLLM_LOG_LEVEL", "1")
        cmd = [
            "./demo",
            IMAGE,
            VISION_MODEL,
            LLM_MODEL,
            "256",
            "4096",
            "3",
            "<|vision_start|>",
            "<|vision_end|>",
            "<|image_pad|>",
        ]
        log("QWEN", "starting persistent demo")
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(DEMO_DIR),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        os.set_blocking(self.proc.stdout.fileno(), False)
        self.read_buffer = ""
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.proc.stdout, selectors.EVENT_READ)
        self._wait_ready()

    def _read_available(self, timeout=0.1, flush_partial=False):
        lines = []
        for key, _ in self.sel.select(timeout):
            try:
                data = os.read(key.fileobj.fileno(), 8192)
            except BlockingIOError:
                data = b""
            if not data:
                continue

            self.read_buffer += data.decode("utf-8", errors="ignore")

            while "\n" in self.read_buffer:
                line, self.read_buffer = self.read_buffer.split("\n", 1)
                lines.append(line + "\n")

        if flush_partial and self.read_buffer.strip():
            lines.append(self.read_buffer)
            self.read_buffer = ""

        return lines

    def _wait_ready(self):
        start = time.time()
        last_log = 0
        while time.time() - start < 180:
            for line in self._read_available(timeout=0.5, flush_partial=True):
                s = line.strip()
                if s:
                    print(f"[{now()}][QWEN-BOOT] {s}", file=sys.stderr, flush=True)
                if "可输入以下问题" in s or s == "user:":
                    log("QWEN", "ready")
                    return
            elapsed = int(time.time() - start)
            if elapsed >= last_log + 10:
                last_log = elapsed
                log("QWEN", f"waiting ready... elapsed={elapsed}s")
        log("QWEN", "ready wait timeout, continue anyway")

    def ask(self, prompt):
        use_image = os.environ.get("INTERACTIVE_USE_IMAGE", "0").lower() in {"1", "true", "yes", "on"}
        if use_image and "<image>" not in prompt:
            send_prompt = "<image>" + prompt
        else:
            send_prompt = prompt
        if os.environ.get("INTERACTIVE_SHORT_REPLY", "1").lower() in {"1", "true", "yes", "on"}:
            send_prompt += " 请简短回答，最多三句话，每句话不超过二十个字。"

        self.proc.stdin.write(send_prompt + "\n")
        self.proc.stdin.flush()

        started = False
        last_output = time.time()
        start = time.time()
        buffer = ""

        while time.time() - start < 420:
            lines = self._read_available(timeout=0.5, flush_partial=True)
            if not lines:
                if started and time.time() - last_output > 8:
                    break
                continue

            for raw in lines:
                s0 = raw.strip()
                if s0:
                    print(f"[{now()}][QWEN-OUT] {s0}", file=sys.stderr, flush=True)

                if started and s0 == "user:":
                    return

                lower = s0.lower()
                if not started:
                    if "robot:" in lower or "assistant:" in lower or "助手" in s0 or "回答" in s0:
                        started = True
                    else:
                        continue

                text = clean_line(s0, prompt, send_prompt)
                if text:
                    last_output = time.time()
                    print(text, flush=True)
                    yield text

        log("QWEN", "answer read finished by timeout/idle")

    def close(self):
        try:
            self.proc.stdin.write("exit\n")
            self.proc.stdin.flush()
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass


def main():
    check_tts()

    synth_q = queue.Queue()
    play_q = queue.Queue()
    synth_th = threading.Thread(target=synth_worker, args=(synth_q, play_q), daemon=True)
    play_th = threading.Thread(target=play_worker, args=(play_q,), daemon=True)
    synth_th.start()
    play_th.start()
    qwen = PersistentQwen()

    print("交互式常驻 Qwen3-VL + Piper 已启动。输入 exit / quit / q / 退出 结束。")
    print("流水线模式：Qwen 输出句子后立即合成，上一句播放时下一句继续合成。")
    print("默认不会自动加 <image>；需要看图时，用 INTERACTIVE_USE_IMAGE=1 启动，或直接在问题里写 <image>。")
    try:
        while True:
            prompt = input("你：").strip()
            if not prompt:
                continue
            if prompt in {"exit", "quit", "q", "退出"}:
                break

            print("助手：", end="", flush=True)
            pending = ""
            idx = 0
            for part in qwen.ask(prompt):
                pending += part
                ready, pending = split_sentences(pending)
                for s in ready:
                    idx += 1
                    synth_q.put((idx, s))
            if pending.strip():
                idx += 1
                synth_q.put((idx, pending.strip()))
            print()
            synth_q.join()
            play_q.join()
    finally:
        qwen.close()
        synth_q.put(STOP)
        synth_q.join()
        play_q.put(STOP)
        play_q.join()


if __name__ == "__main__":
    main()
