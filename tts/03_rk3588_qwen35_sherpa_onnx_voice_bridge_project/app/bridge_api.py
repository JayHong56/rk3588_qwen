import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.qwen_sherpa_voice_chat import run_once
from app.tts_client import health as tts_health

def load_env(path):
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); os.environ.setdefault(k,os.path.expandvars(v))
load_env(os.environ.get('VOICE_BRIDGE_ENV','config/voice_bridge.env'))
app=FastAPI(title='Qwen3.5 + sherpa-onnx voice bridge')
class Req(BaseModel): prompt:str; speak:bool=True
@app.get('/health')
def health():
    d={'ok':True,'qwen_backend':os.environ.get('QWEN_BACKEND'),'qwen_api_base':os.environ.get('QWEN_API_BASE'),'tts_api_base':os.environ.get('TTS_API_BASE')}
    try: d['tts']=tts_health()
    except Exception as e: d['tts_error']=str(e)
    return d
@app.post('/chat_speak')
def chat_speak(req:Req):
    try: return run_once(req.prompt,req.speak)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
