import json
import os
import shlex
import subprocess
import sys
import threading
import time

import httpx


def _debug_enabled() -> bool:
    return os.getenv("VOICE_DEBUG", "0").lower() in ("1", "true", "yes", "on")


def _now() -> str:
    return time.strftime("%F %T")


def _log(tag: str, msg: str) -> None:
    if _debug_enabled():
        print(f"[{_now()}][{tag}] {msg}", file=sys.stderr, flush=True)


class QwenClient:
    def __init__(self):
        self.backend = os.getenv("QWEN_BACKEND", "openai").lower()
        self.base = os.getenv("QWEN_API_BASE", "http://127.0.0.1:8000/v1").rstrip("/")
        self.key = os.getenv("QWEN_API_KEY", "EMPTY")
        self.model = os.getenv("QWEN_MODEL", "qwen3.5-2b")
        self.temperature = float(os.getenv("QWEN_TEMPERATURE", "0.7"))
        self.max_tokens = int(os.getenv("QWEN_MAX_TOKENS", "512"))
        self.cmd = os.getenv("QWEN_CMD", "")

    def stream_chat(self, prompt: str, system: str = "你是一个简洁、可靠的中文语音助手。"):
        _log("QWEN", f"backend={self.backend}")
        if self.backend == "cmd":
            yield from self._cmd_chat(prompt)
        else:
            yield from self._openai_chat(prompt, system)

    def _cmd_chat(self, prompt: str):
        if not self.cmd:
            raise RuntimeError("QWEN_BACKEND=cmd 但 QWEN_CMD 未配置")

        cmd = shlex.split(self.cmd) + [prompt]

        _log("QWEN-CMD", "start subprocess")
        _log("QWEN-CMD", "cmd=" + " ".join(cmd))

        t0 = time.time()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )

        def pump_stderr():
            assert proc.stderr is not None
            for line in proc.stderr:
                print(f"[{_now()}][QWEN-STDERR] {line}", end="", file=sys.stderr, flush=True)

        def watchdog():
            last = 0
            while proc.poll() is None:
                elapsed = int(time.time() - t0)
                if elapsed >= last + 10:
                    last = elapsed
                    print(
                        f"[{_now()}][QWEN-WATCHDOG] qwen still running, elapsed={elapsed}s, pid={proc.pid}",
                        file=sys.stderr,
                        flush=True,
                    )
                time.sleep(1)

        threading.Thread(target=pump_stderr, daemon=True).start()
        threading.Thread(target=watchdog, daemon=True).start()

        assert proc.stdout is not None

        first = True
        char_count = 0
        last_report = time.time()

        while True:
            ch = proc.stdout.read(1)

            if ch:
                if first:
                    _log("QWEN-CMD", f"first stdout received after {time.time() - t0:.2f}s")
                    first = False

                char_count += 1

                if _debug_enabled() and time.time() - last_report > 5:
                    _log("QWEN-CMD", f"received stdout chars={char_count}")
                    last_report = time.time()

                yield ch
                continue

            if proc.poll() is not None:
                break

            time.sleep(0.02)

        code = proc.wait()
        elapsed = time.time() - t0

        _log("QWEN-CMD", f"subprocess finished code={code}, elapsed={elapsed:.2f}s, chars={char_count}")

        if code != 0:
            raise RuntimeError(f"Qwen command failed code={code}")

    def _openai_chat(self, prompt: str, system: str):
        url = self.base + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        _log("QWEN-HTTP", f"POST {url}")

        t0 = time.time()
        count = 0

        with httpx.Client(timeout=None) as client:
            with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()

                for line in resp.iter_lines():
                    if not line:
                        continue

                    data = line[len("data:"):].strip() if line.startswith("data:") else line.strip()

                    if data == "[DONE]":
                        break

                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue

                    content = obj.get("choices", [{}])[0].get("delta", {}).get("content") or ""

                    if content:
                        count += len(content)
                        yield content

        _log("QWEN-HTTP", f"done elapsed={time.time() - t0:.2f}s, chars={count}")
