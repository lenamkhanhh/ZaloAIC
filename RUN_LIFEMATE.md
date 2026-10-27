# RUN_LIFEMATE — executable handoff

CPU harness verified; **GPU/model inference remains UNVALIDATED**. The local scorer is an ENGINEERING_PROXY, not the organiser evaluator. No simulator, dataset, model checkpoint or split assignment is changed by this integration fix.

## 0. Dữ liệu nằm ở đâu — và làm sao lấy lại đúng phiên bản

**Dữ liệu KHÔNG nằm trong repo này** (không push raw dataset/audio/
weights — đó là quy tắc bàn giao). Trên máy dev của tác giả, dữ liệu
nằm ở `workspace/zaic-data/lifemate/`, nhưng đó KHÔNG phải máy của bạn:
đừng coi file trong workspace đó là đã có trên máy bạn. Tải lại đúng
phiên bản bằng lệnh sau (link từ trang Data của portal sau đăng nhập):

```bash
mkdir -p data/lifemate && cd data/lifemate
curl -L -C - -o train+public_test.zip \
  https://dl-challenge.zalo.ai/2026/lifemate_argfzdgert/train+public_test.zip
# Xác minh (bắt buộc — HEAD 200 không tính là tải thành công):
ls -la train+public_test.zip            # phải đúng 876430231 byte
sha256sum train+public_test.zip         # phải đúng 57d371518996ec70d3af86402b7eba61208093c82955b9807a7ab39604b47320
unzip -t train+public_test.zip          # phải báo "No errors" (27254 entry)
unzip -q train+public_test.zip -d extracted   # -> extracted/train+public_test/ (1,2 GB)
```

Phiên bản đã xác minh: `VERSION` ghi `release: v3.2.0`, build
2026-10-24, `train 1545 / public_test 634`. Lưu ý: lần tải đầu tiên
trên máy dev bị đứt ở 99,4% (curl error 18, còn thiếu 5.276.829 byte)
— luôn kiểm tra size + SHA256, đừng tin progress bar. Nếu SHA khác,
tải lại bằng `curl -C -` (resume) rồi kiểm tra lại.

Từ đây trong tài liệu, `<data>` = thư mục `extracted/train+public_test/`
(chứa `train/` và `public_test/`).

## 1. Configuration and experiment-affecting changes

- `recommended.json`: PhoWhisper-small + Qwen3-4B-Instruct-2507 (`cdbee75`), greedy, seed 42, total approximately 4.244B. Grounding enabled.
- `baseline.json`: identical settings, grounding disabled. The switch is now consumed before official tool validation.
- **ASR backend changed to Transformers** for the original PhoWhisper weights. Faster-whisper requires an explicitly converted local directory containing `model.bin`; changing GPU cannot fix a checkpoint-format mismatch.
- Prompts now include the full per-tool JSON schema (optional fields, types, enums, x-ref, descriptions), supplied context, history, and observations. This changes model inputs; old proxy/model results are not directly comparable.
- Numeric/date normalization touches only supplied fields. Name-to-ID repair uses observed read results from the referenced app; it does not invent missing arguments or automatically call ask. The fuzzy thresholds 88/8 are inherited proposals, not validated ZAIC optima. Raw observed IDs retain their original spelling.
- Selective reads are a prompt policy; there is no semantic read cache. The loop guard limits repeated calls. XGrammar token masking is **not implemented** in this runner: generation uses validate-and-retry.
- Both LLM backends reserve 512 output tokens inside the configured 16,384-token context. Oversize prompts fail explicitly; schemas/history are not silently truncated.
- ASR/model initialization and native GPU calls have not been benchmarked. The code does not provide a hard preemptive 30-second GPU watchdog. Verify the complete per-sample runtime on A30 before submission.

## 2. Installation and offline weights

The commands below target **Linux/Kaggle for vLLM**. CPU harness/tests also run on Windows. A GPU with around 16 GB or more is a starting hardware estimate, not a measured guarantee.

```bash
pip install jsonschema rapidfuzz
pip install torch transformers accelerate huggingface_hub vllm
```

The GPU dependency stack is not claimed to be validated or locked. Record the exact installed versions and CUDA build after the first GPU smoke test.

The inspected global Windows environment has an incompatible optional torchvision build (`torchvision::nms does not exist`) that blocks AutoProcessor import. Use an isolated compatible environment; no global package repair was performed. See VALIDATION_LIFEMATE.md and its native-import failure log.

Prepare weights once with Internet enabled (this command downloads weights; inference does not):

```bash
python -c "from huggingface_hub import snapshot_download; print(snapshot_download('vinai/PhoWhisper-small')); print(snapshot_download('Qwen/Qwen3-4B-Instruct-2507', revision='cdbee75'))"
```

Configs default to `local_files_only=true`. Use the same Hugging Face cache at inference, or set checkpoint paths to the downloaded snapshot directories. Record the resolved ASR snapshot revision; the inherited ASR checkpoint was not pinned to a revision. Do not put weights or data in Git.

Optional CTranslate2 backend: convert PhoWhisper separately, point `asr_checkpoint` to that local directory, and set `asr_backend=faster-whisper`. Original Transformers weights are rejected before loading. There is no silent backend fallback. Set `llm_backend=transformers` explicitly if vLLM is unavailable.

## 3. CPU validation and split selection

Run from the repository root. Set `<data>` to the extracted directory containing `train/` and `public_test/`.

```bash
export LIFEMATE_DATA='<data>'
python -m unittest discover -s lifemate/tests -v
python -m unittest discover -s deep-dives/tests
python -m lifemate.run replay-gold --data '<data>' --n 50
mkdir -p artifacts
python -m lifemate.run fake-run --data '<data>' --split public_test --limit 20 --out artifacts/fake_public.jsonl
python -m lifemate.run check-submission --data '<data>' --split public_test --limit 20 --submission artifacts/fake_public.jsonl
```

Use the committed `lifemate/splits/train_dev_heldout.json`, seed 42: dev=1237, heldout=308. `--subset` is applied **before** `--limit`. `--subset all` means all selected split samples; it does not mean heldout. Dev/heldout are accepted only with `--split train`. Supply `--split-file` only when intentionally using a different assignment; dataset IDs must match exactly.

Checking/scoring verifies the exact selected IDs and rejects duplicates, unknown IDs and missing rows. For smoke-test submissions use the same `--subset` and `--limit` at run/check/score time.

## 4. First GPU run: dev smoke, then heldout

Do not start a full run until the first 5 dev samples load both real backends successfully.

```bash
python -m lifemate.run infer --data '<data>' --split train --subset dev --limit 5 --config lifemate/configs/recommended.json --out artifacts/dev5.jsonl
python -m lifemate.run check-submission --data '<data>' --split train --subset dev --limit 5 --submission artifacts/dev5.jsonl
python -m lifemate.run score --data '<data>' --split train --subset dev --limit 5 --submission artifacts/dev5.jsonl

python -m lifemate.run infer --data '<data>' --split train --subset heldout --config lifemate/configs/baseline.json --out artifacts/heldout_baseline.jsonl
python -m lifemate.run score --data '<data>' --split train --subset heldout --submission artifacts/heldout_baseline.jsonl
python -m lifemate.run infer --data '<data>' --split train --subset heldout --config lifemate/configs/recommended.json --out artifacts/heldout_recommended.jsonl
python -m lifemate.run score --data '<data>' --split train --subset heldout --submission artifacts/heldout_recommended.jsonl
```

For a CPU-only model backend select Transformers in a separate config and pass `--device cpu`; this is not an A30 latency measurement. Training/evaluation history has gold transcripts while public history must be transcribed, an inherited difference to report when comparing split performance.

Do not tune repeatedly on heldout and report that same set as independent evidence. The existing split measures within-template-family generalization; it is not an unseen-app benchmark.

## 5. Public inference

```bash
python -m lifemate.run infer --data '<data>' --split public_test --config lifemate/configs/recommended.json --out artifacts/submission.jsonl
python -m lifemate.run check-submission --data '<data>' --split public_test --submission artifacts/submission.jsonl
```

UTF-8 JSONL: `{id, tool_calls, state_hash}`. Calls/hash come from one official ToolEnv per sample. All executed calls are preserved. Agent input never calls `get_state()` or reads environment files directly; gold replay is diagnostic-only.

## 6. Evidence and remaining questions

See `VALIDATION_LIFEMATE.md` for this integration fix, commands, touched files and actual CPU results. Archive size/SHA and earlier full-gold replay above came from the prior handoff; do not confuse them with model results.

- Organiser evaluator is absent. Ask scoring, read-call F1 and terminal trace scoring remain unresolved. The local scorer is explicitly labelled ENGINEERING_PROXY_NOT_OFFICIAL.
- Fuzzy tool-call matching now uses maximum one-to-one matching; old greedy matching was order-dependent. Proxy scores may change even with identical predictions.
- Grounding, full-schema prompts and ASR backend selection are implementation changes, not demonstrated quality gains.
- No new model inference, training, acoustic rescoring, contextual decoding or SFT result is claimed. Checkpoint/seed/split remain unchanged; model behavior and 30-second runtime still require the GPU smoke test.
