import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import onnxruntime as ort
import soundfile
from rknnlite.api import RKNNLite


@dataclass
class PersistentMeloTTSConfig:
    root: Path
    sample_rate: int = 44100
    speed: float = 0.8
    output_dir: Path = Path("output")
    encoder: str = "encoder.onnx"
    decoder: str = "decoder.rknn"
    lexicon: str = "lexicon.txt"
    token: str = "tokens.txt"


class PersistentMeloTTS:
    def __init__(self, cfg: PersistentMeloTTSConfig):
        self.cfg = cfg
        self.root = Path(cfg.root).resolve()
        self.output_dir = Path(cfg.output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        required = [
            cfg.encoder,
            cfg.decoder,
            "g.bin",
            cfg.lexicon,
            cfg.token,
            "melotts_rknn.py",
        ]
        missing = [name for name in required if not (self.root / name).exists()]
        if missing:
            raise FileNotFoundError(f"缺少 MeloTTS-RKNN2 文件: {missing}, root={self.root}")

        sys.path.insert(0, str(self.root))
        from melotts_rknn import (
            audio_numpy_concat,
            decode_long_word,
            generate_decode_slices,
            generate_pronounce_slice,
            generate_word_pron_num,
            merge_sub_audio,
        )
        from utils import Lexicon, intersperse, split_sentences_zh

        self.audio_numpy_concat = audio_numpy_concat
        self.decode_long_word = decode_long_word
        self.generate_decode_slices = generate_decode_slices
        self.generate_pronounce_slice = generate_pronounce_slice
        self.generate_word_pron_num = generate_word_pron_num
        self.merge_sub_audio = merge_sub_audio
        self.intersperse = intersperse
        self.split_sentences_zh = split_sentences_zh

        t0 = time.perf_counter()
        self.lexicon = Lexicon(str(self.root / cfg.lexicon), str(self.root / cfg.token))
        self.encoder = ort.InferenceSession(
            str(self.root / cfg.encoder),
            providers=["CPUExecutionProvider"],
            sess_options=ort.SessionOptions(),
        )

        self.decoder = RKNNLite()
        ret = self.decoder.load_rknn(str(self.root / cfg.decoder))
        if ret != 0:
            raise RuntimeError(f"Load decoder RKNN model failed: {ret}")

        ret = self.decoder.init_runtime()
        if ret != 0:
            raise RuntimeError(f"Init RKNN runtime failed: {ret}")

        self.g = np.fromfile(str(self.root / "g.bin"), dtype=np.float32).reshape(1, 256, 1)
        self.dec_len = 65536 // 512
        self.load_time_s = time.perf_counter() - t0
        print(f"[PersistentMeloTTS] loaded in {self.load_time_s:.3f}s", flush=True)

    def close(self):
        if getattr(self, "decoder", None) is not None:
            self.decoder.release()
            self.decoder = None

    def synthesize(self, text: str, out_wav: Optional[str] = None, speed: Optional[float] = None) -> str:
        speed = speed if speed is not None else self.cfg.speed
        sample_rate = self.cfg.sample_rate
        out = Path(out_wav).resolve() if out_wav else self.output_dir / f"melotts_{int(time.time() * 1000)}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)

        total_t0 = time.perf_counter()
        sens = self.split_sentences_zh(text)
        audio_list = []
        encoder_total = 0.0
        decoder_total = 0.0

        for sent_index, sentence in enumerate(sens):
            phone_str, yinjie_num, phones, tones = self.lexicon.convert(sentence)
            phone_str = self.intersperse(phone_str, 0)
            phones = np.array(self.intersperse(phones, 0), dtype=np.int32)
            tones = np.array(self.intersperse(tones, 0), dtype=np.int32)
            yinjie_num = np.array(yinjie_num, dtype=np.int32) * 2
            yinjie_num[0] += 1

            pron_slices = self.generate_pronounce_slice(yinjie_num)
            phone_len = phones.shape[-1]
            language = np.array([3] * phone_len, dtype=np.int32)

            t0 = time.perf_counter()
            z_p, pronoun_lens, audio_len = self.encoder.run(
                None,
                input_feed={
                    "phone": phones,
                    "g": self.g,
                    "tone": tones,
                    "language": language,
                    "noise_scale": np.array([0], dtype=np.float32),
                    "length_scale": np.array([1.0 / speed], dtype=np.float32),
                    "noise_scale_w": np.array([0], dtype=np.float32),
                    "sdp_ratio": np.array([0], dtype=np.float32),
                },
            )
            encoder_total += time.perf_counter() - t0

            audio_len = audio_len[0]
            actual_size = z_p.shape[-1]
            dec_slice_num = int(np.ceil(actual_size / self.dec_len))
            z_p = np.pad(
                z_p,
                pad_width=((0, 0), (0, 0), (0, dec_slice_num * self.dec_len - actual_size)),
                mode="constant",
                constant_values=0,
            )

            pron_num = self.generate_word_pron_num(pronoun_lens, pron_slices)
            pron_num_slices, zp_slices, strip_flags, pron_lens, is_long = self.generate_decode_slices(
                pron_num,
                self.dec_len,
            )

            sub_audio_list = []
            for slice_index in range(len(pron_num_slices)):
                pron_start, pron_end = pron_num_slices[slice_index]
                zp_start, zp_end = zp_slices[slice_index]

                if is_long[slice_index]:
                    t0 = time.perf_counter()
                    sub_audio_list.extend(
                        self.decode_long_word(
                            self.decoder,
                            z_p[..., zp_start:zp_end],
                            self.g,
                            self.dec_len,
                        )
                    )
                    decoder_total += time.perf_counter() - t0
                else:
                    sub_dec_len = zp_end - zp_start
                    sub_audio_len = 512 * sub_dec_len
                    zp_slice = z_p[..., zp_start:zp_end]

                    if zp_slice.shape[-1] < self.dec_len:
                        zp_slice = np.concatenate(
                            (
                                zp_slice,
                                np.zeros(
                                    (*zp_slice.shape[:-1], self.dec_len - zp_slice.shape[-1]),
                                    dtype=np.float32,
                                ),
                            ),
                            axis=-1,
                        )

                    t0 = time.perf_counter()
                    outputs = self.decoder.inference(inputs=[zp_slice, self.g])
                    decoder_total += time.perf_counter() - t0

                    audio = outputs[0].flatten()
                    audio = audio[:sub_audio_len]

                    if strip_flags[slice_index][0]:
                        head = 512 * pron_num[pron_start]
                        audio = audio[head:]

                    if strip_flags[slice_index][1]:
                        tail = 512 * pron_num[pron_end - 1]
                        audio = audio[:-tail]

                    sub_audio_list.append(audio)

            sub_audio = self.merge_sub_audio(sub_audio_list, 0, audio_len)
            audio_list.append(sub_audio)

        audio = self.audio_numpy_concat(audio_list, sr=sample_rate, speed=speed)
        soundfile.write(str(out), audio, sample_rate)

        elapsed = time.perf_counter() - total_t0
        print(
            "[PersistentMeloTTS] synth "
            f"chars={len(text)} sentences={len(sens)} "
            f"encoder={encoder_total:.3f}s decoder={decoder_total:.3f}s total={elapsed:.3f}s "
            f"wav={out}",
            flush=True,
        )
        return str(out)
