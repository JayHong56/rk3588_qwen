import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import soundfile as sf


DEFAULT_PIPER_EXTRA_PYTHONPATH = (
    "/home/linaro/Qwen/tts/piper_fast_frontend"
    + os.pathsep
    + "/home/linaro/Qwen/tts/torch_only_site"
)


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


class PiperTtsEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.model = Path(cfg.model)
        self.config = Path(cfg.config)
        if not self.model.exists():
            raise FileNotFoundError(f"missing Piper model: {self.model}")
        if not self.config.exists():
            raise FileNotFoundError(f"missing Piper config: {self.config}")

    def synthesize(self, text, output, sid=None, speed=None):
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
            # Piper length_scale is roughly inverse speed.
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
        extra_pythonpath = os.environ.get("PIPER_EXTRA_PYTHONPATH", DEFAULT_PIPER_EXTRA_PYTHONPATH).strip()
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
            raise RuntimeError(f"Piper failed: {proc.returncode}\n{proc.stdout[-2000:]}")
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"Piper did not create output wav: {out}\n{proc.stdout[-2000:]}")

        info = sf.info(str(out))
        duration = float(info.frames) / float(info.samplerate)
        return {
            "output": str(out),
            "sample_rate": int(info.samplerate),
            "duration_sec": duration,
            "elapsed_sec": elapsed,
            "rtf": elapsed / max(duration, 1e-6),
            "backend": "piper",
        }
