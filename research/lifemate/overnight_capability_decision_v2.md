# Revised capability decision v2 — LifeMate: what the overnight audit got wrong, and the SFT prototype that is actually checkable

**Verdict up front (read this, not the old decision): the prototype and
the protocol below are ready for Codex review. Training is NOT
authorized yet.** It stays blocked on the derived-checkpoint answer
(Q-L2, draft only in §4, never sent) and on the zero-shot benchmark
for the base choice. Anyone who quotes this report as "ready to train"
is misquoting it. This report supersedes
`overnight_capability_decision.md` (v1) on every point listed in §1;
points of v1 not listed here stand as written.

## 1. What changed, and what evidence changed it

### 1.1 Quarantine reversed for 3 samples; train_1696 kept separate (Thread A)
- **Old (v1):** train_1005/1033/1319/1696 removed from train/val/test
  before splitting (population 1233).
- **New (v2):** 1005/1033/1319 RETURN to evaluation AND stay in
  training (flagged `contact_source=message_history`). 1696 stays in
  the split assignment but is the ONLY sample with
  `train_eligible=False`.
- **Evidence:** gold replay via ToolEnv succeeds for all three, and
  changed-apps match `label.final_state` in each case. Each contact
  traces to a structured history result rendered into the prompt
  (1005: history `sms.read_recent` message `contact_id` c_778;
  1033: history `phone.recent_calls` nested id c_217; 1319: history
  `sms.read_recent` message `contact_id` c_9526). The runtime prompt
  explicitly permits ids from previous tool results in the
  conversation, and sms/phone never validate membership — replying
  or calling back needs no roster membership. The three-way
  distinction: (a) label wrong? No evidence. (b) Data insufficient?
  No — the source is prompt-observable. (c) Guard conservative?
  Yes, and that is the whole story: G2 counts only roster evidence,
  but that is a guard limitation, not a label verdict.
- **Full-dev scan (decision not ad-hoc):** gold `contact_id` calls
  108 — roster 105 (97.2%), message/call-log-only 3 (2.8%), nowhere
  0. Sample-level: roster 103, message_history 3. V1's exclusion
  removed 100% of a skill class (reply/callback) from evaluation.
  Training argument for keeping them: they pass the D1 all-succeed
  filter, the id is prompt-observable, and they are the ONLY
  examples of that skill class.
- **Recorded tension (unresolved, not hidden):** current G2 would
  fire on exactly these 3 trajectories if ever hard-enforced. That
  must be resolved by guard evolution or search-first teaching, not
  by hiding samples from evaluation. G2 stays shadow-only.
- **train_1696 (separate anomaly):** two verified facets — target
  chat_6142 never appears in the preceding `list_chats` (5 chats
  returned), and the gold `send_message` itself fails replay (ok
  True, done False). The other two gold calls succeed and
  changed-apps match final_state, so this is NOT a final_state
  mismatch. State-hash degeneracy: reproducing the failing call vs
  skipping it gives the identical full-state hash (chat_ott
  unchanged either way); only tool-call F1 distinguishes them (all
  3 calls: 1.0; skip send: 0.8). Handling: keep in evaluation with
  anomaly flag, report its metric separately, report aggregates
  with a with/without-1696 sensitivity note. Training exclusion
  rests on a mechanical ground only (trajectory cannot pass the D1
  all-succeed filter), logged in the manifest — not on a "label
  wrong" verdict.

### 1.2 Manifest v2: membership is not eligibility (Thread A)
- V1 (`inner_split_seed1337.json`) is kept untouched as control.
  V2 (`inner_split_seed1337_v2.json`, generator
  `generate_inner_split_v2.py`, checks `a_v2_checks.py`, diff
  `split_v2_diff.md`): seed 1337 kept, 70/15/15 kept, cell-stratified
  (kind × history × read-before-write) kept, population = full dev
  1237.
- **Counts (coordinator independently recomputed, not taken from
  the manifest's own numbers): inner_train 866 / inner_val 185 /
  inner_test 186.** Effective train size is **865 eligible**
  (866 assigned − 1696). Val/test are 100% eligible. Any later brief
  must state which number it means. Per-part kind/history/rbw rates
  all within ±2pp of the 1237 population.
- **Diff vs v1:** common ids 1233, **moved part 124 (10.1%)**,
  added 4, removed 0 (coordinator recomputed: 124 moved, 4 added).
  Moves are expected from re-running the same procedure on a
  different population (cell membership shifts the RNG stream);
  hand-placing only 4 ids would have been placement bias. All 124
  moved ids are listed in the diff file. Returned samples' v2 parts:
  1005 → test, 1033 → train, 1319 → train, 1696 → train
  (assignment) but ineligible. Near-duplicate group
  train_0061/0066/0168 stays whole in train.
- **Audio (content, not just paths):** 4033 referenced dev audio
  paths (current 1237 + history 2796), 0 missing on disk, 4033
  distinct sha256, 0 collisions, 0 cross-part collisions → dev
  audio is content-disjoint across v2 parts (scoped to referenced
  dev audio files only; held-out files never touched).
- **Overlap, reported not hidden:** exact gold tool sequences: 582
  distinct in dev; val 106/185 (57.3%) and test 115/186 (61.8%)
  share a sequence with train. This split measures new requests
  with familiar behaviours, not unseen behaviour — the
  unseen-sequence slice in the protocol (§3) is the instrument for
  the other question, not this split.
- **Templates:** normalized text (NFD diacritic fold + lowercase +
  digit-run masking) = 1235 groups, 1 multi-member group, 0 groups
  straddling v2 parts; entity-masked secondary identical. NO
  "template-disjoint" claim is made — shared normalized text is a
  text template only; behaviour overlap is the tool-sequence figure
  above.

### 1.3 History-transcript contradiction resolved (Thread A)
- **Old (v1):** one passage said train history has clean
  `audio_text`, another said there is no gold history.
- **Resolution:** the field EXISTS (history user turns 2796, `audio`
  2796/2796, `audio_text` 2796/2796; sample `audio`/`audio_text`
  1237/1237; history assistant `tool_results` list 2384 /
  repr-string 412), but no provenance document in the train
  directory labels `audio_text` as human gold or ASR output.
  Correct term: **"dataset-provided transcript"** (provenance
  UNVERIFIED) — never "gold sạch".
- **Lineage (code-read):** a2e832b `cmd_infer` ALWAYS transcribes
  the current request with ASR; for history it transcribes ONLY if
  `audio_text is None and audio` exists — so on train it uses the
  dataset text as-is and never re-transcribes, while on public_test
  it ASR-transcribes. Prompt history rendering: user turn =
  `audio_text` or "[audio, no transcript available]"; assistant
  turn = text + calls JSON + results repr — history results ARE in
  the prompt (this is also why §1.1's message-history contacts are
  prompt-observable).
- **Consequence:** M4 (current request) gap is KNOWN — dataset text
  in training vs ASR at inference. M3 (history) gap is UNMEASURED
  with provenance UNVERIFIED — write "dataset-provided text vs ASR
  text, gap size UNMEASURED". If dataset history text is itself
  ASR output from dataset construction, M3 is smaller than v1
  assumed — a hypothesis, not a conclusion, needing provenance or
  history-audio WER measurement. No serialization change follows;
  only labels and evidence status change. The E0 claim "history
  stayed ASR" is a harness-design claim, not repo-verified, and NOT
  a property of train.jsonl.

### 1.4 Grounding correction (Thread B)
- **Old (v1):** "grounding stays ON at inference."
- **New:** the frozen zero-shot cell is `baseline.json`
  (grounding=false) for clean attribution; `recommended.json`
  (grounding=true) is a SEPARATE inference variant, evaluated
  separately. The two configs are otherwise identical (same model,
  revision, decoding, context), so no training prompt changes either
  way — but the pilot's comparison cell must say which config it
  used. Training targets are gold calls as-is regardless; grounding
  is never baked into targets.

### 1.5 One runtime contract, provisional (Thread B)
- **Chosen contract (exactly one): `a2e832b-text`** — single user
  message via `apply_chat_template(add_generation_prompt=True)`,
  prose tool list in prompt (one JSON line/tool, name-sorted,
  installed-apps-filtered + `sys.ask_missing_info`), text
  observations (`- <name>(<args repr>) -> <outcome>;
  output=<compact JSON>`), parser `llm.parse_model_output`
  (strip, optional ```json fence, `json.loads`, dict required;
  garbage → `{"name": "__invalid__"}` → validation reject, never
  auto-repaired), stop target `{"stop": true}` (+ EOS
  `<|im_end|>` id 151645), max 3 attempts/step (1 generation + 2
  validation retries), `LoopGuard(max_repeats=2)`, max_steps 12,
  max_context 16384, max_new_tokens 512, transcript_mode gold.
  Pinned: worktree `~/workspace/zaic-branch-a2e832b/lifemate/`,
  agent commit `a2e832b`, config `lifemate/configs/baseline.json`.
- **Why not native V10/V11:** V10 is a bundle (messages + tools +
  parser changed together) whose effect cannot be attributed to any
  part, and it REGRESSED prerequisite (5/21 text → 4/21 native)
  while proxy rose only via sample 0004 — native must never be
  described as "better at planning". V11's catch is channel-scope
  only (pseudo-calls caught 0 → 2, silent stops 1 → 0). Traces
  /tmp/t2_v10_trace.json and /tmp/t2_v11_trace.json are LOST (tmp
  cycle) → trace-level native details are UNVERIFIED, report-level
  only. Arms to separate the bundle (B-roles/B-tools) have NOT run.
- **Provisional:** no full-dev zero-shot benchmark output exists in
  the workspace (only small-sample diagnostics E0/V10/V11/V13 and
  mechanics-only run.py subcommands). The running zero-shot
  benchmark sits outside the workspace (Codex side); its results
  are an input to base selection, not evidence already in hand.
  Base Qwen3-4B-Instruct-2507 rev cdbee75 is therefore the
  PROVISIONAL default (`--model`/`--revision` parameters), not the
  "best base". The builder is base-parameterized, not hardcoded.

### 1.6 Method corrections (Thread C)
- **"Pure SFT only learns ask form" is hypothesis H1, not a
  LifeMate result.** No SFT has run on LifeMate. Mechanisms for H1
  (next-token default fill, SFT imitating structure, SFT OOD
  failure) compete with a mechanism against it (a read-first filter
  directly changes the trajectory distribution the model sees, so
  prerequisite may be learnable by imitation alone). D1-lite exists
  to falsify H1, not to confirm it.
- **D1-lite is a falsifiable pilot (val, cells G1+A0), with
  pre-registered cases:** F0 flat everywhere (proxy < +1pp AND
  prerequisite < +2pp AND fill-act reduction < 2pp) → D1 falsified
  standalone, do not use as D2 cold start; F1 form-only (proxy ≥
  +3pp BUT fill-act < 1pp AND prerequisite < 1pp) → H1 supported
  (not proven), do not adopt D1 alone, D2 only if the pair gate
  passes; F2 decision-shaped (fill-act reduction ≥ 2pp AND
  prerequisite gain ≥ 2pp, proxy not regressing) → H1 partly
  falsified, D1 becomes an adopt candidate (via test), D2 optional
  only if decision errors remain; F3 cell contradiction G1/A0 →
  INCONCLUSIVE, investigate the clean-vs-ASR gap, do not report
  the favorable cell; F4 format breakage (parse failures /
  rejected-call rate up) → D1 rejected, check serialization/loss
  mask before concluding anything about decisions. Results near a
  threshold (±1pp) → INCONCLUSIVE; do not open test to resolve val
  ambiguity (that is test leakage).
- **D2/DPO is conditional, not the default winner.** Order is NOT
  fixed linear D1 → D2: if D1 falsifies fully → backup (D3 +
  grammar/guard, frozen model), no D2. If D1 adopts via test → D2
  optional. DPO runs only if (1) val shows ≥ 10 samples with
  fill-act OR ≥ 10 with prerequisite failure (counted per sample;
  10 is a disclosed operating convention, not a measured constant),
  AND (2) pair yield passes all gates: same true prefix, first-
  divergent-step only (else rename to "trajectory DPO", losing the
  Step-DPO claim), chosen verified (gold or state-hash match),
  rejected from the model's own traces (never imported, never from
  the 404 friend repo), all 3 classes covered (fill-act,
  prerequisite-skip, wrong-entity; none 0, none > 60%),
  ask-chosen share in [30%, 70%], and count
  `N_min = max(5 × distinct error situations in val decision
  errors, 100)` — fixed from pilot yield and logged, never lowered
  after seeing DPO results. Val traces are never training pairs.
  DPO-from-base is REMOVED from the main plan (v1 §6.5's "D2-lite
  on base" contradicted v1 §4.1); it would need a separately
  registered family after D1/D2 results.
- **Test-read rule fixed:** validation selects pilot/config.
  Inner-test opens ONCE per frozen family, as confirmation only.
  The v1 rule "max 2 reads per family (pilot + final)" is DELETED
  because it permits selection on test. Fail → REJECT that family,
  no iteration. A second candidate in the same family is a new
  family needing a new test set (which does not exist) → it is
  test-informed exploration, reported as such, never as adoption.
  Every test read is logged (family, date, cells, config hash,
  result, verdict); an unlogged read is still a read. F_D1 and F_D2
  designs must both freeze BEFORE reading test for either family —
  if F_D2's design changes after seeing F_D1's test, F_D2 is
  test-informed.
- **Sequential held-out exception:** by default NOT used. It may
  only rescue a test-INCONCLUSIVE result if it was pre-registered
  BEFORE reading test ("if test INCONCLUSIVE then held-out decides
  adopt with the same bar", alpha cost disclosed in the Stage 4
  log). Without that pre-registration, held-out never rescues a
  test result. The coordinator decision for this programme:
  **default = no exception** (recorded here so the choice is made
  before test is read).
- **Power: the ≥3pp/CI bar is usually undetectable at n=185–186.**
  For paired binary outcomes with d discordant pairs,
  SE(diff) ≈ √d/n, 95% half-width ≈ 1.96·SE. A +3pp effect is
  ≈ 5.6 net wins; it excludes 0 only if d < 8. At d=10 the
  half-width is already 3.35pp; at d=30 it is 5.80pp. The bar is
  KEPT (never loosened post-hoc: no +3pp → +2pp, no 95% → 90%, no
  one-sided switch, no val+test pooling to inflate n, no
  continuous-proxy backdoor unless a secondary hierarchy was
  pre-registered with primary deciding adopt). The default verdict
  for a small gain is therefore **INCONCLUSIVE** — not "no effect",
  not adopt, not reject. INCONCLUSIVE is a failure of sample size
  to discriminate, not necessarily a failure of the candidate.
  Valid options when underpowered (chosen BEFORE reading test):
  (a) accept INCONCLUSIVE and report fully (recommended default);
  (b) the pre-registered sequential held-out rule above;
  (c) a future protocol with a larger evaluation set + new seed +
  new families (never reusing the old test).
- **Guard reporting (mandatory for every guard table):** overall
  AND breakdown by reference type (contact_id-roster,
  `*_id`-registry, phone_number-roster, phone_number-log,
  phone_number-spoken/text) AND by independent situation, defined
  as (sample_id, reference_value, reference_type) — same triple
  across arms/versions counts ONCE (train_0004 light_set = 1).
  The G2 overall 1.54% (15/976, Wilson [0.0093, 0.0252]) must NEVER
  appear without the phone-only subset 11/19 = 57.9% (Wilson
  [0.3628, 0.7686]). Deployment number = false-block rate =
  false_blocks / (false_blocks + correct_passes) on adjudicated
  correct proposals, with Wilson CI and denominator. Relabeling
  1 − false-block rate as "precision" is banned. Gold-replay rate
  and model-proposal rate are different quantities. No hard-enforce;
  G1/G3 still DROP. Every guard table carries "conditional on the
  call's own ids" (existence ≠ disambiguation). Phone_number branch
  stays shadow-only until text evidence exists.
- **Small strata (principled rule, replacing mechanical 5pp):**
  strata with n < 30 (v2 test: ask_only 7, empty 14, ask_after 18)
  are reported DESCRIPTIVELY with numerator/denominator + Wilson
  CI, never gated at 5pp (1 sample at ask_only n=7 is 14.3pp — a
  5pp gate would reject on one sample). Wilson illustrations: 0/7
  → [0, 0.3543]; 1/7 → [0.0257, 0.5131]; 6/7 → [0.4869, 0.9743].
  Single exception — catastrophic floor: a small stratum with 0
  correct (0/n) blocks adoption of that checkpoint (not a permanent
  direction reject). Strata with n ≥ 30 (v2 test: normal 147) take
  the normal > 5pp regression gate, with CI. Never print a stratum
  as a bare percentage.
- **Paper-claim hygiene (spot-checked, labels kept):** Step-DPO
  first-erroneous-step + self-generated > OOD pairs confirmed at
  abstract level (arXiv:2406.18629v1) — but its scope is math
  long-chain at >70B, NOT tool use at 4B; LifeMate's
  chosen = gold/verified call is an ADAPTATION, labeled as such.
  SpeakRL headline confirmed (Figure 1: base 25.63 / SpeakRL
  46.17, MultiWOZ 2.4) but its SFT/DPO ablation numbers did NOT
  appear in the spot-check snippet → they stay "Thread B read
  §§1–3", not "Thread C confirmed"; its GRPO drops the KL penalty,
  unlike DPO — mechanisms do not transfer. Tool Zero pattern
  confirmed (Live 61.1 → 78.6, Multi-Turn 9.6 → 7.8, xLAM
  cross-dataset inconsistency) but its 7B delta numbers conflict
  slightly across snippets (+7.14/+7.18 vs +6.84/+8.33) → NO delta
  number is quoted as verified, pattern only. STaR/RFT/APIGen/
  APIGen-MT/Hammer stay Thread-B-read, not independently
  re-verified; RFT "distinct paths" is a GSM8K finding applied to
  LifeMate by INFERENCE. AwN stays "abstract + fragment v2, full
  text NOT read". When2Call stays "original NOT read, taxonomy via
  secondary" (taxonomy only, never its dataset as training data).
  Hammer's 7.61B checkpoint is excluded by the 5B cap; only the
  irrelevance idea survives, adapted (LifeMate has no `[]` output;
  its abstention is ask/stop).

### 1.7 Coordinator fixes to the builder (with repro)
Two generic defects were found by the coordinator after Thread B
handed over (the recorded `exitCode 2` in Thread B's handoff was
checked: B's suite passes 20/20 on both backends, and exit 2 is
the documented CLI abort behavior for out-of-part ids — the
coordinator re-verified an abort exits 2 with no file built, see
§2.4; it is not a test failure).
- **Fix 1 — eligibility was silently ignored.** V1's
  `load_manifest` returned only the assignment, dropping
  `train_eligible`. Repro (before fix): `--ids-file train_1696`
  on the v2 manifest → built 1, 4 steps, exit 0. Fix: manifests
  without the map treat all samples as eligible (v1/synthetic
  behavior unchanged); ids-mode aborts (exit 2, nothing built) on
  any ineligible id; coverage mode scans only eligible samples and
  reports `excluded_ineligible`. After fix: `--ids-file
  train_1696` → exit 2, no file built; coverage rerun → scanned
  865, excluded `[train_1696]`, same 16 prototype ids. Tests
  re-run after the fix: 20/20 on both backends.
- **Fix 2 — failing gold calls were recorded as normal steps.**
  `replay_gold` validated (schema only) but never checked
  `done is False`, so 1696's failing `send_message` was built as
  an ordinary step. Fix: any gold call returning ok True with done
  False now drops the trajectory with reason `not_done: <tool>`
  (predicate identical to B's own `not_done_steps` definition, so
  reads — which carry no `done` key — are unaffected). This is the
  D1 all-succeed filter enforced in code, not in prose.
- **Scope note:** Thread B's report predates these fixes; its
  description of builder behavior is stale on exactly these two
  points. This section, not B's report, is the current builder
  contract. The fixes are generic logic, not sample-ID rules.

## 2. SFT prototype — final results on manifest v2 (CPU only)

Builder: `sft_prototype_builder.py` (with §1.7 fixes). Validator:
`sft_prototype_validator.py`. Tests: `test_sft_prototype.py`.
Report: `sft_prototype_report.md` (IDs/counts/token counts only, no
full prompt text). Local-only output: `sft_prototype_local.json`
(contains full prompt texts — NEVER pushed; reproducible by the
commands in §6).

### 2.1 Selection (v2, coverage mode, per-class 2)
Selected 16, built 16, dropped 0, steps 38, scanned eligible 865,
excluded ineligible [train_1696]. No class NOT_FOUND on v2.

| Class | Rule (generic) | Ids (v2) |
|---|---|---|
| empty_stop | 0 gold calls → single stop step | train_0036, train_0057 |
| ask_only | gold calls == [sys.ask_missing_info] | train_0116, train_0219 |
| read_ask | ≥1 read, no write, last call ask | train_0048, train_0245 |
| read_write | 1 write whose `*_id` appears as an `id` field in a prior READ result (WRITE results excluded — an id just created is not an id read) | train_0003, train_0004 |
| multi_step | ≥3 gold calls | train_0011, train_0014 |
| conditional_no_write | 0 writes AND ≥1 read AND condition marker in current request text AND no ask in gold | train_0690, train_0789 |
| direct_phone | phone.call/sms.send with phone_number AND no contacts.search in gold | train_0451, train_0502 |
| history_dependent | 1 `*_id` argument appears in flattened history assistant tool_result AND NOT in current request text (substring check) | train_0063, train_0095 |

Note: these 16 ids coincide with Thread B's v1 smoke-test ids.
That is verified, not assumed: the builder picks greedily in
sorted-id order, and all 16 earliest matches remained in train
under v2. The v2 rerun (not the v1 smoke run) is the prototype of
record; the v1 output is preserved only in /tmp for comparison.

### 2.2 Verification (validator, tokenizer via zaic-test-venv)
- **16/16 passed, 0 failed. Hash match 16/16 (SECONDARY only —
  reads/asks do not change state, so hash alone cannot verify a
  trajectory). Token-span verdicts 16/16 pass.**
- Trained tokens: **636** (target tokens + 1 EOS per step, summed
  over 38 steps; prompt tokens are shared prefixes across steps and
  are NOT summed into this total). Max sequence 8600 tokens, max
  prompt 8594 tokens — all within budget (prompt + 512 ≤ 16384,
  sequence ≤ 16384), 0 over-budget, 0 not_done steps in the final
  set (enforced by §1.7 Fix 2, not by luck of selection).
- Per-example trained tokens (targets + EOS): 0036: 6, 0057: 6,
  0116: 23, 0219: 23, 0048: 37, 0245: 37, 0003: 112, 0004: 43,
  0011: 101, 0014: 63, 0690: 44, 0789: 30, 0451: 30, 0502: 27,
  0063: 31, 0095: 23 (sum 636).
- Causality enforced by construction + validator rebuild equality:
  step-t prompt rebuilt from base + observations of steps < t must
  equal the stored prompt exactly; step-t prompt must not contain
  the full result JSON of step t or later, the final_state JSON
  (trivial `"{}"`/`"[]"` excepted), or the step-t target JSON.
  Documented exception: stop targets are exempt from the
  target-leakage check because the instruction text itself contains
  the literal `{"stop": true}` — that is format specification, not
  answer leakage (found by the validator itself in B's first run:
  12 initial "failures" were all stop steps explained by this).
- Argument fidelity: key sets identical; exact for non-fuzzy
  params; token-F1 > 0.6 for fuzzy params (scoring.py token-F1:
  NFC, lowercase, strip non-word, whitespace tokens; empty/empty →
  1.0; threshold is an engineering-proxy convention, NOT official
  evaluator). Parser round-trip: every target re-parses via
  `llm.parse_model_output` replication to its recorded call, or to
  the stop signal for stop steps.
- Sequence fidelity is PRIMARY (name + canonical args JSON, in
  order; ask last when present; exactly one stop step at the end,
  or absent when ask-terminated; empty = single stop step).
  Counterexample proving hash is insufficient (in the test suite,
  on real ToolEnv): gold + 1 extra read fails sequence check while
  state hash is unchanged (train_0003, extra read
  `contacts.search {"query": "ZZZ-no-such-name"}`).

### 2.3 Coverage limits the prototype does NOT hide
- **Repr-string history: NOT demonstrated by any gold prototype
  example.** All 16 samples have 0 history turns with repr-string
  tool_results (dev has 412 such results). Builder handling of
  repr-strings is covered only by synthetic conformance tests
  against the real `build_base_prompt` (which renders results via
  repr in all cases, so a repr-string result is rendered as a
  quoted string — faithful to the runtime, however odd it looks).
  Codex full-build check: include at least one repr-string-history
  sample when validating rendering on the full training set; do
  not assume the prototype proved it on gold.
- **conditional_no_write matches are rule-candidates, not
  branch-verified.** The rule (condition marker + read + no write +
  no ask) cannot prove the read result decided the branch. The two
  matches are matches by that rule, nothing stronger.
- **read_write is existence-only.** It proves an id appeared in a
  prior read result, not that the entity choice was correct.
- **history_dependent is substring-based, not semantic.** It proves
  textual presence in a history result plus absence from the
  current request, not semantic inference.
- **Guard shadow on prototype trajectories was NOT run.** The
  validator deliberately does not import the guard (guard fire on
  a gold trajectory is a guard-false-block diagnostic, never a data
  error, and the verdict is identical with flags True/False/absent
  — proven by unit test). Running the Round 3 audit scripts over
  the 16 prototype trajectories is a coordinator/Codex follow-up.
  Note the prototype set does NOT contain 1033/1319 (train) or
  1005 (test), so the §1.1 guard tension on message-history
  trajectories is untested by this prototype set.
- **Replay scope, stated plainly:** replay via `env.call` verifies
  simulator transitions only — NOT the full AgentLoop (prompt
  rendering inside the loop, validation retries, loop guard,
  grounding, parser inside the loop are covered by conformance
  tests + prompt-rebuild checks, not by this replay).

### 2.4 Test backends (coordinator reruns, final code)
- `test_sft_prototype.py`: **20/20 pass under system python3 AND
  20/20 pass under ~/workspace/zaic-test-venv/bin/python, 0
  skipped, 0 failed** (both reruns after the §1.7 fixes).
- CLI abort behavior re-verified: `--ids-file` with an ineligible
  id → exit 2, no file built; `--ids-file` with an out-of-part id
  → exit 2, no file built (B's documented case); rerun determinism
  → byte-identical output.
- A-checks rerun: `a_v2_checks.py` reproduces the §1.2 overlap and
  template figures exactly, and rewrites `split_v2_diff.md`
  byte-identically (deterministic).

## 3. Minimal GPU brief (staged; nothing runs by default)

Counts below use v2 (test 186, val 185) with formulas, not v1
totals. Costs are separated; anything unmeasured is NOT_MEASURED
(never an estimate dressed as a measurement). Each stage answers
one decision; a stage that is not reached costs nothing.

- **Stage 0 — Zero-shot model selection (consume, do not rerun
  blind).** The running benchmark's rows are consumable ONLY if
  each row records sample set + n, transcript cell, config, and
  scorer version. If it ran on full dev or held-out, its numbers
  are NOT imported — fall back to Stage 0b. Base stays PROVISIONAL
  until this stage closes. If the benchmark changes the base,
  re-baseline; comparing a candidate trained on the old base
  against a comparator on the new base is forbidden.
- **Stage 0b — Frozen comparator (once, before any candidate).**
  Baseline on inner_test, cells G1+A0: **372 runs** (186 × 2),
  reusable for every family, never re-run on test after seeing a
  candidate. Plus gold-replay sanity on test (CPU): state-hash
  exact must be 1.0 or STOP (scorer/simulator bug, not a model
  result). Val baselines for pilot comparisons (G0/G1/A0 on val)
  are 555 runs, counted only if needed for pilot arms.
- **Stage 1 — ASR ablation (val only).** A1 vs A0 on val 185:
  **185 new model runs** (A1) + 185 medium ASR passes on val
  current (if not cached). Metrics: entity-span error rate + WER
  (per-sample mean + pooled) + attribution G0-vs-A0
  (ASR-attributable = G0 right + A0 wrong; ASR-luck counted
  separately, never netted) + overcorrection rate for every
  conditioning knob. Continue to ASR-critical path only if
  ASR-attributable ≥ 10% of val (≥ 19/185) AND concentrated on
  entity/negation; below 10% → deprioritize, still report the
  negative result. Stage 1 adopts no ASR checkpoint.
- **Stage 2 — SFT pilot D1-lite.** Train ONLY on v2 inner_train
  eligible 865; iterate ONLY on val 185, cells G1+A0. Per
  checkpoint val metrics (mandatory, every checkpoint): 4-number
  proxy decomposition (state-hash exact, gated proxy, raw F1,
  write-only F1) + fill-act + prerequisite + ask confusion + ask
  rate + termination + format failures / rejected-call rate.
  Ask-rate band, pre-registered before the first checkpoint
  evaluation: **gold val ask rate 27/185 = 14.59% → band [9.59%,
  24.59%]** ([rate − 5pp, rate + 10pp]; asymmetric by design —
  over-asking is the main failure mode, under-asking is already
  caught by fill-act). Stop rules: val proxy degrades 2
  checkpoints in a row; ask-rate leaves the band; format failures
  rise; constraint breach; divergence. Cost per full val
  evaluation: 370 runs (185 × 2 cells); total = 370 × checkpoints
  actually run. Output: frozen D1 checkpoint OR verdict F0–F4
  (§1.6) + val numbers + pair-yield report. NO test read.
- **Stage 3 — DPO, conditional.** Only if §1.6 gates pass. Pairs
  from train traces only (never val traces); iterate on val;
  reference = D1 (never DPO-from-base). Stop rules as Stage 2, plus
  DPO format breakage → stop immediately. Any hyperparameter change
  after training starts = a new variant with its own val read.
- **Stage 4 — Frozen test confirmation (exactly 1 read per
  family).** Per family: **372 runs** (candidate G1+A0, 186 × 2);
  baseline comparator reused (0 new); guard shadow 0 model runs.
  If both F_D1 and F_D2 reach test: 372 (comparator, Stage 0b) +
  372 + 372 = **1116 runs** for the test phase. Adopt ONLY if ALL
  pre-registered conditions hold: (1) primary binary (state-hash
  exact) paired diff ≥ +3pp AND paired bootstrap 95% CI excludes 0
  in BOTH G1 and A0; (2) no catastrophic stratum failure (no
  stratum 0 correct); (3) no stratum with n ≥ 30 regresses > 5pp;
  (4) guard shadow on test traces: model-proposal false-block ≤
  2% point estimate, Wilson upper ≤ 5%, correct blocks on ≥ 3
  independent situations (currently 1 on old traces — NOT met,
  must be re-measured, never inherited); (5) constraints pass
  under BOTH total and non-embedding param countings; (6) D1
  standalone additionally requires fill-act AND prerequisite both
  to improve. Fail → REJECT that family. No iteration, no rescue
  except the pre-registered sequential held-out rule (default: NOT
  used, §1.6).
- **Stage 5 — Held-out post-freeze (only if Stage 4 adopts).**
  **616 runs** (308 × G1/A0), reported as-is, no tuning after.
  A contradiction with test is reported, not repaired.
- **Costs (separate lines, all NOT_MEASURED until measured):**
  model runs (counted above per stage actually run); ASR passes
  (Stage 1: 185 medium passes + whatever the pilot's cells need);
  training (wall-clock/memory for D1-lite pilot and DPO — pilot
  slice first: ~100 trajectories, 1 epoch, then a few hundred DPO
  pairs, measuring wall-clock/memory before committing); A30
  latency (p50/p95/max per sample on 1× A30 — BLOCKED, no
  measurement exists; never infer from T4x2). There is no default
  total: the v1 "2096 runs" figure is retired — it summed stages
  that must not all run, on v1 counts, with test reads used for
  selection.

## 4. Draft organiser questions — DRAFT ONLY, NEVER SENT

Status: Q-L1/Q-L2/Q-L3/Q-D1/Q-L5 (+ Q-L4) have NEVER been sent.
The drafts below are for the user to approve/edit first; the
coordinator sends nothing. Suggested send order: Q-L2 first →
Q-L1/Q-L3 before freezing a candidate → Q-D1/Q-L5 in the same
batch → Q-L4 only if A30 access is unavailable.

- **Q-L2 (gates Stage 3 training for submission; ask first):**
  "If we fine-tune a model checkpoint that was released before 26
  October 2026, is the resulting derived checkpoint eligible for
  submission, or must the derived checkpoint itself have been
  released before that date? Does the answer differ for LoRA
  adapters versus fully fine-tuned weights, and for the ASR model
  versus the LLM?"
- **Q-L1 (param counting):** "Does the 6B system / 5B LLM limit
  count embedding parameters? Is the total counted as ASR + LLM +
  any router/embedder/verifier combined, or per-component? Should
  we report both total and non-embedding counts?" (Until answered,
  every candidate must pass under BOTH countings.)
- **Q-L3 (serving/decoding):** "Is vLLM permitted as the serving
  backend inside the offline Docker image? Is structured output /
  XGrammar (or any grammar-constrained decoding backend) permitted
  on the submission path, or must generation be unconstrained?"
- **Q-D1 (licence vs open-source):** "Which licences satisfy the
  open-source rule? In particular, is a research-only or
  non-commercial (e.g. CC BY-NC) licence eligible if the weights
  are publicly downloadable?"
- **Q-L5 (parser contract):** "Is the output parser contract
  (native tool calls plus the registered pseudo-call prefix) part
  of the official evaluation, or may a submission define its own
  output format as long as the tool calls execute correctly? If a
  submission uses a different serialization, how is it scored?"
- **Q-L4 (A30 measurement; only if A30 access is unavailable):**
  "Is the 30-second-per-sample limit measured as wall-clock per
  sample (including ASR + LLM + guard) or amortised over the run?
  Is warm-up excluded?"

## 5. What is BLOCKED, and what this report does not claim

- **Training commitment: BLOCKED on Q-L2.** A derived checkpoint
  may be ineligible for submission regardless of proxy gains. Q-L2
  gates Stage 3 training for submission (not research-only pilot
  measurement, which must be labeled research-only until Q-L2 is
  answered). The other questions (Q-L1/Q-L3/Q-D1/Q-L5) are open but
  do not individually block pilot measurement.
- **Base choice: PROVISIONAL.** Zero-shot benchmark unfinished;
  Qwen3-4B-Instruct-2507 is the current-runtime default, not a
  ranked winner.
- **Official evaluator: ABSENT.** Every score here is the
  engineering proxy (state-hash-gated tool F1, fuzzy threshold
  0.6, ask scoring, read-call scoring — all proxy conventions,
  unverified against the official evaluator). If the official
  evaluator contradicts the proxy, adopt criteria must be
  re-evaluated before any submission claim.
- **Fill-act rule: UNVALIDATED for verdicts.** Before fill-act is
  used for any adopt/reject verdict, 20 flagged cases must be
  manually audited with reported agreement; below 80% agreement,
  fill-act is exploratory only and related verdicts are
  INCONCLUSIVE. (Turn alignment is fragile when the model differs
  from gold in turn count; the rule cannot separate "valid task
  default" from hallucination outside its (a)–(c) sources; it
  inherits prover limits on paraphrase and spoken numbers.)
- **Guard tension on message-history trajectories: UNRESOLVED**
  (§1.1). Guard evolution vs search-first teaching is an open
  decision; the prototype set does not test it (§2.3).
- **A30 latency, train cost/memory: NOT_MEASURED.** No wall-clock
  figure in this report is a measurement.
- **History transcript provenance: UNVERIFIED** (§1.3). Any claim
  about the M3 gap size inherits this caveat.
- **Friend SFT: NOT AUDITED** (repo 404; no alternate access
  attempted; no friend number used or judged).

## 6. Commits, files, hashes, reproduction

- Base of this work: Round 3 branch `round10-provenance-gates-fixes`
  @ `61d84390`; overnight audit branch `overnight-capability-audit`
  @ `d549f583`. This follow-up lives on its OWN branch (created
  from `overnight-capability-audit`, NO merge to main) — branch
  name and push commit are recorded in the handover reply and
  verified below by the coordinator before delivery.
- Push set (12 files; blob-SHA byte-verified local == remote
  before delivery):
  - Thread A: `analysis/overnight_capability_audit/generate_inner_split_v2.py`,
    `inner_split_seed1337_v2.json`, `a_v2_checks.py`,
    `split_v2_diff.md`, `thread_a_split_revision.md`
  - Thread B (builder WITH §1.7 coordinator fixes): `analysis/overnight_capability_audit/sft_prototype_builder.py`,
    `sft_prototype_validator.py`, `test_sft_prototype.py`,
    `sft_prototype_report.md`
  - Thread C: `research/lifemate/overnight_methods_critique_v2.md`,
    `overnight_evaluation_protocol_v2.md`
  - Coordinator: `research/lifemate/overnight_capability_decision_v2.md`
    (this report)
- NEVER pushed: `sft_prototype_local.json` (full prompt texts),
  audio, environments, weights, any dataset with full train
  content. Manifests contain IDs/flags/counts only.
- Reproduction (from `~/workspace/zalo-aic-round3/`, CPU only):
  ```
  python3 analysis/overnight_capability_audit/generate_inner_split_v2.py
  # expect: counts 866/185/186, ALL_CHECKS_PASS: True
  python3 analysis/overnight_capability_audit/a_v2_checks.py
  # expect: structural OK, 4033 audio hashes / 0 collisions, diff written
  python3 analysis/overnight_capability_audit/test_sft_prototype.py
  # expect: 20/20 OK (system python3 and venv python)
  python3 analysis/overnight_capability_audit/sft_prototype_builder.py \
    --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
    --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
    --manifest analysis/overnight_capability_audit/inner_split_seed1337_v2.json \
    --part inner_train --manifest-version v2 --select-coverage --per-class 2 \
    --tokenizer-python ~/workspace/zaic-test-venv/bin/python \
    --out analysis/overnight_capability_audit/sft_prototype_local.json
  # expect: selected 16, built 16, dropped 0, steps 38, scanned 865,
  #   excluded_ineligible [train_1696]
  python3 analysis/overnight_capability_audit/sft_prototype_validator.py \
    --output analysis/overnight_capability_audit/sft_prototype_local.json \
    --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
    --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
    --catalog ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train_tools_catalog.json \
    --tokenizer-python ~/workspace/zaic-test-venv/bin/python
  # expect: n_examples 16, passed 16, failed 0, hash_match 16, token spans 16/16
  ```
