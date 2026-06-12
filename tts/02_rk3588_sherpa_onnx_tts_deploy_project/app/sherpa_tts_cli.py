#!/usr/bin/env python3
import argparse, os
from pathlib import Path
from app.sherpa_tts_engine import SherpaTtsEngine, config_from_env
from app.audio_player import play_audio

def load_env(path):
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); os.environ.setdefault(k,os.path.expandvars(v))
ap=argparse.ArgumentParser(); ap.add_argument('--env',default='config/sherpa_tts.env'); ap.add_argument('--text',required=True); ap.add_argument('--output',default='output/tts.wav'); ap.add_argument('--play',action='store_true'); args=ap.parse_args()
load_env(args.env); r=SherpaTtsEngine(config_from_env()).synthesize(args.text,args.output); print(r)
if args.play: play_audio(r['output'])
