# RK3588 Qwen3.5-2B + MeloTTS-RKNN2 语音播报桥接工程

本工程用于把已经部署在 RK3588 上的 Qwen3.5-2B 接入 MeloTTS-RKNN2，实现：

```text
用户输入
  -> Qwen3.5-2B 文本生成
  -> 流式句子切分
  -> MeloTTS-RKNN2 合成 wav
  -> RK3588 本地播放
```

## 特性

- 支持 OpenAI-compatible `/v1/chat/completions`；
- 支持命令行 Qwen 程序；
- 支持流式 token 切句播报；
- 自动清理 Markdown、URL、代码块、`<think>...</think>`；
- 可作为 CLI 使用，也可作为 HTTP 桥接服务使用；
- 可安装 systemd 服务。

## 快速开始

先启动第二个工程的 TTS 服务：

```bash
cd 02_rk3588_melotts_rknn2_deploy_project
source .venv/bin/activate
bash scripts/05_start_api.sh
```

再启动本工程：

```bash
unzip 03_rk3588_qwen35_melotts_voice_bridge_project.zip
cd 03_rk3588_qwen35_melotts_voice_bridge_project

cp config/voice_bridge.env.example config/voice_bridge.env
nano config/voice_bridge.env

bash scripts/00_install_deps.sh
source .venv/bin/activate

bash scripts/01_check_qwen_api.sh
bash scripts/02_check_tts_api.sh
bash scripts/03_run_voice_chat.sh "请用三句话介绍 RK3588。"
```

## OpenAI-compatible Qwen 配置

```bash
QWEN_BACKEND=openai
QWEN_API_BASE=http://127.0.0.1:8000/v1
QWEN_API_KEY=EMPTY
QWEN_MODEL=qwen3.5-2b
```

## 命令行 Qwen 配置

```bash
QWEN_BACKEND=cmd
QWEN_CMD=/home/rock/qwen/run_qwen.sh
```

要求命令行程序接收最后一个参数作为 prompt，并把回答输出到 stdout。

## 启动桥接 API

```bash
bash scripts/04_start_bridge_api.sh
```

测试：

```bash
curl -X POST http://127.0.0.1:8020/chat_speak \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"请介绍一下你自己。","speak":true}'
```

## 接入已有 Qwen 主程序

最小改动：

```python
import requests

answer = qwen_generate(user_text)
print(answer)
requests.post(
    "http://127.0.0.1:8010/speak",
    json={"text": answer, "play": True, "split": True},
    timeout=180,
)
```

更好的方式是流式切句，参考 `examples/streaming_hook_example.py`。
