END = set("。！？!?；;\n")

class SentenceStreamer:
    def __init__(self, max_chars: int = 80, min_chars: int = 4):
        self.max_chars = max_chars
        self.min_chars = min_chars
        self.buf = []

    def feed(self, text: str):
        out = []
        for ch in text:
            self.buf.append(ch)
            if ch in END or len(self.buf) >= self.max_chars:
                s = "".join(self.buf).strip()
                self.buf = []
                if len(s) >= self.min_chars:
                    out.append(s)
        return out

    def flush(self):
        s = "".join(self.buf).strip()
        self.buf = []
        return [s] if len(s) >= self.min_chars else []
