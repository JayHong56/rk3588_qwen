#!/usr/bin/env python3
import argparse, os, time
from pathlib import Path
from app.melotts_subprocess import MeloTTSConfig, MeloTTSSubprocess

ap=argparse.ArgumentParser()
ap.add_argument("--texts", nargs="+", required=True)
args=ap.parse_args()
tts=MeloTTSSubprocess(MeloTTSConfig(
    root=Path(os.getenv("MELOTTS_DIR","/home/rock/MeloTTS-RKNN2")),
    python_bin=os.getenv("PYTHON_BIN","python"),
    sample_rate=int(os.getenv("MELOTTS_SAMPLE_RATE","44100")),
    speed=float(os.getenv("MELOTTS_SPEED","0.8")),
    output_dir=Path(os.getenv("VOICE_OUTPUT_DIR","output")),
))
for text in args.texts:
    t0=time.perf_counter()
    wav=tts.synthesize(text)
    print(f"{time.perf_counter()-t0:.3f}s\t{len(text)} chars\t{wav}")
