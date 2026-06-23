#!/usr/bin/env python3
import argparse
import soundfile as sf
import sherpa_onnx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", required=True)
    parser.add_argument(
        "--model-dir",
        default="/home/linaro/Qwen/asr/models/sherpa-onnx-paraformer-zh-2024-03-09",
    )
    parser.add_argument("--num-threads", type=int, default=4)
    args = parser.parse_args()

    tokens = f"{args.model_dir}/tokens.txt"
    paraformer = f"{args.model_dir}/model.int8.onnx"

    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        tokens=tokens,
        paraformer=paraformer,
        num_threads=args.num_threads,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        debug=False,
    )

    samples, sample_rate = sf.read(args.wav, dtype="float32")

    if samples.ndim == 2:
        samples = samples[:, 0]

    if sample_rate != 16000:
        raise RuntimeError(f"wav 采样率是 {sample_rate}，需要 16000 Hz")

    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    recognizer.decode_stream(stream)

    print(stream.result.text)


if __name__ == "__main__":
    main()



