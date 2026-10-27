# LifeMate dev5 GPU smoke

Run `python kaggle/lifemate_smoke/build_notebook.py` to regenerate the notebook.
The notebook is self-contained; Kaggle does not need the sidecar Python files.

- Private kernel, fixed 5 dev IDs, source commit a9d48d2, seed 42.
- Recommended pipeline, PhoWhisper-small + Qwen3-4B. Transformers backend;
  this is not an ASR/LLM comparison, training run or heldout evaluation.
- All history user audio is transcribed, even though dev history includes gold
  transcripts. Gold transcripts/calls are diagnostic outputs only.
- Setup mounts the exact SHA-verified official ZIP and pinned source archive
  from private dataset `khanhss/lifemate-runtime-inputs-20261028/1`.
  Missing/mismatched inputs stop immediately; there is no data/source network
  fallback. Only package/model setup uses the network.
  Data/source live under /kaggle/temp; outputs contain no weights/data archive.
- Existing torch is preserved. Optional torchvision is removed only in this
  disposable Kaggle environment. Package pins are validated against PyPI;
  actual native GPU compatibility must be established by this run.
- No strict 30-second A30 claim. Soft debug budget is 180 seconds/sample at
  generation boundaries; native CUDA calls are not preempted. Kernel run is
  capped at 1200 seconds in the repaired paired launch.
- On failure, inspect `smoke_artifacts.zip` and phase logs before any rerun.

Version 1 was inspected locally before a controlled retry: both original
models loaded on T4, but 4/5 samples failed with CUDA OOM during long-prompt
attention. No quality result is inferred from that run. Version 2 preserves
FP16 weights, seed and five IDs, and balances LLM layers across the two assigned
T4s (6 GiB weight-placement budget per GPU). This is a smoke placement, not a
claim of fitting or meeting 30 seconds on a single A30. Source/core defaults
still use a single device unless this optional placement is requested.

Version 2 also hit attention OOM on 4/5 samples despite confirmed sharding.
Version 3 keeps that placement and uses HF's explicit repeat_kv path with
PyTorch EFFICIENT_ATTENTION for LLM generation only. Native SDPA GQA supports
Flash/math, so automatic selection can use quadratic math attention on T4.
This override is scoped to each generation and requires transformers 4.57.6;
it is not a core pipeline default. Numerical kernel differences may affect
greedy outputs even though the weights, prompt, seed and token limits match.
Before downloading data/weights, both GPUs must pass tiny GQA-reference
parity and 8192-token Qwen-shaped prefill/decode using the actual HF helper.
Unsupported efficient kernels fail immediately, with no math fallback.
The preflight restores RNG state before model loading.

Launch once (GPU time is consumed):

```text
kaggle kernels push -p kaggle/lifemate_smoke --timeout 1200 --accelerator NvidiaTeslaT4
kaggle kernels status khanhss/lifemate-smoke-dev5-20261027
```

CPU preflight:
`python -m unittest discover -s kaggle/lifemate_smoke -p test_smoke.py`.

## Paired current-transcript diagnostic

The optional builder flags `--paired-inputs <local-json> --output-dir <artifact-directory>`
create a private diagnostic notebook outside the source tree. Its input JSON
contains the five cached v3 current/history ASR transcripts and the initial
prompt SHA256 for each ID. Do not commit those data-derived inputs/notebooks.
The ordinary notebook remains a live-ASR five-sample smoke.

The diagnostic runs ten trials: each fixed dev ID with cached ASR current text
and with gold current text from the verified train data. Both arms use exactly
the cached v3 ASR history, the same prompt/model settings, fresh ToolEnv, and
the same efficient-attention kernel. Cached-ASR initial prompt hashes must
match v3. This measures the effect of replacing the current transcript only;
it does not remove history-ASR errors or represent a deployable pipeline.
ASR stays resident for matching placement but is not called; timings exclude
ASR. Separate per-arm submission files avoid duplicate IDs within a file;
per-arm proxy means remain diagnostic, not official scores.

## V5 data-transfer stall and mounted-input recovery

Cancelled v5 had verified hardware/attention/source but stayed in
data_download_and_verify, with no model inference. Exact remote transport
cause was not recoverable: curl was killed before its captured output was
written. The old nested retries (three outer attempts, each curl with two
retries and a 900-second transfer limit) allowed long stalls; silent curl and
buffered logs hid progress. A Running status was not model progress.

The repaired path removes all origin-data and GitHub-source downloading from
the worker. ZIP bytes are preserved as `.zip.bin` in the private dataset to
prevent archive preprocessing, with the same hashes used in v3. A private
CPU/no-internet/no-model canary checks the actual mount, full ZIP/source hashes,
CRC, release version and source layout before the controlled GPU relaunch.
Every setup subprocess now writes its log live and has an enforced wall-clock
deadline (packages 300 seconds, weights 600 seconds), emitting progress every
15 seconds. Hash/extract helpers also emit progress. A failed child is
terminated and waited on; no retry loop silently extends those deadlines.
Runtime/quality success still requires auditing the resulting model traces.
