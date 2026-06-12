# 故障排查

## Qwen API 不通
运行 `bash scripts/01_check_qwen_api.sh`，确认 `QWEN_API_BASE` 是否包含 `/v1`。

## TTS API 不通
先启动第二个工程的 `scripts/05_start_api.sh`。

## 播报了思考内容
修改 `app/text_cleaner.py` 的清理规则。

## 卡顿
确保 TTS 服务串行执行，降低 `MAX_SENTENCE_CHARS`。
