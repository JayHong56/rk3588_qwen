#!/usr/bin/env python3
import argparse, os
from pathlib import Path
from app.melotts_subprocess import MeloTTSConfig, MeloTTSSubprocess
from app.text_normalizer import normalize_for_tts
from app.audio_player import play_wav

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--out", default="")
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--speed", type=float, default=float(os.getenv("MELOTTS_SPEED","0.8")))
    args=ap.parse_args()
    tts=MeloTTSSubprocess(MeloTTSConfig(
        root=Path(os.getenv("MELOTTS_DIR","/home/rock/MeloTTS-RKNN2")),
        python_bin=os.getenv("PYTHON_BIN","python"),
        sample_rate=int(os.getenv("MELOTTS_SAMPLE_RATE","44100")),
        speed=args.speed,
        output_dir=Path(os.getenv("VOICE_OUTPUT_DIR","output")),
    ))
    wav=tts.synthesize(normalize_for_tts(args.text), args.out or None, args.speed)
    print(wav)
    if args.play:
        play_wav(wav, os.getenv("AUDIO_PLAYER","aplay"), os.getenv("AUDIO_DEVICE",""))

if __name__=="__main__":
    main()
