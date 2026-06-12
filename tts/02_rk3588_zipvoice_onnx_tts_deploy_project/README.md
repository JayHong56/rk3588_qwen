# RK3588 ZipVoice ONNX TTS

This service exposes ZipVoice ONNX with a sherpa-compatible HTTP API:

- `GET /health`
- `POST /synthesize`
- `POST /speak`

## 1. Install

```bash
cd /home/linaro/Qwen/tts/02_rk3588_zipvoice_onnx_tts_deploy_project
bash scripts/00_install_env.sh
```

If Hugging Face download is slow:

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

## 2. Prepare voice prompt

Create a short clean prompt wav, preferably 1-3 seconds:

```text
/home/linaro/Qwen/voice_prompts/speaker1.wav
```

Edit:

```bash
nano config/zipvoice.env
```

Set:

```bash
ZIPVOICE_PROMPT_WAV=/home/linaro/Qwen/voice_prompts/speaker1.wav
ZIPVOICE_PROMPT_TEXT=参考音频里逐字对应的文本
```

## 3. Test once

```bash
bash scripts/01_check_prompt.sh
bash scripts/02_run_once.sh "你好，这是 ZipVoice ONNX 测试。" output/test.wav
aplay output/test.wav
```

## 4. Start API

```bash
bash scripts/03_start_api.sh
```

Test:

```bash
curl -X POST http://127.0.0.1:8012/speak \
  -H 'Content-Type: application/json' \
  -d '{"text":"你好，这是 ZipVoice HTTP 服务测试。","play":true}'
```

## 5. Connect Qwen bridge

Set in the Qwen sherpa bridge environment:

```bash
TTS_API_BASE=http://127.0.0.1:8012
```

Then run existing scripts.
