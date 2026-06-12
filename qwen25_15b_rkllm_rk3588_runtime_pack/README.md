# RK3588 端工程包：Qwen2.5-1.5B-Instruct RKLLM/NPU Runtime

用途：在 RK3588 板端安装 PC 端导出的 `.rkllm` 模型和官方 `demo_Linux_aarch64` 运行文件，完成 NPU 自检、运行测试、日志查看和可选 HTTP bridge。

> 本包不包含 `.rkllm` 模型、不包含 `librkllmrt.so`。这些应由 PC 端工程包的 `make export && make build-demo && make bundle` 产生。

## 目录结构

```text
.
├── .env.example
├── README.md
├── scripts/
│   ├── 00_check_board.sh
│   ├── 01_install_deps.sh
│   ├── 02_install_app.sh
│   ├── 03_run_demo.sh
│   ├── 04_fix_freq_wrapper.sh
│   ├── 05_install_systemd_cli.sh
│   ├── 06_logs.sh
│   └── 07_install_bridge_service.sh
├── systemd/
│   ├── qwen25-rkllm-cli.service.template
│   └── qwen25-rkllm-bridge.service.template
└── bridge/
    ├── requirements.txt
    ├── demo_bridge_api.py
    └── run_bridge.sh
```

## 快速使用

假设你已经从 PC 端拿到：

```text
rk3588_qwen25_runtime_bundle.tar.gz
```

在 RK3588 上：

```bash
mkdir -p ~/rkllm_qwen25
cp rk3588_qwen25_runtime_bundle.tar.gz ~/rkllm_qwen25/
cd ~/rkllm_qwen25
tar -xzf rk3588_qwen25_runtime_bundle.tar.gz --strip-components=1

# 再把本 runtime_pack 解压/复制到同一目录，或直接复制 scripts/systemd/bridge 进来
unzip qwen25_15b_rkllm_rk3588_runtime_pack.zip
cp -a qwen25_15b_rkllm_rk3588_runtime_pack/. .

cp .env.example .env
vim .env

bash scripts/00_check_board.sh
bash scripts/01_install_deps.sh
bash scripts/04_fix_freq_wrapper.sh
bash scripts/03_run_demo.sh
```

## 默认运行命令

```bash
export LD_LIBRARY_PATH=./lib:$LD_LIBRARY_PATH
export RKLLM_LOG_LEVEL=1
./llm_demo ./Qwen2.5-1.5B-Instruct_W8A8_RK3588.rkllm 128 4096
```

## 说明

- `llm_demo` 是交互式程序，适合先验证 NPU 推理。
- `scripts/05_install_systemd_cli.sh` 只适合自检场景，因为官方 demo 本身是 stdin 交互程序。
- 需要临时 HTTP 测试时，先执行 `scripts/02_install_app.sh`，再执行 `scripts/07_install_bridge_service.sh`，接口为 `POST /chat`。
- 产品化建议改造成 C/C++ 常驻服务，初始化 RKLLM 一次后通过 HTTP/Unix Socket 接收请求。
- `bridge/demo_bridge_api.py` 是为了快速把交互式 demo 包成 HTTP 测试接口，不建议作为最终生产服务。

## HTTP bridge 临时测试

安装服务后：

```bash
sudo systemctl start qwen25-rkllm-bridge
curl -s http://127.0.0.1:18080/health
curl -s http://127.0.0.1:18080/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"我今天有点累"}'
```

这个 bridge 通过 `pexpect` 驱动官方交互式 demo，只用于验证链路。正式语音陪聊建议直接基于 RKLLM C/C++ API 写常驻服务。
