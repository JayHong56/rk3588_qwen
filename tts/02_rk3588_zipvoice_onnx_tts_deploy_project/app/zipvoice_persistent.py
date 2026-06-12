import json
import os
import threading
import time
from pathlib import Path

import torch
from lhotse.utils import fix_random_seed

from zipvoice.bin.infer_zipvoice import get_vocoder
from zipvoice.bin.infer_zipvoice_onnx import (
    EmiliaTokenizer,
    EspeakTokenizer,
    LibriTTSTokenizer,
    OnnxModel,
    SimpleTokenizer,
    VocosFbank,
    generate_sentence,
)


class PersistentZipVoiceOnnx:
    def __init__(self):
        self.lock = threading.Lock()
        self.model_dir = Path(os.environ["ZIPVOICE_MODEL_DIR"])
        self.onnx_int8 = os.environ.get("ZIPVOICE_ONNX_INT8", "true").lower() in ("1", "true", "yes", "on")
        self.num_thread = int(os.environ.get("ZIPVOICE_NUM_THREAD", "4"))
        self.tokenizer_name = os.environ.get("ZIPVOICE_TOKENIZER", "emilia")
        self.lang = os.environ.get("ZIPVOICE_LANG", "zh")
        self.vocoder_path = os.environ.get("ZIPVOICE_VOCODER_PATH") or None
        self.num_step = int(os.environ.get("ZIPVOICE_NUM_STEP", "4"))
        self.guidance_scale = float(os.environ.get("ZIPVOICE_GUIDANCE_SCALE", "3.0"))
        self.t_shift = float(os.environ.get("ZIPVOICE_T_SHIFT", "0.5"))
        self.target_rms = float(os.environ.get("ZIPVOICE_TARGET_RMS", "0.1"))
        self.feat_scale = float(os.environ.get("ZIPVOICE_FEAT_SCALE", "0.1"))
        self.remove_long_sil = os.environ.get("ZIPVOICE_REMOVE_LONG_SIL", "true").lower() in ("1", "true", "yes", "on")

        if not self.model_dir.is_dir():
            raise FileNotFoundError(f"ZIPVOICE_MODEL_DIR not found: {self.model_dir}")

        text_encoder = "text_encoder_int8.onnx" if self.onnx_int8 else "text_encoder.onnx"
        fm_decoder = "fm_decoder_int8.onnx" if self.onnx_int8 else "fm_decoder.onnx"
        self.text_encoder_path = self.model_dir / text_encoder
        self.fm_decoder_path = self.model_dir / fm_decoder
        self.model_config_path = self.model_dir / "model.json"
        self.token_file = self.model_dir / "tokens.txt"

        for p in [self.text_encoder_path, self.fm_decoder_path, self.model_config_path, self.token_file]:
            if not p.is_file():
                raise FileNotFoundError(p)

        torch.set_num_threads(self.num_thread)
        torch.set_num_interop_threads(self.num_thread)
        fix_random_seed(int(os.environ.get("ZIPVOICE_SEED", "666")))

        t0 = time.perf_counter()
        self.tokenizer = self._create_tokenizer()
        with self.model_config_path.open("r") as f:
            self.model_config = json.load(f)
        self.model = OnnxModel(str(self.text_encoder_path), str(self.fm_decoder_path), num_thread=self.num_thread)
        self.vocoder = get_vocoder(self.vocoder_path)
        self.vocoder.eval()
        if self.model_config["feature"]["type"] != "vocos":
            raise NotImplementedError(f"Unsupported feature type: {self.model_config['feature']['type']}")
        self.feature_extractor = VocosFbank()
        self.sampling_rate = int(self.model_config["feature"]["sampling_rate"])
        self.load_elapsed_s = time.perf_counter() - t0

    def _create_tokenizer(self):
        if self.tokenizer_name == "emilia":
            return EmiliaTokenizer(token_file=self.token_file)
        if self.tokenizer_name == "libritts":
            return LibriTTSTokenizer(token_file=self.token_file)
        if self.tokenizer_name == "espeak":
            return EspeakTokenizer(token_file=self.token_file, lang=self.lang)
        if self.tokenizer_name == "simple":
            return SimpleTokenizer(token_file=self.token_file)
        raise ValueError(f"unsupported tokenizer: {self.tokenizer_name}")

    def synthesize(self, text, output, prompt_wav, prompt_text, speed=None):
        text = (text or "").strip()
        if not text:
            raise ValueError("empty text")
        if not prompt_wav or not Path(prompt_wav).exists():
            raise FileNotFoundError(f"prompt wav not found: {prompt_wav}")
        if not prompt_text:
            raise ValueError("empty prompt text")

        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        speed = float(os.environ.get("ZIPVOICE_SPEED", "1.0")) if speed is None else float(speed)

        with self.lock:
            wall_t0 = time.perf_counter()
            metrics = generate_sentence(
                save_path=str(output),
                prompt_text=prompt_text,
                prompt_wav=prompt_wav,
                text=text,
                model=self.model,
                vocoder=self.vocoder,
                tokenizer=self.tokenizer,
                feature_extractor=self.feature_extractor,
                num_step=self.num_step,
                guidance_scale=self.guidance_scale,
                speed=speed,
                t_shift=self.t_shift,
                target_rms=self.target_rms,
                feat_scale=self.feat_scale,
                sampling_rate=self.sampling_rate,
                remove_long_sil=self.remove_long_sil,
            )
            wall = time.perf_counter() - wall_t0

        return {
            "ok": True,
            "output": str(output),
            "duration_sec": metrics["wav_seconds"],
            "elapsed_sec": wall,
            "model_elapsed_sec": metrics["t"],
            "model_no_vocoder_sec": metrics["t_no_vocoder"],
            "vocoder_sec": metrics["t_vocoder"],
            "rtf": wall / max(metrics["wav_seconds"], 1e-6),
            "model_rtf": metrics["rtf"],
            "load_elapsed_s": self.load_elapsed_s,
            "backend": "persistent",
        }
