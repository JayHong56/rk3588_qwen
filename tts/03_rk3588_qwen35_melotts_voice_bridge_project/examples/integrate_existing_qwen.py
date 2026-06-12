import requests

def speak(text: str):
    requests.post("http://127.0.0.1:8010/speak", json={"text": text, "play": True, "split": True}, timeout=180).raise_for_status()

def qwen_generate(prompt: str) -> str:
    # TODO: 替换为你的 Qwen3.5-2B 生成函数
    return "这是示例回答。"

if __name__ == "__main__":
    user_text = input("用户：")
    answer = qwen_generate(user_text)
    print("助手：", answer)
    speak(answer)
