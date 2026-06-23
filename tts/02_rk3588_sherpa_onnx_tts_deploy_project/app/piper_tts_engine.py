import base64
import io
import os
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import soundfile as sf


DEFAULT_PIPER_EXTRA_PYTHONPATH = (
    "/home/linaro/Qwen/tts/piper_fast_frontend"
    + os.pathsep
    + "/home/linaro/Qwen/tts/torch_only_site"
)

# ── sys.path bootstrap for persistent engine ─────────────────────────────
# The TTS service process may not have torch / fast-frontend on its
# default sys.path.  Inject them once at import time so that
# ``import piper.voice`` can resolve g2pw→pypinyin, torch, etc.
for _entry in DEFAULT_PIPER_EXTRA_PYTHONPATH.split(os.pathsep):
    _entry = _entry.strip()
    if _entry and _entry not in sys.path:
        sys.path.insert(0, _entry)


@dataclass
class PiperTtsConfig:
    model: str
    config: str
    piper_bin: str = "piper"
    speaker: Optional[int] = None
    length_scale: Optional[float] = None
    noise_scale: Optional[float] = None
    noise_w: Optional[float] = None
    sentence_silence: Optional[float] = None
    data_dir: Optional[str] = None


def piper_config_from_env():
    model = os.environ.get(
        "PIPER_MODEL",
        "/home/linaro/Qwen/tts/models/piper_zh_xiao_ya_medium/zh_CN-xiao_ya-medium.onnx",
    )
    config = os.environ.get("PIPER_CONFIG", model + ".json")
    speaker = os.environ.get("PIPER_SPEAKER", "")
    return PiperTtsConfig(
        model=model,
        config=config,
        piper_bin=os.environ.get("PIPER_BIN", "piper"),
        speaker=int(speaker) if speaker.strip() else None,
        length_scale=_optional_float("PIPER_LENGTH_SCALE"),
        noise_scale=_optional_float("PIPER_NOISE_SCALE"),
        noise_w=_optional_float("PIPER_NOISE_W"),
        sentence_silence=_optional_float("PIPER_SENTENCE_SILENCE"),
        data_dir=os.environ.get("PIPER_DATA_DIR", "/home/linaro/Qwen/tts/piper_data"),
    )


def _optional_float(name):
    value = os.environ.get(name, "").strip()
    return float(value) if value else None


# ═══════════════════════════════════════════════════════════════════════════
#  Persistent engine  – loads PiperVoice once, reuses across requests
# ═══════════════════════════════════════════════════════════════════════════

class PersistentPiperEngine:
    """Piper TTS engine that keeps the ONNX model loaded in-process.

    Uses the ``piper.voice.PiperVoice`` Python API so that model
    loading happens **once** at service startup instead of inside a
    new subprocess for every ``/synthesize`` call.
    """

    def __init__(self, cfg: PiperTtsConfig):
        self.cfg = cfg
        self.model = Path(cfg.model)
        self.config = Path(cfg.config)
        if not self.model.exists():
            raise FileNotFoundError(f"missing Piper model: {self.model}")
        if not self.config.exists():
            raise FileNotFoundError(f"missing Piper config: {self.config}")

        # Ensure g2pW data dir exists (unused with fast frontend, but safe)
        if cfg.data_dir:
            Path(cfg.data_dir).mkdir(parents=True, exist_ok=True)

        # ── load ONNX model once ─────────────────────────────────────────
        from piper.voice import PiperVoice  # noqa: E402

        t0 = time.time()
        self._voice = PiperVoice.load(
            str(self.model),
            str(self.config),
            use_cuda=False,
            download_dir=str(Path(cfg.data_dir)) if cfg.data_dir else None,
        )
        _LOGGER.info("PersistentPiperEngine loaded in %.3fs", time.time() - t0)

    def synthesize(self, text: str, output: str, sid=None, speed=None, volume=None):
        text = (text or "").strip()
        if not text:
            raise ValueError("empty text")

        # ── build SynthesisConfig ────────────────────────────────────────
        from piper.config import SynthesisConfig  # noqa: E402

        syn_cfg_kwargs = {}

        speaker = self.cfg.speaker if sid is None else sid
        if speaker is not None:
            syn_cfg_kwargs["speaker_id"] = speaker

        if self.cfg.length_scale is not None:
            syn_cfg_kwargs["length_scale"] = self.cfg.length_scale
        elif speed and speed > 0:
            syn_cfg_kwargs["length_scale"] = 1.0 / float(speed)

        if self.cfg.noise_scale is not None:
            syn_cfg_kwargs["noise_scale"] = self.cfg.noise_scale
        if self.cfg.noise_w is not None:
            syn_cfg_kwargs["noise_w_scale"] = self.cfg.noise_w

        syn_cfg = SynthesisConfig(**syn_cfg_kwargs)

        sr = self._voice.config.sample_rate

        # ── in-memory mode: write WAV to BytesIO, no disk ─────────────
        if output == "__memory__":
            start = time.time()
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                self._voice.synthesize_wav(text, wf, syn_config=syn_cfg)
            pcm = buf.getvalue()
            elapsed = time.time() - start
            if len(pcm) == 0:
                raise RuntimeError("Piper produced empty wav")
            duration = (len(pcm) - 44) / (2 * sr)  # WAV header = 44 bytes
            return {
                "sample_rate": int(sr),
                "duration_sec": duration,
                "elapsed_sec": elapsed,
                "rtf": elapsed / max(duration, 1e-6),
                "backend": "piper-persistent",
                "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                "pcm_len": len(pcm),
                "pcm_is_wav": True,   # Piper writes WAV, not raw PCM
            }

        # ── file mode (original) ────────────────────────────────────────
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            self._voice.synthesize_wav(text, wf, syn_config=syn_cfg)
        elapsed = time.time() - start

        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"Piper produced empty wav: {out}")

        info = sf.info(str(out))
        duration = float(info.frames) / float(info.samplerate)
        return {
            "output": str(out),
            "sample_rate": int(info.samplerate),
            "duration_sec": duration,
            "elapsed_sec": elapsed,
            "rtf": elapsed / max(duration, 1e-6),
            "backend": "piper-persistent",
        }


# ═══════════════════════════════════════════════════════════════════════════
#  Subprocess engine  – original implementation kept as fallback
# ═══════════════════════════════════════════════════════════════════════════

class PiperTtsEngine:
    """Original subprocess-based Piper backend.

    Each ``/synthesize`` call spawns a new ``piper`` CLI process.
    Kept as fallback – set ``PIPER_BACKEND=subprocess`` to use.
    """

    def __init__(self, cfg: PiperTtsConfig):
        self.cfg = cfg
        self.model = Path(cfg.model)
        self.config = Path(cfg.config)
        if not self.model.exists():
            raise FileNotFoundError(f"missing Piper model: {self.model}")
        if not self.config.exists():
            raise FileNotFoundError(f"missing Piper config: {self.config}")

    def synthesize(self, text, output, sid=None, speed=None, volume=None):
        text = (text or "").strip()
        if not text:
            raise ValueError("empty text")

        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.cfg.piper_bin,
            "--model",
            str(self.model),
            "--config",
            str(self.config),
            "--output_file",
            str(out),
        ]

        speaker = self.cfg.speaker if sid is None else sid
        if speaker is not None:
            cmd += ["--speaker", str(speaker)]

        if self.cfg.length_scale is not None:
            cmd += ["--length_scale", str(self.cfg.length_scale)]
        elif speed and speed > 0:
            cmd += ["--length_scale", str(1.0 / float(speed))]

        if self.cfg.noise_scale is not None:
            cmd += ["--noise_scale", str(self.cfg.noise_scale)]
        if self.cfg.noise_w is not None:
            cmd += ["--noise_w", str(self.cfg.noise_w)]
        if self.cfg.sentence_silence is not None:
            cmd += ["--sentence_silence", str(self.cfg.sentence_silence)]
        if self.cfg.data_dir:
            Path(self.cfg.data_dir).mkdir(parents=True, exist_ok=True)
            cmd += ["--data-dir", str(self.cfg.data_dir)]

        start = time.time()
        env = os.environ.copy()
        extra_pythonpath = os.environ.get(
            "PIPER_EXTRA_PYTHONPATH", DEFAULT_PIPER_EXTRA_PYTHONPATH
        ).strip()
        if extra_pythonpath:
            current_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                extra_pythonpath
                if not current_pythonpath
                else extra_pythonpath + os.pathsep + current_pythonpath
            )

        proc = subprocess.run(
            cmd,
            input=text + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(self.cfg.data_dir) if self.cfg.data_dir else None,
        )
        elapsed = time.time() - start
        if proc.returncode != 0:
            raise RuntimeError(
                f"Piper failed: {proc.returncode}\n{proc.stdout[-2000:]}"
            )
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(
                f"Piper did not create output wav: {out}\n{proc.stdout[-2000:]}"
            )

        info = sf.info(str(out))
        duration = float(info.frames) / float(info.samplerate)
        return {
            "output": str(out),
            "sample_rate": int(info.samplerate),
            "duration_sec": duration,
            "elapsed_sec": elapsed,
            "rtf": elapsed / max(duration, 1e-6),
            "backend": "piper-subprocess",
        }


# ═══════════════════════════════════════════════════════════════════════════
#  Factory
# ═══════════════════════════════════════════════════════════════════════════

import logging  # noqa: E402

_LOGGER = logging.getLogger("piper_tts_engine")


def create_piper_engine(cfg: PiperTtsConfig):
    """Return the right Piper engine based on ``PIPER_BACKEND`` env var.

    ``persistent`` (default) – loads model once, reuses across requests.
    ``subprocess``           – original behaviour, one process per request.
    """
    backend = os.environ.get("PIPER_BACKEND", "persistent").strip().lower()
    if backend == "subprocess":
        _LOGGER.info("using subprocess Piper backend")
        return PiperTtsEngine(cfg)
    _LOGGER.info("using persistent Piper backend")
    return PersistentPiperEngine(cfg)
