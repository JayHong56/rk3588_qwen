---
license: agpl-3.0
tags:
- rknn
---


# MeloTTS-RKNN2

## (English README see below)

在RK3588上运行MeloTTS文字转语音模型!

- 推理速度(RK3588): 约5倍速
- 内存占用(RK3588): 约0.2GB

## 使用方法

1. 克隆或者下载此仓库到瑞芯微SoC的系统上.
  
2. 安装依赖

```bash
pip install -r requirements.txt
pip install rknn-toolkit-lite2
```

4. 运行
   
```bash
python melotts_rknn.py -s "你想要生成的文本"
```

## 模型转换

1. 安装依赖

```bash
pip install -r requirements.txt
pip install rknn-toolkit2==2.3.0
```

2. 转换模型

```bash
python convert_rknn.py
```

## 已知问题

- 和原项目一样，Encoder部分并没有使用NPU加速，但是耗时不大，应该不会对推理速度有太大影响。

## 参考

- [melotts.axera](https://github.com/ml-inory/melotts.axera)
- [MeloTTS](https://github.com/myshell-ai/MeloTTS)


## English README

# MeloTTS-RKNN2

Run the MeloTTS text-to-speech model on RK3588!

- Inference speed (RK3588): about 5x real-time
- Memory usage (RK3588): about 0.2GB

## Usage

1. Clone or download this repository to your Rockchip SoC system.
  
2. Install dependencies

```bash
pip install -r requirements.txt
pip install rknn-toolkit-lite2
```

3. Run
   
```bash
python melotts_rknn.py -s "The text you want to generate."
```

## Model Conversion

1. Install dependencies

```bash
pip install -r requirements.txt
pip install rknn-toolkit2==2.3.0
```

2. Convert the model

```bash
python convert_rknn.py
```

## Known Issues

- Same as the original project, the Encoder part is not accelerated by the NPU. However, its processing time is short and should not significantly affect the inference speed.

## References

- [melotts.axera](https://github.com/ml-inory/melotts.axera)
- [MeloTTS](https://github.com/myshell-ai/MeloTTS)
