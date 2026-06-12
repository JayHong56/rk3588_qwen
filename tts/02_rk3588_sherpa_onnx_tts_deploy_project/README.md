# 02 RK3588 板端：sherpa-onnx TTS 部署工程

本工程在 RK3588 上部署 sherpa-onnx TTS：离线合成、HTTP API、systemd 服务、benchmark。

默认模型：`vits-melo-tts-zh_en`。默认端口：`8011`。

## 快速部署

```bash
unzip 02_rk3588_sherpa_onnx_tts_deploy_project.zip
cd 02_rk3588_sherpa_onnx_tts_deploy_project
cp config/sherpa_tts.env.example config/sherpa_tts.env
bash scripts/00_check_board.sh
bash scripts/01_install_env.sh
source .venv/bin/activate
bash scripts/02_download_tts_model.sh
bash scripts/03_verify_tts_model.sh
bash scripts/04_run_once.sh "你好，这是 RK3588 上的 sherpa-onnx TTS 测试。" output/test.wav
aplay output/test.wav
bash scripts/05_start_api.sh
```

## API

健康检查：

```bash
curl http://127.0.0.1:8011/health
```

合成并播放：

```bash
curl -X POST http://127.0.0.1:8011/speak   -H 'Content-Type: application/json'   -d '{"text":"你好，本地语音播报服务已经启动。","play":true}'
```

只合成 wav：

```bash
curl -X POST http://127.0.0.1:8011/synthesize   -H 'Content-Type: application/json'   -d '{"text":"你好。","output":"output/api.wav"}'
```

## systemd

```bash
bash scripts/06_install_systemd.sh
sudo systemctl status sherpa-onnx-tts --no-pager
```

## 生产建议

- `SHERPA_NUM_THREADS=2~4`；线程太多可能影响 Qwen。
- Qwen 占 NPU，TTS 走 CPU，系统更稳。
- 音频无声先检查 `aplay -l` 和 `AUDIO_DEVICE`。
