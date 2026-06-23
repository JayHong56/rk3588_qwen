#!/usr/bin/env python3
import base64
import io
import os
import queue
import re
import selectors
import shutil
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading
import time
import wave
from pathlib import Path

import numpy as np
import requests
import sherpa_onnx

# ── backend selection ────────────────────────────────────────────────────
# QWEN_MODEL_BACKEND=vl   → Qwen3-VL 4B  (vision-language, ./demo)
# QWEN_MODEL_BACKEND=text → Qwen3 8B      (text-only,     ./llm_demo)
QWEN_BACKEND = os.environ.get("QWEN_MODEL_BACKEND", "text").strip().lower()
assert QWEN_BACKEND in {"vl", "text"}, f"unsupported QWEN_MODEL_BACKEND={QWEN_BACKEND}"

if QWEN_BACKEND == "text":
    DEMO_DIR   = Path("/home/linaro/Qwen/rkllm_qwen3_4b")
    DEMO_BIN   = "./llm_demo"
    LLM_MODEL  = "./Qwen3-4B_W8A8_RK3588.rkllm"
else:
    DEMO_DIR   = Path("/home/linaro/rkllm_qwen3vl4b/demo_Linux_aarch64")
    DEMO_BIN   = "./demo"
    IMAGE      = "/home/linaro/test.jpg"
    VISION_MODEL = "./qwen3-vl_vision_rk3588.rknn"
    LLM_MODEL  = "./qwen3-vl-4b-instruct_w8a8_rk3588.rkllm"

TTS_API_BASE = os.environ.get("TTS_API_BASE", "http://127.0.0.1:8011").rstrip("/")
TTS_VOLUME = float(os.environ.get("SHERPA_VOLUME", "1.5"))
TTS_SPEED = float(os.environ.get("TTS_SPEED", "0.75"))
TTS_RECORD_DIR = os.environ.get("TTS_RECORD_DIR", "").strip()
# ── inter-sentence pause ──────────────────────────────────────────────────
# Per-punctuation pauses (seconds); can override base values via env.
_HARD_PAUSE = float(os.environ.get("TTS_PAUSE_HARD", "0.30"))   # 。！？
_SOFT_PAUSE = float(os.environ.get("TTS_PAUSE_SOFT", "0.10"))   # ，；：、
# ── F1 interrupt ────────────────────────────────────────────────────────────
_F1_SEQUENCES = {b'\x1bOP', b'\x1b[11~', b'\x1b[[A'}   # xterm / VT220 / Linux console

def _enter_raw_stdin():
    """Put stdin in raw mode (no line buffering, no echo). Returns saved settings."""
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    # lflags: disable canonical (line buffering) and echo; keep signal handling
    new[3] = (new[3] & ~(termios.ICANON | termios.ECHO)) | termios.ISIG
    # cc: VMIN=1, VTIME=0 → read blocks until ≥1 byte available
    new[6][termios.VMIN] = 1
    new[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, new)
    return saved

def _restore_terminal(saved):
    """Restore terminal to saved settings."""
    try:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, saved)
    except Exception:
        pass

def _read_keypress(fd):
    """Try to read one complete key sequence from a raw fd. Returns bytes or None."""
    import select
    try:
        ch = os.read(fd, 1)
    except (BlockingIOError, OSError):
        return None
    if not ch:
        return None
    if ch != b'\x1b':
        return ch  # regular key
    # Escape sequence — read remaining bytes with short select timeout
    seq = b'\x1b'
    for _ in range(6):  # max 6 more bytes
        r, _, _ = select.select([sys.stdin], [], [], 0.02)  # 20ms timeout
        if not r:
            break
        try:
            ch = os.read(fd, 1)
        except (BlockingIOError, OSError):
            break
        if not ch:
            break
        seq += ch
        if seq in _F1_SEQUENCES:
            return seq
        # A complete escape sequence ends with a letter or tilde
        if ch.isalpha() or ch == b'~':
            return seq
    return seq

STOP = object()
# Audio forwarding over TCP (for SSH sessions)
_AUDIO_FWD_DISABLE = os.environ.get("AUDIO_FORWARD", "").strip().lower() in {"0", "false", "no", "off"}
_AUDIO_FWD_HOST = os.environ.get("AUDIO_FORWARD_HOST", "").strip()
if not _AUDIO_FWD_DISABLE and not _AUDIO_FWD_HOST:
    ssh_client = os.environ.get("SSH_CLIENT", "")
    if ssh_client:
        _AUDIO_FWD_HOST = ssh_client.split()[0]
AUDIO_FORWARD_HOST = _AUDIO_FWD_HOST if not _AUDIO_FWD_DISABLE else ""
AUDIO_FORWARD_PORT = int(os.environ.get("AUDIO_FORWARD_PORT", "9876"))
VOICE_INPUT = os.environ.get("VOICE_INPUT", "0").strip().lower() in {"1", "true", "yes", "on"}
MIC_DEVICE = os.environ.get("MIC_DEVICE", "default")
ASR_MODEL_DIR = os.environ.get(
    "ASR_MODEL_DIR",
    "/home/linaro/Qwen/asr/models/sherpa-onnx-paraformer-zh-2024-03-09",
)
ASR_NUM_THREADS = int(os.environ.get("ASR_NUM_THREADS", "4"))

_asr_recognizer = None
_vad_detector = None


def init_asr():
    """Load the ASR model once (persistent)."""
    global _asr_recognizer
    if _asr_recognizer is not None:
        return _asr_recognizer
    t0 = time.time()
    _asr_recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        tokens=f"{ASR_MODEL_DIR}/tokens.txt",
        paraformer=f"{ASR_MODEL_DIR}/model.int8.onnx",
        num_threads=ASR_NUM_THREADS,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        debug=False,
    )
    log("ASR", f"model loaded in {time.time()-t0:.1f}s")
    return _asr_recognizer


def init_vad():
    """Load the Silero VAD model once (persistent)."""
    global _vad_detector
    if _vad_detector is not None:
        return _vad_detector
    t0 = time.time()
    silero_vad = sherpa_onnx.SileroVadModelConfig()
    silero_vad.model = os.path.join(ASR_MODEL_DIR, "silero_vad.onnx")
    silero_vad.threshold = float(os.environ.get("VAD_THRESHOLD", "0.5"))
    silero_vad.min_silence_duration = float(os.environ.get("VAD_MIN_SILENCE_DUR", "0.5"))
    silero_vad.min_speech_duration = float(os.environ.get("VAD_MIN_SPEECH_DUR", "0.25"))
    silero_vad.max_speech_duration = float(os.environ.get("VAD_MAX_SPEECH_DUR", "20.0"))
    silero_vad.window_size = int(os.environ.get("VAD_WINDOW_SIZE", "512"))
    vad_config = sherpa_onnx.VadModelConfig()
    vad_config.silero_vad = silero_vad
    _vad_detector = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=60)
    log("VAD", f"model loaded in {time.time()-t0:.1f}s")
    return _vad_detector


def voice_input(recognizer, vad):
    """Record from mic with VAD, run ASR, return text."""
    log("VOICE", "listening (VAD) ...")
    vad_pre_gain = float(os.environ.get("VAD_PRE_GAIN", "100.0"))
    proc = subprocess.Popen(
        ["arecord", "-D", MIC_DEVICE, "-f", "S16_LE", "-r", "16000", "-c", "1", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    vad.reset()
    speech_segment = None
    raw_buf = []
    t_start = time.time()
    max_wait = float(os.environ.get("VAD_MAX_WAIT", "60"))
    try:
        while True:
            raw = proc.stdout.read(3200)
            if not raw:
                break
            raw_buf.append(raw)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            samples_amp = np.clip(samples * vad_pre_gain, -1.0, 1.0)
            vad.accept_waveform(samples_amp)
            if not vad.empty():
                speech_segment = vad.front.samples
                vad.pop()
                break
            if time.time() - t_start > max_wait:
                log("VOICE", "timeout — no speech detected")
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
    if speech_segment is None or len(speech_segment) < 16000 * 0.2:
        log("VOICE", "no speech segment found")
        return ""
    duration = len(speech_segment) / 16000
    log("VOICE", f"speech {duration:.1f}s, recognizing ...")
    # Use original (unamplified) raw bytes for ASR
    raw_all = b"".join(raw_buf)
    orig_samples = np.frombuffer(raw_all, dtype=np.int16).astype(np.float32) / 32768.0
    t0 = time.time()
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, orig_samples)
    recognizer.decode_stream(stream)
    text = stream.result.text.strip()
    log("VOICE", f"recognized in {time.time()-t0:.2f}s: {text}")
    return text


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
    """Remove ANSI codes, system noise, and prompt prefixes from a single output line."""
    s = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
    s = s.replace("\r", "").strip()
    if not s:
        return ""
    for pat in NOISE_PATTERNS:
        if re.search(pat, s, flags=re.I):
            return ""
    lower = s.lower()
    # Strip prompt prefixes BEFORE echo filtering
    s = re.sub(r"^.*?\buser\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?\brobot\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?\bassistant\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?助手\s*[:：]\s*", "", s)
    s = re.sub(r"^.*?回答\s*[:：]\s*", "", s)
    s = s.replace("<image>", "").strip()
    return s


def is_speakable(text):
    """Return True if text contains at least one CJK or alphanumeric character."""
    return bool(re.search(r"[一-鿿㐀-䶿a-zA-Z0-9]", text))


def split_sentences(text):
    # Strip ALL markdown formatting
    text = re.sub(r'\*{1,2}', '', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'`{1,3}', '', text)
    text = re.sub(r'^[-*_]{3,}\s*', '', text)  # --- or *** at line starts
    text = text.replace('：', '，').replace(':', '，')  # colons → commas
    # Strip Chinese/English quotes and brackets (keep ，。！？ for TTS prosody)
    _strip_syms = "\"'\"'「」『』【】《》…—*-<>()[]{}"
    out = []
    buf = ""
    max_chars = int(os.environ.get("INTERACTIVE_TTS_MAX_CHARS", "25"))
    for ch in text:
        buf += ch
        soft = ch in "，；、"
        hard = ch in "。！？!?\n"
        if hard or soft or len(buf) >= max_chars:
            s = buf.strip()
            if hard:
                s = s.strip(_strip_syms + "，；、：")  # strip wrap symbols but keep 。！？
                s = s.strip(_strip_syms)
            elif len(buf) >= max_chars:
                s = s.strip(_strip_syms + "，；、。！？!?，：")  # forced break – strip all
            else:
                s = s.strip(_strip_syms + "。！？!?")  # soft break – keep ，；、
                s = s.strip(_strip_syms)
            # Validate: must have CJK, and CJK >= ASCII letters (no pure pinyin)
            cjk = len(re.findall(r'[一-鿿㐀-䶿]', s))
            asc = len(re.findall(r'[a-zà-ǖ]', s))
            valid = cjk > 0 and cjk >= asc
            if not valid:
                buf = ""
                continue
            # Hard break or max_chars → always emit. Soft break → emit only if 6+ chars.
            if hard or len(buf) >= max_chars or len(s) >= 4:
                out.append(s)
                buf = ""
            # else: soft break on short fragment → keep accumulating
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
            r = requests.post(
                TTS_API_BASE + "/synthesize",
                json={"text": text, "output": "__memory__", "volume": TTS_VOLUME, "speed": TTS_SPEED},
                timeout=600,
            )
            synth_dt = time.perf_counter() - t0
            r.raise_for_status()
            data = r.json()
            pcm = base64.b64decode(data["pcm_base64"])
            log("SYNTH", f"done idx={idx} elapsed={synth_dt:.3f}s dur={data['duration_sec']:.2f}s rtf={data.get('rtf',0):.2f}")
            play_q.put((idx, pcm, data["sample_rate"], data.get("pcm_is_wav", False), text))
        except Exception as e:
            log("SYNTH-ERROR", repr(e))
        finally:
            synth_q.task_done()


def _raw_to_wav(pcm, sample_rate):
    """Wrap raw S16_LE PCM in a WAV header so aplay can auto-detect format."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


# ── Continuous audio streaming ring buffer ────────────────────────────────
CHUNK_SIZE = 4096  # bytes per streaming chunk (~46ms @ 44100 Hz)
RING_BUFFER_CAPACITY = 1 * 1024 * 1024  # 1 MiB (~12s @ 44100 Hz)


class RingBuffer:
    """Thread-safe ring buffer for continuous PCM streaming.

    One writer (play_worker), one reader (forward_worker).
    read() always returns exactly n bytes — fills with silence when empty.
    """

    def __init__(self, capacity=RING_BUFFER_CAPACITY):
        self._buf = bytearray(capacity)
        self._cap = capacity
        self._wp = 0  # write position
        self._rp = 0  # read position
        self._avail = 0  # readable bytes
        self._lock = threading.Lock()
        self.sample_rate = None

    def write(self, data: bytes):
        """Append PCM data. Overwrites oldest data if full (non-blocking)."""
        with self._lock:
            n = len(data)
            if n > self._cap:
                data = data[-self._cap:]
                n = self._cap
            # Advance read pointer if overwriting
            if self._avail + n > self._cap:
                drop = self._avail + n - self._cap
                self._rp = (self._rp + drop) % self._cap
                self._avail -= drop
            # Copy in (may wrap)
            end = self._wp + n
            if end <= self._cap:
                self._buf[self._wp:end] = data
            else:
                first = self._cap - self._wp
                self._buf[self._wp:] = data[:first]
                self._buf[:end - self._cap] = data[first:]
            self._wp = end % self._cap
            self._avail += n

    def read(self, n: int) -> bytes:
        """Read exactly n bytes. Returns silence (zeros) for missing data."""
        with self._lock:
            if self._avail <= 0:
                return b'\x00' * n
            take = min(n, self._avail)
            result = bytearray(n)
            end = self._rp + take
            if end <= self._cap:
                result[:take] = self._buf[self._rp:end]
            else:
                first = self._cap - self._rp
                result[:first] = self._buf[self._rp:]
                result[first:take] = self._buf[:end - self._cap]
            self._rp = end % self._cap
            self._avail -= take
            return bytes(result)


def forward_worker(host, port, ring_buf, stop_ev):
    """Continuous audio streaming sender.

    Connects to PC, sends 4B sample_rate header, then continuously reads
    fixed-size chunks from the ring buffer and sends them at real-time rate.
    When the ring buffer is empty, silence (zeros) is sent — the stream
    never pauses, eliminating underruns on the PC side.
    """
    if not host:
        return
    CHUNK = CHUNK_SIZE
    while not stop_ev.is_set():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.settimeout(None)
            log("FWD", f"connected to {host}:{port}")

            # Wait for sample_rate from first TTS response
            while ring_buf.sample_rate is None and not stop_ev.is_set():
                time.sleep(0.05)
            if stop_ev.is_set():
                sock.close()
                return
            sr = ring_buf.sample_rate
            interval = CHUNK / (sr * 2)  # seconds per chunk

            # Send sample_rate header (4 bytes)
            sock.sendall(struct.pack(">I", sr))
            log("FWD", f"streaming started sr={sr} chunk={CHUNK}B interval={interval*1000:.1f}ms")

            # Continuous send loop
            while not stop_ev.is_set():
                t0 = time.perf_counter()
                data = ring_buf.read(CHUNK)
                sock.sendall(data)
                elapsed = time.perf_counter() - t0
                sleep_time = interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except Exception as e:
            if not stop_ev.is_set():
                log("FWD", f"error: {e}, reconnecting in 2s ...")
                time.sleep(2)
        finally:
            try:
                sock.close()
            except Exception:
                pass


def _pause_duration(text):
    """Return inter-sentence pause in seconds based on final punctuation."""
    last = text.strip()[-1] if text.strip() else ""
    if last in "。！？!?":
        return _HARD_PAUSE
    if last in "，；：、":
        return _SOFT_PAUSE
    return 0.0


def play_worker(play_q, ring_buf, interrupt_event=None):
    fwd_host = AUDIO_FORWARD_HOST
    ie = interrupt_event or threading.Event()
    while True:
        item = play_q.get()
        try:
            if item is STOP:
                return
            # Skip remaining items if interrupted
            if ie.is_set():
                play_q.task_done()
                continue

            idx, pcm, sample_rate, is_wav, *rest = item
            text = rest[0] if rest else ""
            pause_s = _pause_duration(text)

            if fwd_host:
                if ie.is_set():
                    play_q.task_done()
                    continue
                if is_wav:
                    pcm = pcm[44:]  # strip WAV header, send raw PCM
                if ring_buf.sample_rate is None:
                    ring_buf.sample_rate = sample_rate
                ring_buf.write(pcm)
                if pause_s > 0 and not ie.is_set():
                    silence = b'\x00' * int(pause_s * sample_rate * 2)
                    ring_buf.write(silence)
                log("PLAY", f"wrote idx={idx} sr={sample_rate} len={len(pcm)} pause={pause_s:.2f}s")
            elif is_wav:
                proc = subprocess.Popen(["aplay", "-q", "-"], stdin=subprocess.PIPE)
                try:
                    proc.stdin.write(pcm)
                    proc.stdin.close()
                    while proc.poll() is None:
                        if ie.is_set():
                            proc.kill()
                            proc.wait()
                            log("PLAY", f"interrupted idx={idx}")
                            break
                        time.sleep(0.05)
                    else:
                        if pause_s > 0 and not ie.is_set():
                            time.sleep(pause_s)
                        log("PLAY", f"done idx={idx} pause={pause_s:.2f}s")
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    raise
            else:
                proc = subprocess.Popen(
                    ["aplay", "-q", "-r", str(sample_rate), "-f", "S16_LE", "-c", "1", "-"],
                    stdin=subprocess.PIPE,
                )
                try:
                    proc.stdin.write(pcm)
                    proc.stdin.close()
                    while proc.poll() is None:
                        if ie.is_set():
                            proc.kill()
                            proc.wait()
                            log("PLAY", f"interrupted idx={idx}")
                            break
                        time.sleep(0.05)
                    else:
                        if TTS_RECORD_DIR and not ie.is_set():
                            rec_dir = Path(TTS_RECORD_DIR)
                            rec_dir.mkdir(parents=True, exist_ok=True)
                            ts = int(time.time() * 1000)
                            rec_path = rec_dir / f"tts_{ts}_{idx:03d}.wav"
                            rec_path.write_bytes(_raw_to_wav(pcm, sample_rate))
                        if pause_s > 0 and not ie.is_set():
                            time.sleep(pause_s)
                        log("PLAY", f"done idx={idx} pause={pause_s:.2f}s")
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    raise
        except Exception as e:
            log("PLAY-ERROR", repr(e))
        finally:
            play_q.task_done()


class PersistentQwen:
    def __init__(self, interrupt_event=None):
        self.interrupt_event = interrupt_event or threading.Event()
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = str(DEMO_DIR / "lib") + ":" + env.get("LD_LIBRARY_PATH", "")
        env.setdefault("RKLLM_LOG_LEVEL", "1")

        if QWEN_BACKEND == "text":
            cmd = [
                DEMO_BIN,
                LLM_MODEL,
                "512",   # max_new_tokens
                "2048",   # max_context_len
            ]
        else:
            cmd = [
                DEMO_BIN,
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

        log("QWEN", f"starting persistent demo (backend={QWEN_BACKEND})")
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(DEMO_DIR),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,  # isolate from Ctrl+C
        )
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        os.set_blocking(self.proc.stdout.fileno(), False)
        self.read_buffer = ""
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.proc.stdout, selectors.EVENT_READ)
        self._stdin_registered = False
        self._wait_ready()

    def _register_stdin(self):
        """Register stdin on the selector for F1 interrupt detection."""
        if not self._stdin_registered:
            try:
                self.sel.register(sys.stdin, selectors.EVENT_READ)
                self._stdin_registered = True
            except Exception:
                pass

    def _unregister_stdin(self):
        """Remove stdin from the selector."""
        if self._stdin_registered:
            try:
                self.sel.unregister(sys.stdin)
            except Exception:
                pass
            self._stdin_registered = False

    def _read_available(self, timeout=0.1, flush_partial=False):
        lines = []
        for key, _ in self.sel.select(timeout):
            fd = key.fileobj.fileno()

            # ── stdin → check for F1 interrupt ────────────────────────
            if key.fileobj is sys.stdin:
                seq = _read_keypress(fd)
                if seq and seq in _F1_SEQUENCES:
                    log("QWEN", "F1 interrupt detected")
                    self.interrupt_event.set()
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
                continue

            # ── Qwen stdout ───────────────────────────────────────────
            try:
                data = os.read(fd, 8192)
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
            send_prompt += " 请简短回答，最多三句话。不要使用任何markdown格式标记，不要输出拼音。"

        # ── enable raw stdin for F1 detection ───────────────────────────
        saved_term = _enter_raw_stdin()
        self._register_stdin()
        try:
            self.proc.stdin.write(send_prompt + "\n")
            self.proc.stdin.flush()

            started = False
            last_output = time.time()
            start = time.time()

            while time.time() - start < 420:
                # Check interrupt before reading
                if self.interrupt_event.is_set():
                    log("QWEN", "interrupted by F1")
                    return

                lines = self._read_available(timeout=0.5, flush_partial=True)

                # Check interrupt after reading (F1 may have fired)
                if self.interrupt_event.is_set():
                    log("QWEN", "interrupted by F1")
                    return

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
        finally:
            self._unregister_stdin()
            _restore_terminal(saved_term)

    def restart(self):
        """Kill old process and spawn a new one. Resets interrupt flag."""
        log("QWEN", "restarting subprocess ...")
        self.interrupt_event.clear()
        self._unregister_stdin()
        self.close()
        time.sleep(1)
        self.__init__(self.interrupt_event)
        log("QWEN", "restart complete")

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


def _stdin_has_data():
    """Non-blocking check for pending keyboard input."""
    import select
    try:
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except Exception:
        return False


def _drain_queues(synth_q, play_q):
    """Discard all pending items from both queues."""
    for q in (synth_q, play_q):
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except queue.Empty:
                break

def _process_prompt(qwen, prompt, synth_q, play_q, interrupt_event):
    """Feed prompt to Qwen, queue sentences for TTS, wait for playback.
    On BrokenPipeError, raise it so caller can restart Qwen.
    Returns True if interrupted, False otherwise."""
    print("助手：", end="", flush=True)
    pending = ""
    idx = 0
    interrupted = False
    try:
        for part in qwen.ask(prompt):
            if interrupt_event.is_set():
                interrupted = True
                break
            pending += part
            ready, pending = split_sentences(pending)
            for s in ready:
                if is_speakable(s):
                    idx += 1
                    synth_q.put((idx, s))
    except (BrokenPipeError, OSError) as e:
        log("QWEN", f"pipe broken: {e}")
        raise

    if interrupted or interrupt_event.is_set():
        interrupted = True
        log("QWEN", "interrupted — flushing text generation")
    elif pending.strip():
        if is_speakable(pending):
            idx += 1
            synth_q.put((idx, pending.strip()))

    print()
    if interrupted:
        return True
    synth_q.join()
    play_q.join()
    return False

def _safe_ask(qwen, prompt, synth_q, play_q, interrupt_event):
    """Call _process_prompt, restarting Qwen automatically if it died."""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            interrupted = _process_prompt(qwen, prompt, synth_q, play_q, interrupt_event)
            if interrupted:
                log("QWEN", "interrupted — draining queues and restarting")
                _drain_queues(synth_q, play_q)
                qwen.restart()
                print("\n⏹ 已打断", flush=True)
            return
        except (BrokenPipeError, OSError) as e:
            if attempt < max_retries - 1:
                log("QWEN", f"attempt {attempt+1} failed: {e}, restarting ...")
                try:
                    qwen.restart()
                except Exception as re:
                    log("QWEN", f"restart also failed: {re}")
                    raise
            else:
                log("QWEN", f"all {max_retries} attempts failed")
                raise


def main():
    check_tts()

    # Always init ASR/VAD so runtime switching works
    recog = None
    vad = None
    try:
        recog = init_asr()
        vad = init_vad()
    except Exception as e:
        log("INIT", f"ASR/VAD init failed: {e}")

    have_voice = recog is not None and vad is not None
    mode = "voice" if (VOICE_INPUT and have_voice) else "keyboard"

    interrupt_event = threading.Event()
    synth_q = queue.Queue()
    play_q = queue.Queue()
    ring_buf = RingBuffer()
    _fwd_stop_ev = threading.Event()
    synth_th = threading.Thread(target=synth_worker, args=(synth_q, play_q), daemon=True)
    play_th = threading.Thread(target=play_worker, args=(play_q, ring_buf, interrupt_event), daemon=True)
    fwd_th = threading.Thread(
        target=forward_worker,
        args=(AUDIO_FORWARD_HOST, AUDIO_FORWARD_PORT, ring_buf, _fwd_stop_ev),
        daemon=True,
    )
    synth_th.start()
    play_th.start()
    if AUDIO_FORWARD_HOST:
        fwd_th.start()
    qwen = PersistentQwen(interrupt_event)

    if QWEN_BACKEND == "text":
        print("交互式常驻 Qwen3-4B (text-only) + TTS 已启动。")
    else:
        print("交互式常驻 Qwen3-VL 4B + TTS 已启动。")
    print("流水线模式：Qwen 输出句子后立即合成，上一句播放时下一句继续合成。")
    if QWEN_BACKEND == "vl":
        print("默认不会自动加 <image>；需要看图时，用 INTERACTIVE_USE_IMAGE=1 启动，或直接在问题里写 <image>。")
    print("切换模式：键盘输入 /v 或 /voice → 语音 | /k 或 /keyboard → 键盘")
    print("按 F1 打断当前输出，回到输入界面")
    if AUDIO_FORWARD_HOST:
        print(f"音频转发（连续流）：→ {AUDIO_FORWARD_HOST}:{AUDIO_FORWARD_PORT}（PC 端: python pc_audio_receiver.py {AUDIO_FORWARD_PORT}）")
    if have_voice:
        print(f"当前模式：{'语音(VAD)' if mode == 'voice' else '键盘'}，设备={MIC_DEVICE}")
    else:
        print("当前模式：键盘（语音不可用）")
    print("输入 exit / quit / q / 退出 结束。")

    def switch_mode(new_mode):
        nonlocal mode
        if new_mode == "voice" and not have_voice:
            print("[切换失败] 语音模式不可用（ASR/VAD 未初始化）")
            return
        mode = new_mode
        print(f"[已切换] {'语音模式(VAD) — 自动聆听' if mode == 'voice' else '键盘输入模式'}")

    try:
        while True:
            if mode == "keyboard":
                # Check if user typed something before we prompt (e.g. from voice mode)
                if _stdin_has_data():
                    raw_kb = sys.stdin.readline().strip()
                else:
                    raw_kb = input("你：").strip()

                if not raw_kb:
                    continue
                if raw_kb in {"exit", "quit", "q", "退出"}:
                    break
                if raw_kb in {"/voice", "/v"}:
                    switch_mode("voice")
                    continue
                if raw_kb in {"/keyboard", "/k"}:
                    continue  # already keyboard
                _safe_ask(qwen, raw_kb, synth_q, play_q, interrupt_event)

            else:  # voice mode
                # Check for pending keyboard input before listening
                if _stdin_has_data():
                    raw_kb = sys.stdin.readline().strip()
                    if raw_kb in {"/keyboard", "/k"}:
                        switch_mode("keyboard")
                        continue
                    if raw_kb in {"/voice", "/v"}:
                        continue
                    if raw_kb in {"exit", "quit", "q", "退出"}:
                        break
                    # Treat other typed text as keyboard input — switch + process
                    switch_mode("keyboard")
                    _safe_ask(qwen, raw_kb, synth_q, play_q, interrupt_event)
                    continue

                print("[语音模式] 正在听...", end=" ", flush=True)
                try:
                    text = voice_input(recog, vad)
                except KeyboardInterrupt:
                    print("\n[Ctrl+C] 已切换回键盘模式")
                    switch_mode("keyboard")
                    continue
                except Exception:
                    log("VOICE", "录音或识别失败")
                    continue

                if not text:
                    continue
                print(f"识别: {text}")
                if text in {"exit", "quit", "退出"}:
                    break
                if text in {"/keyboard", "/k"} or text.endswith("键盘输入") or text.endswith("键盘模式"):
                    switch_mode("keyboard")
                    continue
                if text in {"/voice", "/v"}:
                    continue
                _safe_ask(qwen, text, synth_q, play_q, interrupt_event)
    finally:
        qwen.close()
        synth_q.put(STOP)
        synth_q.join()
        play_q.put(STOP)
        play_q.join()
        _fwd_stop_ev.set()
        if fwd_th.is_alive():
            fwd_th.join(timeout=2)


if __name__ == "__main__":
    main()
