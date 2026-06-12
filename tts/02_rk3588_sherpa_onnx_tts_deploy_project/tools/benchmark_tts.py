#!/usr/bin/env python3
import os
from pathlib import Path
from app.sherpa_tts_engine import SherpaTtsEngine, config_from_env
if Path('config/sherpa_tts.env').exists():
    for line in Path('config/sherpa_tts.env').read_text().splitlines():
        if line.strip() and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); os.environ.setdefault(k,v)
e=SherpaTtsEngine(config_from_env())
for i,t in enumerate(['你好，这是第一条测试。','Qwen 生成文本后，sherpa-onnx 负责播报。','This is a mixed English and Chinese benchmark.']): print(e.synthesize(t,f'output/bench_{i}.wav'))
