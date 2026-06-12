import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import soundfile as sf
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.audio_player import play_audio
from app.zipvoice_persistent import PersistentZipVoiceOnnx


def load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, os.path.expandvars(v))


load_env(os.environ.get("ZIPVOICE_ENV", "config/zipvoice.env"))

app = FastAPI(title="RK3588 ZipVoice ONNX TTS")
_engine = None


class Req(BaseModel):
    text: str
    output: Optional[str] = None
    play: bool = False
    speed: Optional[float] = None
    prompt_wav: Optional[str] = None
    prompt_text: Optional[str] = None


def str_bool(value):
    return str(value).lower() in ("1", "true", "yes", "on")


def get_engine():
    global _engine
    if _engine is None:
        _engine = PersistentZipVoiceOnnx()
    return _engine


def wav_duration(path):
    info = sf.info(str(path))
    return info.frames / float(info.samplerate)


def build_cmd(req, output):
    repo_dir = os.environ.get("ZIPVOICE_REPO_DIR", "/home/linaro/Qwen/tts/ZipVoice")
    prompt_wav = req.prompt_wav or os.environ.get("ZIPVOICE_PROMPT_WAV", "")
    prompt_text = req.prompt_text or os.environ.get("ZIPVOICE_PROMPT_TEXT", "")
    if not prompt_wav or not Path(prompt_wav).exists():
        raise FileNotFoundError(f"ZIPVOICE_PROMPT_WAV not found: {prompt_wav}")
    if not prompt_text or prompt_text == "这里填写参考音频对应的文字。":
        raise ValueError("ZIPVOICE_PROMPT_TEXT is not configured")

    cmd = [
        sys.executable,
        "-m",
        "zipvoice.bin.infer_zipvoice_onnx",
        "--onnx-int8",
        os.environ.get("ZIPVOICE_ONNX_INT8", "true"),
        "--model-name",
        os.environ.get("ZIPVOICE_MODEL_NAME", "zipvoice_distill"),
        "--prompt-wav",
        prompt_wav,
        "--prompt-text",
        prompt_text,
        "--text",
        req.text,
        "--res-wav-path",
        str(output),
        "--num-thread",
        os.environ.get("ZIPVOICE_NUM_THREAD", "4"),
        "--num-step",
        os.environ.get("ZIPVOICE_NUM_STEP", "4"),
        "--tokenizer",
        os.environ.get("ZIPVOICE_TOKENIZER", "emilia"),
        "--lang",
        os.environ.get("ZIPVOICE_LANG", "zh"),
        "--speed",
        str(req.speed if req.speed is not None else os.environ.get("ZIPVOICE_SPEED", "1.0")),
        "--remove-long-sil",
        os.environ.get("ZIPVOICE_REMOVE_LONG_SIL", "true"),
    ]

    model_dir = os.environ.get("ZIPVOICE_MODEL_DIR", "").strip()
    if model_dir:
        cmd += ["--model-dir", model_dir]

    return repo_dir, cmd


def synthesize_persistent(req, output):
    prompt_wav = req.prompt_wav or os.environ.get("ZIPVOICE_PROMPT_WAV", "")
    prompt_text = req.prompt_text or os.environ.get("ZIPVOICE_PROMPT_TEXT", "")
    if prompt_text == "这里填写参考音频对应的文字。":
        raise ValueError("ZIPVOICE_PROMPT_TEXT is not configured")
    return get_engine().synthesize(
        text=req.text,
        output=output,
        prompt_wav=prompt_wav,
        prompt_text=prompt_text,
        speed=req.speed,
    )


@app.get("/health")
def health():
    repo_dir = os.environ.get("ZIPVOICE_REPO_DIR", "/home/linaro/Qwen/tts/ZipVoice")
    return {
        "ok": True,
        "engine": "zipvoice_onnx",
        "backend": os.environ.get("ZIPVOICE_BACKEND", "persistent"),
        "repo_dir": repo_dir,
        "repo_exists": Path(repo_dir).exists(),
        "model_name": os.environ.get("ZIPVOICE_MODEL_NAME", "zipvoice_distill"),
        "onnx_int8": str_bool(os.environ.get("ZIPVOICE_ONNX_INT8", "true")),
        "prompt_wav": os.environ.get("ZIPVOICE_PROMPT_WAV", ""),
        "port": os.environ.get("ZIPVOICE_PORT", "8012"),
    }


@app.post("/synthesize")
def synthesize(req: Req):
    try:
        text = (req.text or "").strip()
        if not text:
            raise ValueError("empty text")

        output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        output = Path(req.output) if req.output else output_dir / f"zipvoice_{int(time.time() * 1000)}.wav"
        output.parent.mkdir(parents=True, exist_ok=True)

        if os.environ.get("ZIPVOICE_BACKEND", "persistent").lower() == "persistent":
            return synthesize_persistent(req, output)

        repo_dir, cmd = build_cmd(req, output)
        start = time.perf_counter()
        env = os.environ.copy()
        env["PYTHONPATH"] = repo_dir + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            cmd,
            cwd=repo_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=600,
        )
        elapsed = time.perf_counter() - start
        if proc.returncode != 0:
            raise RuntimeError(f"ZipVoice failed rc={proc.returncode}\n{proc.stdout}")
        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError(f"ZipVoice did not create wav: {output}")

        duration = wav_duration(output)
        return {
            "ok": True,
            "output": str(output),
            "duration_sec": duration,
            "elapsed_sec": elapsed,
            "rtf": elapsed / max(duration, 1e-6),
            "stdout_tail": proc.stdout[-2000:],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/speak")
def speak(req: Req):
    result = synthesize(req)
    if isinstance(result, dict) and req.play:
        play_audio(result["output"])
        result["played"] = True
    return result
