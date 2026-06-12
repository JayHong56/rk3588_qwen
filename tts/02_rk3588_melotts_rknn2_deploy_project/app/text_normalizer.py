import re
_CODE_BLOCK = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_URL = re.compile(r"https?://\S+|www\.\S+")

def normalize_for_tts(text: str) -> str:
    text = text or ""
    text = _CODE_BLOCK.sub(" 代码内容已省略。 ", text)
    text = _INLINE_CODE.sub(lambda m: m.group(1), text)
    text = _URL.sub(" 链接 ", text)
    text = re.sub(r"[*_#>\[\]()]","",text)
    text = re.sub(r"\s+"," ",text)
    return text.strip()
