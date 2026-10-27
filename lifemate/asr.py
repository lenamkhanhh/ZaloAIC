"""ASR backends — lazy imports, so missing models never break imports.

- ``TransformersASR``: original PhoWhisper weights, recommended default.
- ``FasterWhisperASR``: optional explicitly converted local CT2 checkpoint.
- ``TranscriptOracle``: returns the train ``audio_text`` verbatim.
  TRAIN-ONLY, for pipeline mechanics and for measuring the LLM/agent
  in isolation from ASR error. It is NEVER a substitute for ASR on
  public/private data (where no audio_text exists) and any score
  measured with it must be labelled "oracle-transcript", not an ASR
  baseline. Importing or using it on a public_test sample raises.
"""
from __future__ import annotations

from pathlib import Path


class FasterWhisperASR:
    def __init__(self, checkpoint: str = "vinai/PhoWhisper-small", device: str = "cuda", compute_type: str = "float16"):
        if not (Path(checkpoint) / "model.bin").is_file():
            raise ValueError(
                "faster-whisper requires a local converted CTranslate2 directory "
                "containing model.bin. Convert the checkpoint first or use "
                "asr_backend=transformers for the original PhoWhisper weights."
            )
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Install it for the GPU/Kaggle "
                "run (see RUN_LIFEMATE.md §3); it is not installed on the CPU-only "
                "dev VM, where ASR runs are out of scope."
            ) from exc
        self.model = WhisperModel(checkpoint, device=device, compute_type=compute_type)

    def transcribe(self, wav_path: str | Path) -> str:
        segments, _info = self.model.transcribe(str(wav_path), language="vi", beam_size=1)
        return "".join(s.text for s in segments).strip()


class TransformersASR:
    """Original PhoWhisper checkpoint; no CTranslate2 conversion required."""

    def __init__(self, checkpoint: str, device: str = "cuda", local_files_only: bool = True):
        try:
            import torch
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
        except (ImportError, RuntimeError) as exc:
            raise RuntimeError(
                "Cannot import Transformers ASR dependencies. Use an isolated environment "
                "with compatible torch/transformers and optional torchvision builds; "
                "see VALIDATION_LIFEMATE.md. No automatic backend fallback was attempted."
            ) from exc

        processor = AutoProcessor.from_pretrained(checkpoint, local_files_only=local_files_only)
        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            checkpoint, torch_dtype=dtype, local_files_only=local_files_only,
        )
        self.pipeline = pipeline(
            "automatic-speech-recognition", model=model,
            tokenizer=processor.tokenizer, feature_extractor=processor.feature_extractor,
            device=device, chunk_length_s=30,
        )

    def transcribe(self, wav_path: str | Path) -> str:
        # Read PCM locally: no ffmpeg executable or online decoder required.
        import wave
        import numpy as np

        with wave.open(str(wav_path), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
                raise ValueError("ASR expects mono 16-bit PCM WAV at 16 kHz")
            audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        result = self.pipeline(
            {"array": audio, "sampling_rate": 16000},
            generate_kwargs={"language": "vi", "task": "transcribe", "num_beams": 1, "do_sample": False},
        )
        return result["text"].strip()


def build_asr(config, device: str = "cuda"):
    if config.asr_backend == "transformers":
        return TransformersASR(config.asr_checkpoint, device, local_files_only=config.local_files_only)
    if config.asr_backend == "faster-whisper":
        return FasterWhisperASR(config.asr_checkpoint, device=device,
                                compute_type="float16" if device.startswith("cuda") else "float32")
    raise ValueError(f"Unknown ASR backend: {config.asr_backend!r}")


class TranscriptOracle:
    """Train-only transcript source (see module docstring warning)."""

    def __init__(self, samples_by_id: dict):
        self._by_id = samples_by_id

    def transcribe_for(self, sample_id: str) -> str:
        sample = self._by_id.get(sample_id)
        if sample is None or sample.split != "train" or sample.audio_text is None:
            raise ValueError(
                f"TranscriptOracle is train-only; no transcript for {sample_id!r}. "
                "Public/private samples must go through real ASR."
            )
        return sample.audio_text
