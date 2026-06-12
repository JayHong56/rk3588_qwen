from typing import List
_END = set("。！？!?；;\n")

def split_sentences(text: str, max_chars: int = 80) -> List[str]:
    out, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch in _END or len(buf) >= max_chars:
            s = "".join(buf).strip()
            if s: out.append(s)
            buf = []
    tail = "".join(buf).strip()
    if tail: out.append(tail)
    return out
