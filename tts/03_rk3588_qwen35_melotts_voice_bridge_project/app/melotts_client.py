import os
import sys
import time

import requests


def _debug_enabled() -> bool:
    return os.getenv("VOICE_DEBUG", "0").lower() in ("1", "true", "yes", "on")


def _log(tag: str, msg: str) -> None:
    if _debug_enabled():
        print(f"[{time.strftime('%F %T')}][{tag}] {msg}", file=sys.stderr, flush=True)


class MeloTTSClient:
    def __init__(self, url=None, play=None, split=None):
        self.url = url or os.getenv("TTS_API_URL", "http://127.0.0.1:8010/speak")
        self.play = play if play is not None else os.getenv("TTS_PLAY", "true").lower() in ("1", "true", "yes", "on")
        self.split = split if split is not None else os.getenv("TTS_SPLIT", "false").lower() in ("1", "true", "yes", "on")

    def speak(self, text: str, timeout: float = 180):
        text = text.strip()
        if not text:
            return None

        payload = {
            "text": text,
            "play": self.play,
            "split": self.split,
        }

        _log("TTS", f"POST {self.url}, chars={len(text)}, play={self.play}, split={self.split}")
        _log("TTS", f"text={text}")

        t0 = time.time()

        r = requests.post(self.url, json=payload, timeout=timeout)

        dt = time.time() - t0

        _log("TTS", f"response status={r.status_code}, elapsed={dt:.2f}s")

        r.raise_for_status()
        return r.json()
