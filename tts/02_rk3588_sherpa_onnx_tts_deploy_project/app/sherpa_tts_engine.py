import os, time, threading
from pathlib import Path
from dataclasses import dataclass
import sherpa_onnx, soundfile as sf

@dataclass
class SherpaTtsConfig:
    model_dir:str; model_file:str='model.onnx'; lexicon_file:str='lexicon.txt'; tokens_file:str='tokens.txt'; rule_fsts:str='date.fst,number.fst'; provider:str='cpu'; num_threads:int=4; sid:int=0; speed:float=1.0

def config_from_env():
    return SherpaTtsConfig(os.environ.get('SHERPA_MODEL_DIR','/home/rock/models/vits-melo-tts-zh_en'), os.environ.get('SHERPA_VITS_MODEL','model.onnx'), os.environ.get('SHERPA_VITS_LEXICON','lexicon.txt'), os.environ.get('SHERPA_VITS_TOKENS','tokens.txt'), os.environ.get('SHERPA_RULE_FSTS','date.fst,number.fst'), os.environ.get('SHERPA_PROVIDER','cpu'), int(os.environ.get('SHERPA_NUM_THREADS','4')), int(os.environ.get('SHERPA_SID','0')), float(os.environ.get('SHERPA_SPEED','1.0')))

class SherpaTtsEngine:
    def __init__(self,cfg): self.cfg=cfg; self.model_dir=Path(cfg.model_dir); self.lock=threading.Lock(); self.tts=self._create()
    def _create(self):
        m=self.model_dir/self.cfg.model_file; lex=self.model_dir/self.cfg.lexicon_file; tok=self.model_dir/self.cfg.tokens_file
        for p in [m,lex,tok]:
            if not p.exists(): raise FileNotFoundError('missing '+str(p))
        rules=[str(self.model_dir/x.strip()) for x in self.cfg.rule_fsts.split(',') if x.strip() and (self.model_dir/x.strip()).exists()]
        cfg=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(m),lexicon=str(lex),tokens=str(tok)),num_threads=self.cfg.num_threads,provider=self.cfg.provider),rule_fsts=','.join(rules),max_num_sentences=1)
        if not cfg.validate(): raise RuntimeError('invalid sherpa config')
        return sherpa_onnx.OfflineTts(cfg)
    def synthesize(self,text,output,sid=None,speed=None):
        text=(text or '').strip();
        if not text: raise ValueError('empty text')
        sid=self.cfg.sid if sid is None else sid; speed=self.cfg.speed if speed is None else speed
        out=Path(output); out.parent.mkdir(parents=True,exist_ok=True)
        with self.lock:
            st=time.time(); audio=self.tts.generate(text,sid=sid,speed=speed); el=time.time()-st
        if len(audio.samples)==0: raise RuntimeError('empty audio')
        sf.write(str(out),audio.samples,audio.sample_rate); dur=len(audio.samples)/audio.sample_rate
        return {'output':str(out),'sample_rate':audio.sample_rate,'duration_sec':dur,'elapsed_sec':el,'rtf':el/max(dur,1e-6)}
