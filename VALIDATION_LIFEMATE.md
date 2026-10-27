# LifeMate integration fixes — 2026-10-27

Base: `fe7e0aea2b20a111dcbbe4baad31f5a61626ebfa`.
Branch: `codex/lifemate-baseline-integration`.
All changes are in this checkout. Simulator, dataset, seed 42, LLM checkpoint
`Qwen3-4B-Instruct-2507` revision `cdbee75`, and the committed split are unchanged.

## Six fixes

| Area | Before | After / evidence |
|---|---|---|
| ASR | Original PhoWhisper weights passed directly to CTranslate2 | Transformers backend for original weights; backend factory honours config; unconverted CT2 path rejected before loading |
| Subset | `infer --split train` ran all train despite heldout instructions | Shared selection for run/check/score, assignment before limit; actual dataset selects exactly 308 heldout IDs |
| Grounding | Config flag unused | Typed supplied-slot normalization before official validation; observed name-to-ID repair; regression changes amount string `1,5 triệu` to integer 1500000 only when enabled |
| Tool prompt | Only name/description/required fields | Full JSON schema including optional properties, types, enum, x-ref; context/history and observations retained |
| Context | 16K only in config | vLLM `max_model_len` and both backends' prompt+reserved-output checks; fail explicitly on overflow |
| Proxy F1 | Greedy matching depended on call order | Maximum bipartite one-to-one matching; adversarial case is 1.0 for both permutations (previously 0.5 versus 1.0) |

The two configurations still use the same model sizes and greedy seed. ASR
backend, full-schema prompt and actual grounding activation affect predictions;
they are not accuracy-neutral refactors and no quality improvement is claimed.
The scorer remains **ENGINEERING_PROXY_NOT_OFFICIAL**.

## Actual validation

Environment: Windows, Python 3.14.1, jsonschema 4.25.1, torch 2.11.0,
transformers 5.7.0. No package installation or model download was performed.

- Before fixes: the original 13 LifeMate tests passed with local data; the new
  targeted suite exposed 8 failures/errors (2 failures, 6 errors).
- After fixes: **24/24 LifeMate tests pass**, including original real-data
  loader/adapter tests and 11 added integration regressions.
- Deep-dives: **46 pass / 8 skip / 0 fail** out of 54; DuckDB is not installed.
- Compile check: `python -m compileall -q lifemate` succeeds.
- Heldout empty-policy run: **308 lines / 0 replay mismatches**.
- Public smoke: **20 lines / 0 replay mismatches**.
- Heldout proxy score of the EMPTY POLICY: **22/308 = 0.07142857**. This is only
  scorer/split/CLI plumbing; **not a model baseline result**.
- ZIP SHA256 independently checked locally:
  `57d371518996ec70d3af86402b7eba61208093c82955b9807a7ab39604b47320`.

Detailed run logs and the exact subprocess argument lists are kept outside
Git under `../artifacts/lifemate-integration-fix/` (`commands.json`, individual
`.log` files and the two empty-policy JSONL artifacts). Data/audio/weights are
not committed.

Native ASR import was also attempted (without weights):
`from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline`.
It **failed** in this global environment: `AutoProcessor` import is blocked by
`RuntimeError: operator torchvision::nms does not exist`. Full traceback:
`../artifacts/lifemate-integration-fix/native_asr_import.log`. This is not a
passed ASR runtime check. No global packages were changed; use an isolated,
compatible dependency environment for the first real run. Do not copy this
global environment's version list as a tested GPU lockfile.

## Touched files

- `.gitignore`: generated cache/output exclusions.
- `README.md`: link to the executable handoff and validation.
- `RUN_LIFEMATE.md`: corrected backend, offline preparation, subset and check/score commands; explicit limitations.
- `lifemate/config.py`: original-weights ASR default, offline mode and reserved output budget.
- `lifemate/configs/baseline.json`, `lifemate/configs/recommended.json`: same checkpoint/seed/split, new backend and budget settings.
- `lifemate/asr.py`: Transformers implementation and explicit CT2 preflight.
- `lifemate/llm.py`: backend factory, offline cached weights, context accounting.
- `lifemate/agent.py`: schema/context prompt and grounding invocation.
- `lifemate/grounding.py`: supplied-slot normalization and observed name-to-ID repair.
- `lifemate/run.py`: subset/limit wiring and exact submission ID checking.
- `lifemate/scoring.py`: order-independent matching.
- `lifemate/tests/test_integration_fixes.py`: 11 focused regressions.
- `VALIDATION_LIFEMATE.md`: this report.

## Commands executed

Read-only inspection used `Get-ChildItem`, targeted `Get-Content` on the project
instructions/source/data README and first train JSONL, scoped `rg --files`,
`git rev-parse`, `git status --short -- .` and scoped `git diff`.
The initial checkout and branch commands were:

```text
git clone https://github.com/lenamkhanhh/ZaloAIC.git repo
git switch -c codex/lifemate-baseline-integration
```

Python capability/version checks used `importlib.util.find_spec` and
`importlib.metadata.version` (no installation). A small Python script updated
only the two config JSON files. The handoff was rewritten in place.

Verification commands (the subprocess log contains expanded absolute paths):

```powershell
$env:LIFEMATE_DATA=(Resolve-Path '..\train+public_test\train+public_test').Path
$env:PYTHONWARNINGS='ignore::ResourceWarning'
python -m unittest discover -s lifemate/tests -p test_integration_fixes.py -v
python -m unittest discover -s lifemate/tests -v
python -m unittest discover -s deep-dives/tests
python -m compileall -q lifemate
python -m lifemate.run infer --help
Get-FileHash -Algorithm SHA256 -LiteralPath '..\train+public_test.zip'
git diff --check -- .
git diff --stat -- .
```

The warning filter suppresses existing unclosed-file ResourceWarnings from the
unmodified official `zaic_tools`; no simulator code was edited.

Run/check/score smoke commands:

```text
python -m lifemate.run fake-run --data <data> --split train --subset heldout --out <artifacts>/heldout_empty.jsonl
python -m lifemate.run check-submission --data <data> --split train --subset heldout --submission <artifacts>/heldout_empty.jsonl
python -m lifemate.run score --data <data> --split train --subset heldout --submission <artifacts>/heldout_empty.jsonl
python -m lifemate.run fake-run --data <data> --split public_test --limit 20 --out <artifacts>/public20_empty.jsonl
python -m lifemate.run check-submission --data <data> --split public_test --limit 20 --submission <artifacts>/public20_empty.jsonl
```

## Remaining limits

No model inference, model latency or GPU/A30 claim is made. The backend wiring
and context limits are tested with doubles; this does not verify native vLLM,
CUDA, weights or ASR numerical behavior. The first real run remains 5 dev
samples, then the fixed heldout. GPU dependencies are not claimed to be locked.
There is no hard native-call 30-second watchdog. ASR snapshot revision should
be recorded at preparation time. Ask/read scoring questions remain unresolved.

Official API references consulted:
[PhoWhisper model card](https://huggingface.co/vinai/PhoWhisper-small),
[vLLM LLM API](https://docs.vllm.ai/en/stable/api/vllm/entrypoints/llm/).
