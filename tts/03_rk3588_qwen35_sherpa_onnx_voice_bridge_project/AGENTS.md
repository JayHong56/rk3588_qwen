# AGENTS.md

本工程用于 RK3588 上 Qwen3.5-2B + sherpa-onnx TTS 语音播报。

## 工具链边界

- sherpa-onnx TTS 使用 ONNX / ONNX Runtime，不使用 RKLLM-Toolkit 转换。
- RKLLM-Toolkit 只用于 Qwen/Llama/Phi/Gemma 等 LLM 转 `.rkllm`。
- 如果要把普通 ONNX 转 Rockchip NPU，应看 RKNN-Toolkit2，不是 RKLLM-Toolkit。
- 默认让 Qwen 占用 RK3588 NPU，sherpa-onnx TTS 走 CPU，避免资源抢占。
- 模型权重不直接放进工程包，统一用脚本下载并保留上游来源。

## 修改要求

1. 修改脚本后先跑对应 `scripts/00_*check*.sh` 或健康检查。
2. TTS 服务必须先单句生成 wav，再启动 HTTP API。
3. 桥接服务必须支持 OpenAI-compatible Qwen API，也保留 command/dummy 模式。
4. 长文本必须按句切分，不能逐 token 调 TTS。
