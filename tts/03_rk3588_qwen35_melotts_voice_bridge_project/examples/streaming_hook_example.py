import requests
from app.sentence_streamer import SentenceStreamer
from app.text_cleaner import clean_for_speech

splitter = SentenceStreamer(max_chars=80, min_chars=4)

def speak(sentence: str):
    requests.post("http://127.0.0.1:8010/speak", json={"text": sentence, "play": True, "split": False}, timeout=180).raise_for_status()

def on_qwen_token(token: str):
    print(token, end="", flush=True)
    for sentence in splitter.feed(clean_for_speech(token)):
        speak(sentence)

def on_qwen_done():
    for sentence in splitter.flush():
        speak(clean_for_speech(sentence))
