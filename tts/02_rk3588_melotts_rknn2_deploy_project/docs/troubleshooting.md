# 排错

## `Load decoder RKNN model failed`
检查 `decoder.rknn`、NPU 驱动、`rknn-toolkit-lite2` 和 `/dev/rknpu*` 权限。

## 没声音
运行 `aplay -l` 和 `aplay output/test.wav`；必要时运行 `scripts/08_fix_audio_permissions.sh`。

## 首句慢
上游脚本每次会加载模型。验证阶段可接受，产品化建议改成模型常驻内存。
