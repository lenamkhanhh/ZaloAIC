"""ASR backends — lazy imports, so missing models never break imports.

- ``FasterWhisperASR``: vinai/PhoWhisper-small by default via
  faster-whisper (CTranslate2), greedy decoding, language="vi". This
  is the recommended ASR: 0.244B params, well inside the 6B budget.
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
