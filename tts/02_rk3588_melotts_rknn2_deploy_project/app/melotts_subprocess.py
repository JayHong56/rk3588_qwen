import os, subprocess, time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class MeloTTSConfig:
    root: Path
    python_bin: str = "python"
    sample_rate: int = 44100
    speed: float = 0.8
    output_dir: Path = Path("output")

class MeloTTSSubprocess:
    def __init__(self, cfg: MeloTTSConfig):
        self.cfg = cfg
        self.cfg.root = Path(cfg.root).resolve()
        self.cfg.output_dir = Path(cfg.output_dir).resolve()
        self.cfg.output_dir.mkdir(parents=True, exist_ok=True)
        required = ["melotts_rknn.py","encoder.onnx","decoder.rknn","g.bin","lexicon.txt","tokens.txt"]
        missing = [x for x in required if not (self.cfg.root/x).exists()]
        if missing:
            raise FileNotFoundError(f"缺少 MeloTTS-RKNN2 文件: {missing}, root={self.cfg.root}")

    def synthesize(self, text: str, out_wav: Optional[str] = None, speed: Optional[float] = None) -> str:
        out = Path(out_wav).resolve() if out_wav else self.cfg.output_dir / f"melotts_{int(time.time()*1000)}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.cfg.python_bin, "melotts_rknn.py",
            "-s", text,
            "-w", str(out),
            "-e", "encoder.onnx",
            "-d", "decoder.rknn",
            "-sr", str(self.cfg.sample_rate),
            "--speed", str(speed if speed is not None else self.cfg.speed),
            "--lexicon", "lexicon.txt",
            "--token", "tokens.txt",
        ]
        proc = subprocess.run(cmd, cwd=str(self.cfg.root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            raise RuntimeError(f"MeloTTS failed: {proc.returncode}\n{proc.stdout}")
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"wav 未生成: {out}\n{proc.stdout}")
        return str(out)
