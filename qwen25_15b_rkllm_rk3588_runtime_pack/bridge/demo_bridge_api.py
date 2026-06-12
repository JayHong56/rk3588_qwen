#!/usr/bin/env python3
"""HTTP bridge for official interactive llm_demo.

This is a temporary validation wrapper. It keeps the demo process alive and talks to
its stdin/stdout with pexpect. For production, rewrite with RKLLM C/C++ API directly
so rkllm_init() happens once and streaming tokens can be controlled cleanly.
"""
import os
import re
import threading
from pathlib import Path
from typing import Optional

import pexpect
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

APP_DIR = Path(os.environ.get('APP_DIR', os.getcwd())).resolve()
DEMO_BIN = os.environ.get('DEMO_BIN', 'llm_demo')
MODEL_FILE = os.environ.get('MODEL_FILE', 'Qwen2.5-1.5B-Instruct_W8A8_RK3588.rkllm')
MAX_NEW_TOKENS = os.environ.get('MAX_NEW_TOKENS', '128')
MAX_CONTEXT_LEN = os.environ.get('MAX_CONTEXT_LEN', '4096')
BRIDGE_HOST = os.environ.get('BRIDGE_HOST', '0.0.0.0')
BRIDGE_PORT = int(os.environ.get('BRIDGE_PORT', '18080'))

app = FastAPI(title='RKLLM demo bridge', version='0.1-test-only')
lock = threading.Lock()
child: Optional[pexpect.spawn] = None


class ChatReq(BaseModel):
    text: str
    timeout: int = 90


class ChatResp(BaseModel):
    text: str


def start_child() -> pexpect.spawn:
    global child
    if child is not None and child.isalive():
        return child

    cmd = f'./{DEMO_BIN} ./{MODEL_FILE} {MAX_NEW_TOKENS} {MAX_CONTEXT_LEN}'
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = f"{APP_DIR / 'lib'}:{env.get('LD_LIBRARY_PATH', '')}"
    env.setdefault('RKLLM_LOG_LEVEL', '1')
    child = pexpect.spawn(cmd, cwd=str(APP_DIR), env=env, encoding='utf-8', timeout=180)
    child.logfile_read = None
    child.expect('user:', timeout=180)
    return child


def clean_output(raw: str) -> str:
    s = raw.replace('\r', '')
    if 'robot:' in s:
        s = s.split('robot:', 1)[1]
    s = re.sub(r'\n?user:\s*$', '', s).strip()
    return s


@app.get('/health')
def health():
    alive = child is not None and child.isalive()
    return {'ok': True, 'demo_alive': alive, 'model': MODEL_FILE}


@app.post('/chat', response_model=ChatResp)
def chat(req: ChatReq):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail='text is empty')
    with lock:
        proc = start_child()
        proc.sendline(text)
        proc.expect('user:', timeout=req.timeout)
        return ChatResp(text=clean_output(proc.before))


@app.post('/clear')
def clear():
    with lock:
        proc = start_child()
        proc.sendline('clear')
        proc.expect('user:', timeout=60)
    return {'ok': True}


@app.on_event('shutdown')
def shutdown():
    global child
    if child is not None and child.isalive():
        child.sendline('exit')
        child.close(force=True)


if __name__ == '__main__':
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT)
