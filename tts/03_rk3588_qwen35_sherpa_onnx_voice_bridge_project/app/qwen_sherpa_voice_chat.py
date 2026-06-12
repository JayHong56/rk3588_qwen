#!/usr/bin/env python3
import argparse, os
from pathlib import Path
from app.qwen_client import qwen_stream
from app.text_normalizer import normalize_for_tts
from app.sentence_splitter import split_ready_sentences
from app.tts_client import speak

def load_env(path):
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); os.environ.setdefault(k,os.path.expandvars(v))

def run_once(prompt, do_speak=True):
    answer=[]; buf=''; spoken=0; print('助手：',end='',flush=True)
    for chunk in qwen_stream(prompt):
        print(chunk,end='',flush=True); answer.append(chunk); n=normalize_for_tts(chunk)
        if not n: continue
        buf+=n; ready,buf=split_ready_sentences(buf)
        for s in ready:
            if do_speak: speak(s,play=True); spoken+=1
    print(); final=normalize_for_tts(buf)
    if final and do_speak: speak(final,play=True); spoken+=1
    return {'answer':''.join(answer),'spoken_sentences':spoken}

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--env',default='config/voice_bridge.env'); ap.add_argument('prompt'); ap.add_argument('--no-speak',action='store_true'); a=ap.parse_args(); load_env(a.env); print(run_once(a.prompt,not a.no_speak))
