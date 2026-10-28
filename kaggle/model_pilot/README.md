# Paired model pilot: gold current + history

This is an opt-in experiment. It does not change `lifemate/`, defaults,
the simulator, scorer, split, or normalization hook.

- Base runtime: `a472006441ec69aee1238153b0c7daf53ba41dee`, immutable private mounted source.
- Dataset: original v3.2.0 ZIP, SHA256 checked before extraction.
- Eight selected dev diagnostics, matching the earlier V7/E1 ID set. No held-out.
- Current transcript and every history user transcript are gold. Labels are removed
  from the object supplied to `AgentLoop`; gold replay/scoring occurs after inference.
- Qwen3-4B-Instruct-2507 vs Qwen3.5-4B, exact revisions in `runner.py`.
- Both use the same decision policy and wire-neutral system sentence. Each gets
  its own official tokenizer/template and native wire parser. This is **not**
  an exact replay of V11, which used another Transformers version and final sentence.
- Greedy seed 42, no thinking, FP16, no quantization, context 16384, output 512,
  max 12 steps and the existing retry/grounding guards.
- Qwen3.5 is loaded through `AutoModelForCausalLM`; loaded parameter count and
  model class are recorded. This may omit vision/MTP. No contest eligibility
  conclusion is inferred from that omission.
- Transformers 5.20.2, accelerate 1.15.0, huggingface-hub 2.3.0.
- T4 efficient SDPA uses a temporary HF repeat-KV override, restored on exit.
  Numerical parity is checked before weight download. Floating-point outputs may
  differ from earlier software/kernels; speed is **not** an A30 estimate.
- Sample 240s and generation 90s are diagnostic soft limits, **not** the official
  30s budget. A parent process enforces 2400s for the worker including downloads.

## Gates and outputs

Run `python kaggle/model_pilot/test_contract.py` for synthetic contract tests.
Run the existing `lifemate/tests` separately. The CPU notebook checks real
tokenizer rendering, tool-observation round-trip, matching semantic message
hashes, all 16 initial context budgets, mounted file identities and dev membership.
GPU launch follows CPU success; GPU worker repeats these checks before weights.

`build_notebook.py` writes private CPU/GPU notebook bundles under the sibling
`artifacts/lifemate-model-pilot/` directory. It embeds only this experiment's
source, not credentials or any friend's private code/weights.

Each generation saves raw output, model input messages, token counts, parsing
diagnostics and timing. Each sample saves executed observations, validation
rejects, submission, independent replay check and `ENGINEERING_PROXY_NOT_OFFICIAL`.
An eight-sample pilot validates integration and failure mechanisms; it cannot
establish model ranking, representative accuracy, or a baseline promotion.
