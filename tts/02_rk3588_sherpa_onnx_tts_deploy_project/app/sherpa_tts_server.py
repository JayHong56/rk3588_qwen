import os, time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.sherpa_tts_engine import SherpaTtsEngine, config_from_env
from app.piper_tts_engine import PiperTtsEngine, piper_config_from_env
from app.audio_player import play_audio

def load_env(path):
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); os.environ.setdefault(k,os.path.expandvars(v))
load_env(os.environ.get('SHERPA_TTS_ENV','config/sherpa_tts.env'))
app=FastAPI(title='RK3588 TTS Service')

def create_engine():
    backend = os.environ.get('TTS_ENGINE', 'sherpa_vits').strip().lower()
    if backend in {'sherpa', 'sherpa_vits', 'vits'}:
        return backend, SherpaTtsEngine(config_from_env())
    if backend == 'piper':
        return backend, PiperTtsEngine(piper_config_from_env())
    raise RuntimeError(f'unsupported TTS_ENGINE={backend}')

backend_name, engine = create_engine()

class Req(BaseModel): text:str; output:Optional[str]=None; sid:Optional[int]=None; speed:Optional[float]=None; play:bool=False
@app.get('/health')
def health():
    return {
        'ok': True,
        'backend': backend_name,
        'model_dir': os.environ.get('SHERPA_MODEL_DIR'),
        'piper_model': os.environ.get('PIPER_MODEL'),
        'provider': os.environ.get('SHERPA_PROVIDER','cpu'),
    }
@app.post('/synthesize')
def synth(req:Req):
    try: return engine.synthesize(req.text, req.output or str(Path(os.environ.get('OUTPUT_DIR','output'))/f'tts_{int(time.time()*1000)}.wav'), req.sid, req.speed)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
@app.post('/speak')
def speak(req:Req):
    try:
        r=engine.synthesize(req.text, req.output or str(Path(os.environ.get('OUTPUT_DIR','output'))/f'tts_{int(time.time()*1000)}.wav'), req.sid, req.speed)
        if req.play: play_audio(r['output'])
        r['played']=req.play; return r
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
