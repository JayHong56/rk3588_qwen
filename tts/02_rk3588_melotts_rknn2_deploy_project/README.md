# RK3588 板端 MeloTTS-RKNN2 部署工程

本工程用于在 RK3588 上部署 MeloTTS-RKNN2，提供：

- 板卡/NPU/音频检查；
- Python 虚拟环境安装；
- 模型资产下载或导入；
- 命令行合成 wav；
- FastAPI HTTP TTS 服务；
- systemd 后台服务；
- benchmark 与故障排查。

## 目录

```text
02_rk3588_melotts_rknn2_deploy_project/
├── README.md
├── requirements-rk3588.txt
├── config/melotts.env.example
├── app/
│   ├── audio_player.py
│   ├── melotts_subprocess.py
│   ├── sentence_splitter.py
│   ├── text_normalizer.py
│   ├── tts_api.py
│   └── tts_cli.py
├── scripts/
│   ├── 00_check_board.sh
│   ├── 01_install_env.sh
│   ├── 02_download_assets.py
│   ├── 03_install_upstream_deps.sh
│   ├── 04_run_once.sh
│   ├── 05_start_api.sh
│   ├── 06_install_systemd.sh
│   ├── 07_benchmark.sh
│   └── 08_fix_audio_permissions.sh
├── systemd/melotts-rknn2.service
└── tools/benchmark.py
```

## 快速开始

```bash
unzip 02_rk3588_melotts_rknn2_deploy_project.zip
cd 02_rk3588_melotts_rknn2_deploy_project

cp config/melotts.env.example config/melotts.env
nano config/melotts.env

bash scripts/00_check_board.sh
bash scripts/01_install_env.sh
source .venv/bin/activate

# 方式 A：板端直接下载
python scripts/02_download_assets.py --local-dir /home/rock/MeloTTS-RKNN2

# 方式 B：使用 PC 端打包出的 runtime 目录，拷贝到 /home/rock/MeloTTS-RKNN2

bash scripts/03_install_upstream_deps.sh /home/rock/MeloTTS-RKNN2
bash scripts/04_run_once.sh "你好，这是 RK3588 上的 MeloTTS-RKNN2 测试。" output/test.wav
aplay output/test.wav
```

## 启动 HTTP 服务

```bash
bash scripts/05_start_api.sh
```

测试：

```bash
curl -X POST http://127.0.0.1:8010/synthesize \
  -H 'Content-Type: application/json' \
  -d '{"text":"你好，本地 TTS 服务已经启动。","play":true}'
```

## API

- `GET /health`
- `POST /synthesize`
- `POST /speak`

## 部署建议

初期使用 subprocess 调用上游 `melotts_rknn.py`，稳定优先。若后续首包延迟过高，再改造成模型常驻内存的服务。
