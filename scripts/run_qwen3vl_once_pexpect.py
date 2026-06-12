#!/usr/bin/env python3
import os
import re
import sys
import time
import pexpect


DEMO_DIR = "/home/linaro/rkllm_qwen3vl4b/demo_Linux_aarch64"
IMAGE = "/home/linaro/test.jpg"
VISION_MODEL = "./qwen3-vl_vision_rk3588.rknn"
LLM_MODEL = "./qwen3-vl-4b-instruct_w8a8_rk3588.rkllm"


def clean_output(text: str, prompt: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)

    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        drop_keywords = [
            "rkllm-runtime",
            "rknpu driver",
            "model input num",
            "model input height",
            "input tensors",
            "output tensors",
            "index=",
            "n_dims=",
            "main: ImgEnc",
            "the core num",
            "可输入以下问题",
            "What is in the image",
            "这张图片中有什么",
            "************************************************************************",
            "****************",
            "请输入",
            "Input",
            "User",
            "user",
            "Assistant",
            "assistant",
            "exit",
        ]

        if any(k in line for k in drop_keywords):
            continue

        if line == prompt:
            continue

        lines.append(line)

    out = "\n".join(lines).strip()

    # 去掉可能残留的 prompt 回显
    out = out.replace(prompt, "").strip()

    # 去掉可能残留的 image token
    out = out.replace("<image>", "").strip()

    return out


def main():
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        prompt = "请描述这张图片。"

    # Qwen3-VL demo 示例问题都带 <image>，这里自动补上
    if "<image>" not in prompt:
        prompt_for_model = "<image>" + prompt
    else:
        prompt_for_model = prompt

    os.chdir(DEMO_DIR)

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = os.path.join(DEMO_DIR, "lib") + ":" + env.get("LD_LIBRARY_PATH", "")
    env["RKLLM_LOG_LEVEL"] = "0"

    cmd = (
        f"./demo "
        f"{IMAGE} "
        f"{VISION_MODEL} "
        f"{LLM_MODEL} "
        f"256 4096 3 "
        f"'<|vision_start|>' '<|vision_end|>' '<|image_pad|>'"
    )

    child = pexpect.spawn(
        "/bin/bash",
        ["-lc", cmd],
        cwd=DEMO_DIR,
        env=env,
        encoding="utf-8",
        timeout=300,
        echo=False,
    )

    # 等待菜单出现
    try:
        child.expect("可输入以下问题", timeout=180)
    except pexpect.TIMEOUT:
        # 有些版本没有中文菜单，但仍可能可以输入
        pass

    # 等待菜单打印完
    time.sleep(0.5)

    # 发送问题
    child.sendline(prompt_for_model)

    chunks = []
    start = time.time()
    last_output = time.time()
    overall_timeout = 420
    idle_timeout = 12

    while True:
        if time.time() - start > overall_timeout:
            break

        try:
            s = child.read_nonblocking(size=4096, timeout=1)
            if s:
                chunks.append(s)
                last_output = time.time()
        except pexpect.TIMEOUT:
            # 一段时间没有新输出，认为回答结束
            if chunks and time.time() - last_output > idle_timeout:
                break
        except pexpect.EOF:
            break

    # 尝试退出 demo
    try:
        child.sendline("exit")
        time.sleep(0.3)
        child.close(force=True)
    except Exception:
        pass

    raw = "".join(chunks)
    answer = clean_output(raw, prompt_for_model)

    if answer:
        print(answer)
    else:
        # 保底输出，方便你调试
        print(raw.strip())


if __name__ == "__main__":
    main()
