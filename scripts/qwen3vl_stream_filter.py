#!/usr/bin/env python3
import re
import sys
import time
from pathlib import Path

raw_path = Path(sys.argv[1])
clean_path = Path(sys.argv[2])
user_prompt = sys.argv[3]
send_prompt = sys.argv[4]

raw_f = raw_path.open("a", encoding="utf-8", errors="ignore")
clean_f = clean_path.open("a", encoding="utf-8", errors="ignore")

answer_started = False

noise_patterns = [
    r"^\s*[IWE]\s+rkllm:",
    r"^\s*[IWE]\s+RKNN:",
    r"rkllm-runtime version",
    r"rknpu driver version",
    r"loading rkllm",
    r"rkllm-toolkit version",
    r"max_context_limit",
    r"target_platform",
    r"model_dtype",
    r"Enabled cpus",
    r"Using mrope",
    r"rkllm init success",
    r"LLM Model loaded",
    r"ImgEnc Model loaded",
    r"ImgEnc Model inference took",
    r"===the core num",
    r"model input num",
    r"input tensors",
    r"output tensors",
    r"input tensor",
    r"output tensor",
    r"index=\d+",
    r"name=pixel",
    r"n_dims=",
    r"dims=\[",
    r"n_elems=",
    r"fmt=",
    r"size=",
    r"main:",
    r"Warning: Your rknpu driver",
    r"failed to submit",
    r"update to the latest toolkit",
    r"file storage",
    r"可输入以下问题对应序号",
    r"自定义输入",
    r"^\*{5,}",
    r"^\[0\]",
    r"^\[1\]",
]

def elog(msg):
    print(f"[{time.strftime('%F %T')}][QWEN-FILTER] {msg}", file=sys.stderr, flush=True)

def is_noise(s: str) -> bool:
    for pat in noise_patterns:
        if re.search(pat, s, flags=re.I):
            return True
    return False

def clean_line(s: str) -> str:
    s = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s)
    s = s.replace("\r", "")
    s = s.strip()

    # demo 常见输出：user: robot: xxx
    s = re.sub(r"^.*?\buser\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?\brobot\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?\bassistant\s*[:：]\s*", "", s, flags=re.I)
    s = re.sub(r"^.*?助手\s*[:：]\s*", "", s)
    s = re.sub(r"^.*?回答\s*[:：]\s*", "", s)

    s = s.replace(send_prompt, "")
    s = s.replace(user_prompt, "")
    s = s.replace("<image>", "")
    s = s.strip()
    return s

elog("stream filter started")

try:
    for line in sys.stdin:
        raw_f.write(line)
        raw_f.flush()

        s0 = line.strip()

        if s0:
            print(f"[{time.strftime('%F %T')}][QWEN-DEMO-OUT] {s0}", file=sys.stderr, flush=True)

        if not s0:
            continue

        lower = s0.lower()

        # 只有看到 robot/assistant 后，才开始把内容当成回答
        if not answer_started:
            if "robot:" in lower or "assistant:" in lower or "助手" in s0 or "回答" in s0:
                answer_started = True
                elog("answer stream started")
            else:
                continue

        if is_noise(s0):
            continue

        if user_prompt and user_prompt in s0 and "robot" not in lower and "assistant" not in lower:
            continue

        if send_prompt and send_prompt in s0 and "robot" not in lower and "assistant" not in lower:
            continue

        if lower in {"exit", "quit", "q"}:
            continue

        s = clean_line(s0)
        if not s:
            continue

        clean_f.write(s + "\n")
        clean_f.flush()

        # 只有真正回答写到 stdout，桥接工程才会拿去做 TTS
        print(s, flush=True)

finally:
    elog("stream filter finished")
    raw_f.close()
    clean_f.close()
