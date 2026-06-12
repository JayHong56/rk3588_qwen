import os, json, shlex, subprocess, sys, threading, time, requests

def _now():
    return time.strftime('%F %T')

def qwen_stream(prompt):
    backend=os.environ.get('QWEN_BACKEND','openai').lower()
    if backend=='dummy':
        for ch in '这是桥接测试回答。Qwen 还没有接入，但 sherpa-onnx 语音链路可以先验证。': yield ch
        return
    if backend=='command':
        cmd=os.environ.get('QWEN_CMD');
        if not cmd: raise RuntimeError('QWEN_CMD empty')
        args=shlex.split(cmd)+[prompt]
        print(f'[{_now()}][QWEN-CMD] start: {" ".join(args)}', file=sys.stderr, flush=True)
        t0=time.time()
        p=subprocess.Popen(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=1,env=os.environ.copy())
        def pump_stderr():
            assert p.stderr is not None
            for line in p.stderr:
                print(f'[{_now()}][QWEN-STDERR] {line}', end='', file=sys.stderr, flush=True)
        threading.Thread(target=pump_stderr,daemon=True).start()
        assert p.stdout is not None
        first=True
        for line in p.stdout:
            if first:
                print(f'[{_now()}][QWEN-CMD] first stdout after {time.time()-t0:.3f}s', file=sys.stderr, flush=True)
                first=False
            for ch in line:
                yield ch
        rc=p.wait()
        print(f'[{_now()}][QWEN-CMD] finished rc={rc}, elapsed={time.time()-t0:.3f}s', file=sys.stderr, flush=True)
        if rc!=0:
            raise RuntimeError(f'Qwen command failed: {rc}')
        return
    base=os.environ.get('QWEN_API_BASE','http://127.0.0.1:8000/v1').rstrip('/'); key=os.environ.get('QWEN_API_KEY','EMPTY'); model=os.environ.get('QWEN_MODEL','Qwen/Qwen3.5-2B')
    stream=os.environ.get('QWEN_STREAM','true').lower()=='true'
    payload={'model':model,'messages':[{'role':'user','content':prompt}],'stream':stream,'temperature':float(os.environ.get('QWEN_TEMPERATURE','0.6')),'max_tokens':int(os.environ.get('QWEN_MAX_TOKENS','512'))}
    headers={'Content-Type':'application/json','Authorization':'Bearer '+key}
    if stream:
        with requests.post(base+'/chat/completions',headers=headers,json=payload,stream=True,timeout=300) as r:
            r.raise_for_status()
            for raw in r.iter_lines(decode_unicode=True):
                if not raw: continue
                line=raw.strip(); line=line[5:].strip() if line.startswith('data:') else line
                if line=='[DONE]': break
                try:
                    c=json.loads(line)['choices'][0].get('delta',{}).get('content','')
                    if c: yield c
                except Exception: pass
    else:
        r=requests.post(base+'/chat/completions',headers=headers,json=payload,timeout=300); r.raise_for_status(); content=r.json()['choices'][0]['message']['content']
        for ch in content: yield ch
