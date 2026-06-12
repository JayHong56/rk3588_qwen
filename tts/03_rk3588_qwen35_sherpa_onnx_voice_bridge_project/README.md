# 03 RK3588：Qwen3.5-2B + sherpa-onnx 语音播报桥接工程

把已部署的 Qwen3.5-2B 接入 sherpa-onnx TTS，实现语言播报。

## 架构

```text
用户输入 -> Qwen3.5-2B -> 流式 token -> 文本清洗 -> 按句切分 -> sherpa-onnx TTS API -> wav -> aplay
```

默认端口：Qwen `8000/v1`，TTS `8011`，桥接 API `8021`。

## 部署

```bash
unzip 03_rk3588_qwen35_sherpa_onnx_voice_bridge_project.zip
cd 03_rk3588_qwen35_sherpa_onnx_voice_bridge_project
cp config/voice_bridge.env.example config/voice_bridge.env
bash scripts/00_install_deps.sh
source .venv/bin/activate
bash scripts/02_check_qwen_api.sh
bash scripts/03_check_tts_api.sh
bash scripts/04_run_voice_chat.sh "请用三句话介绍 RK3588。"
```

## 启动桥接 API

```bash
bash scripts/05_start_bridge_api.sh
curl -X POST http://127.0.0.1:8021/chat_speak   -H 'Content-Type: application/json'   -d '{"prompt":"请介绍一下你自己。","speak":true}'
```

## 可选下载资产

如果你还没把模型放到板端，可设置：

```bash
DOWNLOAD_QWEN=true
DOWNLOAD_SHERPA_TTS=true
bash scripts/01_download_optional_assets.sh
```

注意：这个脚本只下载 Qwen HF 权重和 sherpa TTS ONNX 资产，不负责 Qwen -> RKLLM 转换；Qwen 转换请用 01 PC 工程。

## 已支持 Qwen 后端

- `openai`：OpenAI-compatible `/v1/chat/completions`；推荐。
- `command`：调用本地 CLI，例如 `/home/rock/qwen35/run_qwen.sh prompt`。
- `dummy`：不用 Qwen，只验证 TTS 链路。
