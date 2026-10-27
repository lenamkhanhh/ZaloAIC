# LifeMate dev5 GPU smoke

Run `python kaggle/lifemate_smoke/build_notebook.py` to regenerate the notebook.
The notebook is self-contained; Kaggle does not need the sidecar Python files.

- Private kernel, fixed 5 dev IDs, source commit a9d48d2, seed 42.
- Recommended pipeline, PhoWhisper-small + Qwen3-4B. Transformers backend;
  this is not an ASR/LLM comparison, training run or heldout evaluation.
- All history user audio is transcribed, even though dev history includes gold
  transcripts. Gold transcripts/calls are diagnostic outputs only.
- Setup downloads the SHA-verified official ZIP and pinned public model weights.
  Data/source live under /kaggle/temp; outputs contain no weights/data archive.
- Existing torch is preserved. Optional torchvision is removed only in this
  disposable Kaggle environment. Package pins are validated against PyPI;
  actual native GPU compatibility must be established by this run.
- No strict 30-second A30 claim. Soft debug budget is 180 seconds/sample at
  generation boundaries; native CUDA calls are not preempted. Kernel run is
  capped at 3600 seconds when pushed.
- On failure, inspect `smoke_artifacts.zip` and phase logs before any rerun.

Version 1 was inspected locally before a controlled retry: both original
models loaded on T4, but 4/5 samples failed with CUDA OOM during long-prompt
attention. No quality result is inferred from that run. Version 2 preserves
FP16 weights, seed and five IDs, and balances LLM layers across the two assigned
T4s (6 GiB weight-placement budget per GPU). This is a smoke placement, not a
claim of fitting or meeting 30 seconds on a single A30. Source/core defaults
still use a single device unless this optional placement is requested.

Launch once (GPU time is consumed):

```text
kaggle kernels push -p kaggle/lifemate_smoke --timeout 3600 --accelerator NvidiaTeslaT4
kaggle kernels status khanhss/lifemate-smoke-dev5-20261027
```

CPU preflight:
`python -m unittest discover -s kaggle/lifemate_smoke -p test_smoke.py`.
