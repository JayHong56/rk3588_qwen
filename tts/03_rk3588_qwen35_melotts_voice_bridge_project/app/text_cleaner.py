import re
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S | re.I)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
URL = re.compile(r"https?://\S+|www\.\S+")

def clean_for_speech(text: str) -> str:
    text = text or ""
    text = THINK_BLOCK.sub("", text)
    text = CODE_BLOCK.sub(" 代码内容已省略。 ", text)
    text = URL.sub(" 链接 ", text)
    text = re.sub(r"[*_`#>\[\]()]","",text)
    text = re.sub(r"\s+"," ",text)
    return text.strip()
