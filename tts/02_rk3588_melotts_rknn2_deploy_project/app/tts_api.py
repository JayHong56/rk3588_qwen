
#!/usr/bin/env python3
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.audio_player import play_wav
from app.melotts_persistent import PersistentMeloTTS, PersistentMeloTTSConfig
from app.melotts_subprocess import MeloTTSConfig, MeloTTSSubprocess
from app.sentence_splitter import split_sentences
from app.text_normalizer import normalize_for_tts


app = FastAPI(title="MeloTTS-RKNN2 RK3588 Service")

_lock = threading.Lock()
_tts = None


def log(msg: str):
    print(msg, flush=True)


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1)
    play: bool = False
    split: bool = True
    speed: Optional[float] = None
    out_wav: Optional[str] = None


def get_tts():
    global _tts

    if _tts is None:
        backend = os.getenv("MELOTTS_BACKEND", "persistent").lower()
        log(f"[TTS-API] backend={backend}")
        log(f"[TTS-API] MELOTTS_DIR={os.getenv('MELOTTS_DIR', '/home/rock/MeloTTS-RKNN2')}")
        log(f"[TTS-API] PYTHON_BIN={os.getenv('PYTHON_BIN', 'python')}")
        log(f"[TTS-API] AUDIO_PLAYER={os.getenv('AUDIO_PLAYER', 'aplay')}")

        if backend == "subprocess":
            _tts = MeloTTSSubprocess(
                MeloTTSConfig(
                    root=Path(os.getenv("MELOTTS_DIR", "/home/rock/MeloTTS-RKNN2")),
                    python_bin=os.getenv("PYTHON_BIN", "python"),
                    sample_rate=int(os.getenv("MELOTTS_SAMPLE_RATE", "44100")),
                    speed=float(os.getenv("MELOTTS_SPEED", "0.8")),
                    output_dir=Path(os.getenv("VOICE_OUTPUT_DIR", "output")),
                )
            )
        else:
            _tts = PersistentMeloTTS(
                PersistentMeloTTSConfig(
                    root=Path(os.getenv("MELOTTS_DIR", "/home/rock/MeloTTS-RKNN2")),
                    sample_rate=int(os.getenv("MELOTTS_SAMPLE_RATE", "44100")),
                    speed=float(os.getenv("MELOTTS_SPEED", "0.8")),
                    output_dir=Path(os.getenv("VOICE_OUTPUT_DIR", "output")),
                )
            )

    return _tts


@app.get("/health")
def health():
    root = Path(os.getenv("MELOTTS_DIR", "/home/rock/MeloTTS-RKNN2"))

    required = [
        "melotts_rknn.py",
        "encoder.onnx",
        "decoder.rknn",
        "g.bin",
        "lexicon.txt",
        "tokens.txt",
    ]

    missing = [name for name in required if not (root / name).exists()]

    return {
        "ok": len(missing) == 0,
        "melotts_dir": str(root),
        "exists": root.exists(),
        "missing": missing,
        "backend": os.getenv("MELOTTS_BACKEND", "persistent"),
        "audio_player": os.getenv("AUDIO_PLAYER", "aplay"),
        "play_wait": os.getenv("TTS_PLAY_WAIT", "0"),
    }


@app.post("/synthesize")
def synthesize(req: TTSRequest):
    try:
        log("[TTS-API] /synthesize request")
        log(f"[TTS-API] raw_text={req.text}")
        log(f"[TTS-API] play={req.play}, split={req.split}, out_wav={req.out_wav}")

        text = normalize_for_tts(req.text)
        log(f"[TTS-API] normalized_text={text}")

        if req.split:
            parts = split_sentences(
                text,
                int(os.getenv("MAX_SENTENCE_CHARS", "80")),
            )
        else:
            parts = [text]

        log(f"[TTS-API] parts={len(parts)}")
        wavs = []

        with _lock:
            tts = get_tts()

            for index, part in enumerate(parts, 1):
                if not part.strip():
                    continue

                log(f"[TTS-API] synth part {index}/{len(parts)}: {part}")
                out_wav = req.out_wav if req.out_wav and len(parts) == 1 else None

                synth_t0 = time.perf_counter()
                wav = tts.synthesize(
                    part,
                    out_wav=out_wav,
                    speed=req.speed,
                )
                synth_elapsed = time.perf_counter() - synth_t0

                log(f"[TTS-API] synth done wav={wav}, elapsed={synth_elapsed:.3f}s")
                wavs.append(wav)

                if req.play:
                    player = os.getenv("AUDIO_PLAYER", "aplay")
                    device = os.getenv("AUDIO_DEVICE", "")
                    wait = os.getenv("TTS_PLAY_WAIT", "0").lower() in ("1", "true", "yes", "on")
                    log(f"[TTS-API] play wav={wav}, player={player}, device={device}, wait={wait}")
                    play_wav(wav, player, device, wait=wait)
                    log("[TTS-API] play started" if not wait else "[TTS-API] play done")

        return {
            "ok": True,
            "count": len(wavs),
            "wavs": wavs,
        }
    except Exception as exc:
        tb = traceback.format_exc()
        log("[TTS-API][ERROR]")
        log(tb)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": repr(exc),
                "traceback": tb,
            },
        )


@app.post("/speak")
def speak(req: TTSRequest):
    new_req = TTSRequest(
        text=req.text,
        play=True,
        split=req.split,
        speed=req.speed,
        out_wav=req.out_wav,
    )
    return synthesize(new_req)
