# Thread C — Evaluation protocol: zero-shot vs new directions (LifeMate)

- **Thread:** C (evaluation design only). Companion threads A (data/SFT readiness)
  and B (methods research) run in parallel; this document does not depend on
  their conclusions and must not be read as their synthesis.
- **Date / scope:** 2026-10-29. Protocol for comparing the current zero-shot
  pipeline against new directions (SFT or alternatives) on LifeMate.
- **What this document is not:** it runs no model, trains nothing, touches no
  GPU, opens no held-out row, and changes no inference / simulator / scorer /
  guard / benchmark-config code. It is a pre-registered design that Codex (or a
  later GPU run) can execute.
- **Headline rule:** every comparison in this protocol is decided on the
  **inner decision-test (n = 187, §2)** drawn from dev only. The held-out 308
  is locked until post-freeze verification (§2.4). Any result quoted without
  naming its sample set, transcript type, config, and evidence class is
  inadmissible under this protocol.

## 1. Frozen reference: what the new comparison is measured against

### 1.1 Baseline identity (read from the repo, not remembered)

- Baseline config: `lifemate/configs/baseline.json` — PhoWhisper-small
  (`vinai/PhoWhisper-small`, faster-whisper, greedy, `vi`) +
  Qwen3-4B-Instruct-2507 (`Qwen/Qwen3-4B-Instruct-2507`, revision `cdbee75`,
  vLLM, temperature 0.0, seed 42, max context 16,384 tokens, max_steps 12,
  max_repeats 2, grounding off, selective_reads on).
- Budget as configured: total 4.244B (0.244 + 4.0), LLM 4.0B — inside the
  <6B system / <5B LLM limits **under the repo's own counting rule**
  (total parameters including embeddings; see §7 for what is UNVERIFIED
  about the organiser's counting rule).
- Split: `lifemate/splits/train_dev_heldout.json`, seed 42, heldout_frac 0.2 →
  **dev 1237 / held-out 308** (verified by counting the split file's values;
  no held-out row was opened for this document).
- Scorer: `lifemate/scoring.py` is an **engineering proxy, not the official
  evaluator** (the package ships no evaluator). Per sample: score = tool-call
  F1 **iff** submitted state_hash == gold state_hash, else 0; order ignored;
  empty gold scores 1 only if submission is also empty. The scorer's own
  docstring marks as UNVERIFIED: whether `sys.ask_missing_info` is scored by
  the same F1 rule or a special ask rule; whether reads count in F1 at all;
  whether wrong-`[]` vs wrong-ask differ. **Therefore no proxy number in this
  protocol may be reported as "the LifeMate score".** Report the proxy plus
  its components (§4.3) so the conclusion survives either scorer reading.

### 1.2 Prior results, each scoped to its config and sample (evidence classes)

| Result | Value | Evidence class | Scope caveat (do not generalise past this) |
|---|---|---|---|
| E0 | proxy 0.125 | Real model run | Gold **current** transcript only; history stayed ASR. NOT perfect information. The "ASR is not the bottleneck" reading is invalid beyond this cell. |
| V10 (E1) | proxy 0.125 → 0.1875 | Real model run | **Format scope only** (prerequisite 5/21 → 4/21 fell). "Prompt fixes planning" is NOT supported. |
| V11 (E6-C) | caught pseudo-calls 0 → 2; silent stops 1 → 0 | Real model run | **Channel scope only** (registered lowercase `app.tool(` prefix). |
| V13 (E5) | INCONCLUSIVE: target ask-first 0/7 → 1/7; control 0/13 → 0/13; proxy 0.0 → 0.05 (solely train_0116) | Real model run + deep analysis | Other targets fail by **fill-act** (model fills time from context, so "ask when missing" never fires). Do not rescore V13. |
| Guard gold audit (Round 3) | false-block rate 15/976 = **1.54%**, verdict KEEP | Gold replay (dev) | 15 = 4 old message-history/anomaly blocks + 11 residual phone_number blocks (user-spoken / history-text / message-content numbers; §5.4). This is a **gold-replay** rate, not a model-proposal rate. |
| Guard shadow V10/V11/V13 | V10 blocked 6 / passed 8, false_block 0; V11 blocked 6 / passed 4, false_block 0; V13 blocked 16 / passed 6 / out-of-scope 7, false_block 0 | Saved model proposals (shadow, no veto) | Paired re-run after Round 3 integration is **row-identical** on all three traces (14/14, 10/10, 29/29). Independent positive samples = **1 (train_0004 only)** — INSUFFICIENT for any safety / hard-enforcement claim. |
| Friend-harness SFT numbers (e.g. Qwen3.5 SFT 0.6693) | — | README / report without artifact | **Inadmissible for selection.** Different harness/split, SFT effect not isolated, no weights/log/submission, repo access 404. Thread A records this as unaudited; this protocol forbids citing it as a baseline. |
| "Prompt ceiling", "fine-tune bad" | — | Prior conclusions | **Scoped claims, not general truths.** Each rests on one config/sample cell above. Any new direction must be judged on the §2 decision-test, not against these slogans. |

### 1.3 Dev facts measured for this protocol (dev 1237 only, CPU, 2026-10-29)

These numbers shape §2–§3; they are not results of any model run.

- Gold kinds: act 974, ask_mixed 126, empty 89, ask_only 48.
- Gold call counts: 0 calls 89; 1 call 299; 2 calls 332; 3 calls 293;
  4 calls 127; 5 calls 89; 6 calls 8. Multi-call (≥2) gold: 849.
- History present: 814 samples; absent: 423.
- Gold read-before-write present: 667 samples; write without any prior read: 246.
- Gold ask calls total: 174 (across ask_only + ask_mixed samples).
- Audio paths: all 1237 distinct within dev (no duplicate audio file).
- Current-request text templates (diacritic-folded, lowercased, digits
  masked to `#N`): 1235 distinct for 1237 samples; exactly **one** group of 3
  (`train_0061`, `train_0066`, `train_0168` — identical wording except the
  hour digit, which digit-masking merges). Text-template leakage across a
  random inner split is therefore small — but see the next line.
- Gold tool-name sequences: only **582 distinct** for 1237 samples; 816
  samples share their exact gold tool sequence with at least one other
  sample; largest group 89. **Behaviour templates repeat heavily even though
  request texts do not.** A random inner split will share behaviour
  templates across train/val/test. That is expected and reportable (§3.3),
  not contamination — but it forbids claiming a random-split number is an
  "unseen behaviour" number.

## 2. Inner split: train / validation / decision-test inside dev 1237

### 2.1 Design (primary, pre-registered)

Split dev 1237 **once**, before any SFT or tuning, into three disjoint parts:

| Part | Size | Role — the only role it may play |
|---|---|---|
| Inner-train | 866 | SFT training data (if SFT is chosen). Never evaluated for selection. |
| Inner-validation | 185 | Early stopping, checkpoint choice, hyperparameter choice, prompt/config iteration. May be evaluated repeatedly during development. |
| Inner decision-test | 186 | **The single decision set.** Each candidate direction is evaluated on it **once** for the adopt/reject decision (§8). No tuning, no early stopping, no prompt iteration against it. |

Target counts by gold stratum (largest-remainder rounding of 70/15/15):

| Gold stratum (dev n) | Train | Validation | Decision-test |
|---|---|---|---|
| act (974) | 682 | 146 | 146 |
| ask_mixed (126) | 88 | 19 | 19 |
| empty (89) | 62 | 13 | 14 |
| ask_only (48) | 34 | 7 | 7 |
| **Total** | **866** | **185** | **186** |

- **Stratification variables:** gold stratum (above) is mandatory. Within each
  stratum, shuffle with a **new seed distinct from 42 (use 1337)** and deal
  round-robin so history-presence (814 vs 423) and read-before-write presence
  (667 vs 246) stay within ±2pp of dev rates in every part; if a shuffle
  misses that band, re-shuffle (seed 1337 + attempt counter recorded in the
  manifest — never hand-pick samples to fix a band).
- **Why 70/15/15 and not 80/10/10:** SFT on ~866 samples is already small;
  cutting train to gain decision-test precision is the wrong trade only if
  the decision-test is too small to decide. n = 186 gives, for a per-sample
  binary outcome at p ≈ 0.2, SE ≈ 0.029; a paired comparison on the same 186
  samples (§4.2) has materially smaller variance than two independent
  samples. The 80/10/10 variant (train 990 / val 123 / test 124) is permitted
  **only** if Thread A's audit shows a data-hunger case for a specific
  direction, and only if the switch is recorded before any run on either
  candidate test set. Never run both variants and pick the friendlier one.
- **Manifest (to be generated by the main thread / Codex, not by Thread C):**
  `analysis/overnight_capability_audit/inner_split_seed1337.json` mapping
  sample id → `inner_train` / `inner_val` / `inner_test`, plus the generator
  command, the stratum counts above, and the overlap-check report (§3).
  Thread C created **no** split file, to respect single-file ownership; the
  manifest must be generated from dev ids only (the generator must assert
  every id is in the dev set of `lifemate/splits/train_dev_heldout.json`
  before writing anything).

### 2.2 What "trained on part of dev" costs (non-negotiable)

- Any sample in inner-train is **burned for evaluation**: it may never appear
  in a number used to claim the SFT direction beats zero-shot. Reporting an
  SFT number on inner-train (or on full dev 1237, which contains inner-train)
  as evidence of improvement is a protocol violation, not a weak result.
- Inner-validation numbers are **development numbers**: they may guide
  iteration but may not be quoted as the direction's performance.
- Only inner decision-test numbers support an adopt/reject claim, and only
  under the paired analysis of §4.2.

### 2.3 If a direction needs no training (prompt / architecture / ASR change)

The same three parts still apply: iterate on inner-validation, decide once on
inner decision-test. "No training" does not exempt a direction from the
decision-test rule — prompt iteration against the decision-test is the same
leak as training on it, just slower.

### 2.4 Held-out 308: lock rule

- **Locked** for: direction selection, tuning, early stopping, prompt choice,
  threshold choice, guard-threshold choice, error analysis that feeds back
  into design, and any "sanity check" that could change a decision.
- **May be touched exactly once:** after a direction is frozen (config,
  checkpoint, prompts, guard settings all recorded and immutable), a single
  verification run on held-out 308, reported as-is with no further tuning.
  If that run contradicts the decision-test result, the contradiction is
  **reported, not repaired** by re-tuning: the team then decides (as a new,
  recorded decision) whether to re-open development with a new decision-test
  — the old decision-test is then burned for that direction too, and a fresh
  split/seed is required.
- No held-out row, transcript, audio, label, or aggregate computed from
  held-out rows appears in any development artifact. Split sizes (308) and
  this lock rule are the only held-out facts this protocol uses.

## 3. Overlap checks (run on the manifest before any GPU run; fail = re-split)

All checks run on **dev ids only**. A check that fails blocks the GPU chain
(§8) until the manifest is fixed and re-checked.

1. **Sample-id disjointness.** Assert pairwise intersections of the three
   parts are empty. Trivial, but recorded (a silent id leak invalidates
   everything downstream).
2. **Audio disjointness.** Assert no audio path (and, as a second pass, no
   audio file content hash) appears in more than one part. Within dev all
   1237 audio paths are distinct (§1.3), so this check is expected to pass
   by construction; it exists to catch a future data refresh that re-uses
   an audio file under a new id.
3. **Normalised text-template overlap.** Normalise each sample's current
   request text: lowercase → diacritic-fold (NFD strip + đ→d) → digits
   masked to `#N` → whitespace collapsed. Group samples by normalised text.
   **Rule: no group may straddle parts.** The known dev group
   (`train_0061`, `train_0066`, `train_0168`) must land wholly in
   inner-train. Report: number of cross-part groups (must be 0) and the
   group-size distribution.
4. **Entity-masked template check (secondary, approximate).** Repeat check 3
   after additionally masking every roster contact name occurring in the
   text (names taken from that sample's own contacts-search trajectory /
   roster — dev data only) with `#NAME`. This catches near-duplicates that
   differ only by a person's name. Report overlap count; any cross-part
   group found here is moved whole to inner-train (never deleted silently:
   the move is recorded in the manifest's changelog).
5. **Near-duplicate sweep.** For all cross-part pairs of current-request
   texts, compute token Jaccard on normalised tokens; flag pairs ≥ 0.90 for
   manual review. Threshold rationale: below 0.90, Vietnamese request texts
   share function words too freely for the flag to be informative; at or
   above 0.90 the pair is almost certainly the same request with a slot
   changed. Flagged pairs are resolved by moving the val/test member whole
   to inner-train (recorded) — never by editing text.
6. **Gold tool-sequence overlap — report, do not "fix".** Compute the share
   of decision-test samples whose exact gold tool sequence also occurs in
   inner-train (dev-wide expectation: high, §1.3). This number is reported
   alongside every decision-test result as the "shared-behaviour rate". It
   is **not** contamination and must not be eliminated by re-splitting:
   eliminating it would build a test set unlike the deployment distribution.
7. **Sequence-disjoint diagnostic slice (secondary metric only).** Define
   `test_unseen_seq` = decision-test samples whose gold tool sequence occurs
   nowhere in inner-train. Report the primary metric on this slice with its
   n disclosed (expect small n — do not select on it; a slice of n < 30 is
   reported as "indicative, underpowered" and never headlined).
8. **History-text leakage check.** Collect normalised history user-turn texts
   from inner-train samples; assert none equals a decision-test (or
   validation) current-request text after normalisation (check 3's
   normalisation). A match means the test request was already seen as a
   history turn — move the affected test sample to inner-train (recorded).
9. **Audio-content check across parts.** Same file under different paths
   would defeat check 2; verify by content hash of the audio files listed
   for the three parts (hashes only in the report — never audio content).

## 4. Counting units, non-independence, and what "correct" means

### 4.1 Counting units (per metric — no exceptions)

| Metric | Counting unit | Aggregation | Why |
|---|---|---|---|
| Primary: state-hash exact rate; proxy score; ask correctness | **Sample** | Mean over decision-test samples (n = 186), one value per sample | The deployment unit is a user request. Arms/versions on the same sample are repeated measures, not new evidence. |
| Per-proposal / per-generation guard decisions | **Proposal (generation)**, clustered by sample | Report per-proposal counts AND per-sample counts side by side; CIs by cluster bootstrap over samples | A sample with 3 proposals must not count 3× as much as a sample with 1. |
| Per-argument prover/guard verdicts | **Argument**, clustered by sample and call | Same dual reporting | Arguments inside one call/sample are correlated. |
| WER / entity error | **Sample** (then token-pooled as secondary) | Mean per-sample WER + pooled WER, both labelled | Token pooling alone hides short-utterance failures. |
| Latency | **Sample** | p50 / p95 / max over samples, never a mean alone | A mean hides the samples that breach the 30 s limit. |

**Pooling bans:** never pool V10 + V11 + V13; never pool arms (native vs
text vs control); never pool gold-transcript and ASR-transcript cells; never
pool decision-test with validation. Each cell gets its own row, its own n,
its own CI. A pooled number is admissible only as a clearly-labelled
meta-summary with the per-cell rows printed above it.

### 4.2 Paired comparison (the only comparison that supports adoption)

- Candidates and baseline run on the **same** decision-test samples, same
  decoding (temperature 0.0, seed 42), same transcript cell (§6).
- Report per-sample paired differences (candidate − baseline) for the
  primary metric, with a **paired bootstrap 95% CI** (10,000 resamples over
  samples, seed 1337, reported with the seed) and a McNemar-style
  discordant-pair table (baseline-correct/candidate-wrong vs
  baseline-wrong/candidate-correct). A mean improvement whose CI includes 0
  is **not** an improvement under this protocol, however large the point
  estimate.
- Pre-registered adopt bar (§8.4): primary-metric improvement ≥ +3pp with
  the 95% CI excluding 0, **and** no stratum regression > 5pp on any of
  {ask_only, empty, ask_mixed} (§2.1 strata), **and** guard false-block
  conditions (§5.4) satisfied. A mean gain bought by collapsing ask/empty
  behaviour is a rejection, not an adoption.
- **Multiple comparisons:** the decision-test is spent once per candidate.
  Testing k candidates on it and reporting the best is selection bias; the
  protocol allows at most **two** decision-test evaluations per direction
  family (one pilot read + one final read, both recorded), and any further
  read requires a fresh split/seed and burns the old decision-test for that
  family. Pilot reads are labelled as such and never headlined.

### 4.3 Gold-call match is not enough: the additional checks

A candidate that reproduces gold calls can still be wrong. Every
decision-test report must include, per sample, in addition to the proxy
score:

1. **Prerequisite satisfaction at the model prefix.** For each gold write
   that requires a prior read/search (E1's prerequisite relations, computed
   from the gold trajectory: the gold prefix reads/searches that establish
   the write's arguments), check whether the **model's own prefix** (calls
   the model actually made before this write, in this run) contains an
   equivalent read/search (same tool, same identifying argument, succeeded).
   Report `prereq_satisfied_rate` = satisfied / applicable gold writes.
   A write that matches gold but skips its prerequisite is scored as
   **prerequisite-failed**, not correct, in this diagnostic — even if the
   proxy score counts it. (This is the check V10 failed: proxy rose while
   prerequisites fell.)
2. **Intent / ask correctness.** Confusion table on gold kind:
   gold ask_only → model asks (correct) vs writes (wrong) vs empty (wrong);
   gold empty → model empty (correct) vs any call (wrong);
   gold act → model acts (then §4.3.1/§4.3.3 decide correctness).
   Report ask precision (model asks that gold asks) and ask recall (gold
   asks the model asks) separately. An ask is **not** a free pass: asking
   when gold acts is an error of the same standing as writing when gold asks.
3. **State-hash vs F1 decomposition (four numbers, always together).**
   (a) state-hash exact rate; (b) proxy score (F1 gated by hash);
   (c) raw tool-call F1 ignoring the hash gate; (d) write-only F1
   (reads excluded from both submission and gold before F1 — this removes
   the read-dilution penalty: write-only 1.0, +1 read 0.6667, +2 reads 0.5
   under the current proxy). Each answers a different question: (a) did the
   world end right; (b) the reported proxy; (c) did the calls look right
   even when state diverged; (d) did the writes look right ignoring the
   read policy. A candidate that improves (b) only by emitting fewer reads
   (gaming dilution) will show it in (d) staying flat — that is a rejection
   signal, not a win.
4. **Termination / stop correctness.** Report: extra-call rate (submitted
   calls beyond gold count, per sample), no-call-when-gold-acts rate, and
   repeat-call rate (same call repeated within a run — the agent's
   max_repeats = 2 guard interacts here; report repeats that hit the guard).
5. **Schema / simulator standing.** Report rejected-call rate (calls in
   `get_tool_calls()` that the simulator rejected — note: rejected calls
   **are** in the submission trace and dilute F1) and
   ok-True/done-False rate (calls that "succeeded" vacuously — app
   exceptions that return ok True / done False and leave state unchanged).
   A candidate whose F1 falls because of rejected calls has a format
   problem, not a planning problem; the fix differs, so the diagnosis must
   differ.

## 5. Guard evaluation (shadow first, veto last, both rates always)

### 5.1 Method: paired guard on/off on identical model outputs

- Run the candidate model **once**; save its full proposal trace.
- Evaluate the guard twice over the saved trace: (i) shadow mode — log
  every guard decision, veto nothing, model output stands; (ii) veto mode —
  apply the guard's veto (block → ask) and re-score the resulting
  submission. The guard's effect is then isolated from the model's effect:
  any difference between (i) and (ii) is the guard, not the model.
- Never compare "model A + guard" against "model B without guard" and
  attribute the difference to either component.

### 5.2 Adjudication categories (one per proposal, mutually exclusive)

| Category | Definition |
|---|---|
| correct_block | Guard blocked a proposal that is wrong (gold-inconsistent: wrong action, wrong reference, wrong argument, missing slot, prerequisite skipped — adjudicated against gold + the §4.3 checks, not against the guard's own verdict). |
| false_block | Guard blocked a proposal that is correct (matches gold call **and** passes §4.3.1/§4.3.2). |
| correct_pass | Guard passed a correct proposal. |
| miss | Guard passed a wrong proposal. |
| out_of_scope | Proposal's monitored slots do not cover the call (e.g. threshold_kwh, channel, free-text args, missing time) — the guard is silent by design here; counted separately, never as pass or miss. |
| unadjudicated | Insufficient evidence to adjudicate (e.g. history unparseable, gold class ambiguous). Counted and reported; a high unadjudicated rate invalidates the other rates' denominators and must be fixed before any guard claim. |

Per-sample counts accompany per-proposal counts (§4.1). "Independent
positive" accounting follows the Round 3 precedent: repeated generations of
the same situation (e.g. train_0004 light_set across arms/versions) count as
**one** independent positive situation, not several. Report both the raw
count and the de-duplicated-by-sample-and-situation count.

### 5.3 Metrics and the precision relabelling ban

- **Deployment-relevant number: false-block rate** =
  false_blocks / (false_blocks + correct_passes) over adjudicated correct
  proposals — i.e. the fraction of correct proposals the guard would veto.
  Report with Wilson 95% CI and its denominator. This is the number that
  decides veto promotion (§5.4).
- Block precision = correct_block / (correct_block + false_block) and block
  recall = correct_block / (correct_block + miss) are reported **only on
  the adjudicated subset**, labelled as such, with their denominators.
- **Ban (Round 3 finding 6-PR):** do not report `1 − false-block rate` as
  "precision". On gold replay, synthetic true positives equal applicable by
  construction, so that "precision" is just a relabelling of the pass rate
  with zero detection information. The only guard precision that means
  anything is block precision on real model proposals (§5.2), where wrong
  proposals actually exist.
- Gold-replay false-block rate and model-proposal false-block rate are
  **different quantities** (gold calls are correct by definition; model
  proposals mix correct and wrong). Report both, never substitute one for
  the other. Round 3's 1.54% is the gold-replay figure; the model-proposal
  figure is still to be measured on decision-test proposals (V10/V11/V13
  shadow gives the method, but those traces are 8–20 samples and
  ask-heavy — not a decision-test estimate).

### 5.4 Guard promotion rule (pre-registered)

- Shadow mode is mandatory for every candidate; veto mode is reported for
  information even when not promoted.
- **Veto (hard-enforce) promotion requires all of:** (a) model-proposal
  false-block rate ≤ 2% on decision-test proposals (Wilson upper bound
  ≤ 5%); (b) correct_block > 0 on at least 3 independent situations
  (de-duplicated, §5.2 — the current count is 1, which fails this bar);
  (c) no stratum's false-block rate exceeds 5% (a guard that vetoes
  phone_number calls at 89% — the pre-log-source Round 3 figure for
  phone-only gold calls — would fail here even if the overall rate passed);
  (d) out-of-scope rate reported, not hidden.
- **Phone_number branch carve-out (from Round 3 gold measurement):** even
  after the call-log source (fires 21 → 15 on gold replay), 11 residual
  phone-only gold calls still fire: user-spoken digit-word numbers,
  history-text numbers, and message-content numbers, which the gate cannot
  see without text evidence. Until text evidence exists, the phone_number
  branch is **shadow-only**: veto promotion for other reference types does
  not extend to phone_number calls.
- Existence ≠ disambiguation (Round 3 finding 6-EX): the guard proves a
  reference exists or a value derives — never that the model chose the
  right entity among several. Every guard table carries the qualifier
  "conditional on the call's own ids".

## 6. ASR vs LLM ablations (separate controls, no confounding)

### 6.1 Factorial cells (each cell = one full run on the same sample set)

| Cell | Current-request transcript | History transcripts | Model / config |
|---|---|---|---|
| G0 | gold | gold | zero-shot baseline |
| A0 | ASR (small) | ASR (as recorded in data) | zero-shot baseline |
| A1 | ASR (medium, if budget allows: 0.769 + 4.0 = 4.769B < 6B) | ASR (as recorded) | zero-shot baseline |
| G1 | gold | ASR (as recorded) | zero-shot baseline (= E0's design: gold current, ASR history) |
| C-* | gold, then ASR | as in the matching baseline cell | candidate direction |

- **Every cell names its transcript type in its label.** A result reported
  as "the model scores X" without the transcript cell is inadmissible.
- The candidate's ASR benefit (or harm) is measured as (C_ASR − C_gold) −
  (A0 − G0): the candidate's ASR gap minus the baseline's ASR gap. A
  candidate that merely inherits the baseline's ASR gap has not fixed ASR.
- History transcripts: the data's recorded history is ASR output (E0's
  design kept it). Any cell that replaces history transcripts with gold
  must be labelled a **different cell**, not a variant of the same cell.

### 6.2 ASR-only measurements (CPU-measurable on dev, no GPU needed for WER)

- Overall WER (gold current transcript vs ASR transcript) per sample +
  pooled; per-sample WER distribution (mean hides short-utterance failures).
- **Entity-span error rate:** WER restricted to spans carrying slot values —
  person names (roster names), digit sequences (phone/amount), time/date
  expressions, and negation/conditional markers (không, chưa, nếu, khi,
  trừ khi, …). Rationale: a 5% overall WER concentrated in entities is a
  planning bottleneck; a 15% WER in filler words is not. Report both.
- **Attribution (the only ASR-bottleneck claim this protocol allows):**
  per sample, compare G0 vs A0 outcomes: ASR-attributable failure =
  G0 correct and A0 wrong; LLM/planning failure = both wrong; ASR-luck =
  G0 wrong and A0 right (counted separately, never netted against
  ASR-attributable failures — netting hides both effects).
  "ASR is (not) the bottleneck" may only be stated as: "in cell pair
  (G0, A0) on sample set S, ASR-attributable failures are k/n samples
  (list of error classes), vs LLM-attributable m/n". E0 alone cannot
  support any broader sentence.

### 6.3 What ASR work must show before it is adopted

- An ASR change (checkpoint, decoding, hotwords/initial_prompt, rescoring)
  is adopted only if it reduces **entity-span error rate** and does not
  increase ASR-attributable failures on decision-test, under the paired
  analysis of §4.2. A WER-only improvement with flat entity-span error is
  reported as "transcription gain, no planning gain" and does not adopt.
- Hotwords / initial_prompt conditioning (a round-4 proposal) must be
  measured for **overcorrection**: samples where the conditioned transcript
  is worse than the unconditioned one (entity changed toward a hotword it
  is not). Overcorrection rate is a mandatory column in any ASR report.

## 7. Constraints compliance checklist (UNVERIFIED = ask, not assume)

| # | Rule (as stated for LifeMate) | Status | Evidence / procedure | If UNVERIFIED: exact question for organisers |
|---|---|---|---|---|
| C1 | System total < 6B params; LLM < 5B | Configured ✓ (4.244B / 4.0B) but counting rule UNVERIFIED | Repo counts total incl. embeddings (the safe rule). Any candidate must state its count under **both** total and non-embedding counting and pass under both until clarified. | Q-L1: Does the 6B/5B count include embedding parameters? Does it count the ASR model, the LLM, and any router/embedder/verifier separately or as one total? |
| C2 | Checkpoint released before 2026-10-26 | Baseline ✓ (Qwen3-4B-Instruct-2507 rev cdbee75; PhoWhisper-small rev a86b604c346caf7148c37512eafe783a16420adb — dates to be re-confirmed from the model cards at submission time) | Record base revision + date for every candidate. | Q-L2: Is a fine-tune of a pre-cutoff base eligible, or must the **derived checkpoint itself** be released before 2026-10-26? (This decides whether SFT is submittable at all.) |
| C3 | Context ≤ 16,384 tokens | Verifiable by audit | Token-count audit on decision-test prompts (max and p99, with the exact tokenizer of the submitted LLM); any candidate that changes prompt/serialization re-runs the audit. | — (auditable; no question needed unless the audit exceeds the limit, in which case the candidate is rejected, not the rule questioned). |
| C4 | Deterministic decoding | Configured (temp 0.0, seed 42) with a caveat | vLLM greedy decoding is deterministic in principle but batching/quantisation can vary outputs; the submission must state backend + version + whether outputs were verified identical across two runs on decision-test. | Q-L3: Is vLLM permitted as the serving backend in the offline Docker image, and is XGrammar/structured output permitted? (Previously listed under Q-L/Q-D, never sent.) |
| C5 | Fully offline (Docker, no network) | Procedure-defined | Submission Dockerfile built and run with network disabled; any weight/tokenizer download at runtime is a failure. All weights vendored in the image. | — (testable; no question unless the image requires a download). |
| C6 | ≤ 30 s / sample on 1× A30 | **BLOCKED — no measurement exists** | Measure on an A30 only: warm-up run excluded, per-sample wall time incl. ASR + LLM + guard, p50/p95/max over decision-test, sample count stated. | Q-L4 (only if A30 access is unavailable): Is the per-sample limit measured wall-clock per sample or amortised over the run? (Do not assume either.) |
| C7 | Open-source models only | UNVERIFIED in detail | "Open-source" vs licence: a research-only or CC BY-NC licence (the xLAM-2-3b-fc-r signal from round-4 research) may fail an open-source rule even if weights are downloadable. Record licence for every candidate component. | Q-D1: Which licences satisfy the open-source rule? Is a research-only / non-commercial licence eligible? |
| C8 | Single submission format / parser contract | Partially verified (branch parser: native tool calls + registered pseudo-call prefix) | Any candidate that changes serialisation must state its parser contract and prove (unit tests + decision-test traces) that the runtime parser accepts exactly what training emits. Training/runtime serialisation mismatch is a known failure mode (Thread A audits it). | Q-L5: Is the pseudo-call / native-call parser contract part of the official evaluation, or may a submission define its own output format as long as tool calls execute? |

**Resource estimation rule (binding):** no latency, throughput, or GPU-hour
number may be quoted from Kaggle T4x2 FP16 logs as if it were A30 evidence.
Anything unmeasured is labelled **ESTIMATE** (with its basis: e.g. "scales
linearly in samples from the decision-test run, constant unknown") or
**BLOCKED** (no basis at all). The GPU chain (§8) expresses budget in
runs × samples, not hours, until an A30 measurement exists.

## 8. Minimal GPU experiment chain (for Codex to implement later)

Order matters: each stage's gate must pass before the next stage starts.
A failed gate stops the chain; the failure is reported, not routed around.
All stages use temperature 0.0, seed 42, and the §6 cell labels. Sample
counts are decision-test counts unless stated otherwise.

### 8.0 Stage 0 — Freeze and establish decision-test baselines (no candidate)

- **Arms:** baseline config (`lifemate/configs/baseline.json`) on
  inner decision-test (n = 186) in cells G0 (gold current + gold history),
  G1 (gold current + ASR history), A0 (ASR small, as recorded).
- **Also:** gold-replay (CPU, `replay-gold`) on decision-test to verify the
  scorer path end-to-end (state-hash exact rate must be 1.0 on gold replay;
  anything less is a scorer/simulator bug, not a model result — stop).
- **Outputs:** per-sample primary metric + §4.3 diagnostics + §6.2
  attribution table (G0 vs A0) + token-count audit (§7 C3) + (on A30, when
  available) per-sample latency p50/p95/max.
- **Gate:** pipeline runs end-to-end with zero missing outputs and zero
  unadjudicated guard rows attributable to tooling (missing evidence from
  the model itself is fine and counted). No numeric gate vs old full-dev
  numbers — the sample set differs, so old numbers are not a target.

### 8.1 Stage 1 — ASR ablation (decides whether ASR work is on the critical path)

- **Arms:** A1 (ASR medium) vs A0 on decision-test, same baseline model.
  (Budget check first: 0.769 + 4.0 = 4.769B < 6B ✓ under repo counting;
  re-check under §7 C1's both-countings rule.)
- **Metrics:** entity-span error rate, ASR-attributable failure share
  (§6.2), primary metric paired difference A1 − A0 (§4.2).
- **Gate / branch:** if ASR-attributable failures are ≥ 10% of decision-test
  samples **and** concentrated in entity/negation classes, ASR work joins
  the critical path (Stage 3's candidate must include an ASR arm). If below
  10%, ASR work is deprioritised and the chain proceeds to the LLM-side
  candidate; the ASR result is still reported (a negative result is a
  result). Either way, Stage 1 does not adopt an ASR checkpoint by itself —
  adoption needs the §4.2 paired bar on the primary metric.

### 8.2 Stage 2 — Guard shadow on baseline outputs (no veto, no model change)

- **Arms:** guard (Round 3 code, shadow mode) over Stage 0's saved A0
  proposals; adjudicate per §5.2.
- **Metrics:** correct_block / false_block / correct_pass / miss /
  out_of_scope / unadjudicated (per-proposal and per-sample), model-proposal
  false-block rate with Wilson CI, de-duplicated independent-positive count.
- **Gate:** if model-proposal false-block rate > 5% (point estimate), the
  guard stays shadow-only and any veto proposal for that reference type is
  rejected for this round. If unadjudicated rate > 10%, fix adjudication
  evidence before any guard claim (do not proceed to veto discussion).

### 8.3 Stage 3 — Candidate pilot (one direction, inner-val iteration only)

- **Candidate:** whichever direction Threads A+B and the main synthesis
  select (SFT or alternative). The candidate is trained / built using
  **inner-train only** (n = 866). Iteration (early stopping, checkpoint
  choice, prompt tweaks) uses **inner-validation only** (n = 185).
- **Arms on inner-validation:** baseline vs candidate, cells G1 and A0
  (gold-current and ASR cells — a candidate that wins only on gold
  transcripts has not solved the deployed setting).
- **Stop rules (any one stops the pilot):** (a) validation primary metric
  degrades vs baseline for two consecutive checkpoints (early-stop signal,
  not a reason to try a third unrecorded checkpoint); (b) candidate's
  ask_only or empty stratum regresses > 5pp vs baseline on validation;
  (c) candidate exceeds any §7 constraint (context, budget) — rejected, not
  trimmed silently; (d) training diverges / loss NaN — reported, not
  re-run with silently changed hyperparameters (hyperparameter changes are
  recorded as new pilot variants, each with its own validation read).
- **Output:** one frozen candidate (config + checkpoint + prompts +
  serialisation contract recorded) and its validation numbers. No
  decision-test read happens in this stage.

### 8.4 Stage 4 — Decision read (once per direction family)

- **Arms:** frozen candidate vs baseline on inner decision-test (n = 186),
  cells G1 and A0, guard in shadow mode over both traces (Stage 2 method).
- **Metrics:** §4.2 paired analysis + §4.3 diagnostics + §5 guard table.
- **Adopt (all required):** primary-metric improvement ≥ +3pp with paired
  bootstrap 95% CI excluding 0 in **both** G1 and A0 cells (a gold-only win
  does not adopt); no stratum regression > 5pp on {ask_only, empty,
  ask_mixed}; guard shadow false-block rate ≤ 2% point estimate with
  Wilson upper bound ≤ 5% (veto promotion additionally needs §5.4's
  independent-positive bar); §7 constraints all satisfied or explicitly
  waived by an organiser answer (recorded).
- **Reject (any one suffices):** CI includes 0; gold-only win; stratum
  regression; guard violation; constraint violation. Rejection is reported
  with the paired table, not as "no improvement observed" without numbers.
- **Pilot-read allowance:** one additional decision-test read per direction
  family is permitted for a pre-registered fix of a tooling bug (not a
  modelling change); it is labelled "pilot read (tooling fix)" and the
  final read remains the adopting one. Any further read burns the
  decision-test for that family (§4.2).

### 8.5 Stage 5 — Post-freeze verification (held-out 308, once, no tuning)

- Only after Stage 4 adoption: freeze everything, run once on held-out 308
  (cells G1 and A0), report all §4.3/§5 numbers as-is.
- **No feedback loop:** no tuning, no threshold change, no prompt change
  may follow from Stage 5. A contradiction with Stage 4 is reported under
  §2.4's rule (re-opening development requires a fresh split/seed and burns
  the old decision-test for that direction).

### 8.6 Chain budget (in runs × samples, not hours)

- Stage 0: 3 cells × 186 = 558 model runs + gold replay (CPU).
- Stage 1: 1 cell × 186 = 186 runs (plus ASR transcription of decision-test
  current requests with the medium checkpoint if not already cached).
- Stage 2: 0 model runs (re-uses Stage 0 traces; CPU adjudication).
- Stage 3: training on 866 + validation reads (count checkpoints, not
  samples, as the budget unit — record checkpoints evaluated).
- Stage 4: 2 cells × 186 × 2 arms (baseline + candidate) = 744 runs.
- Stage 5: 2 cells × 308 = 616 runs (once).
- Wall-clock / GPU-hour totals: **BLOCKED** until an A30 per-sample latency
  is measured (§7 C6). Do not convert T4x2 timings into A30 hours.

## 9. Reporting template (every stage report must contain these sections)

1. Sample set, n, split seed, manifest hash; transcript cell label per row.
2. Config identity: checkpoint + revision, prompt/serialisation version,
   decoding, guard mode (shadow/veto/off), scorer version.
3. Primary metric + paired CI + discordant table (or "not a decision read"
   label for validation/pilot numbers).
4. §4.3 diagnostics (prerequisite rate, ask confusion, four-number
   decomposition, termination, simulator standing).
5. §5 guard table (if the guard ran) with denominators and the
   false-block rate, never a relabelled precision.
6. §6 attribution (for any ASR claim) and §7 constraint checklist status.
7. Stratum breakdown (act / ask_mixed / empty / ask_only) with n per stratum.
8. What was NOT run, and why (e.g. "held-out untouched per §2.4").

## 10. Unknowns and blockers (explicit, not buried)

1. **Official evaluator absent.** Every score here is a proxy with known
   UNVERIFIED scorer choices (§1.1). If the official evaluator excludes
   reads from F1 or scores asks specially, read-policy and ask-policy
   conclusions change. Mitigation: always report the §4.3 decomposition so
   the conclusion can be re-read under either scorer.
2. **SFT submittability (Q-L2).** If a derived checkpoint is ineligible,
   the SFT direction is unsubmittable regardless of its decision-test win.
   This question should be sent before Stage 3 trains anything (it costs
   nothing to ask early and everything to learn late).
3. **Param counting (Q-L1) and serving backend (Q-L3).** A candidate that
   passes under repo counting but fails organiser counting (or needs
   XGrammar that is disallowed) is rejected at submission, not at Stage 4.
   Ask early; design candidates to pass under both countings where possible.
4. **A30 latency (C6) BLOCKED.** No number in this protocol estimates it.
   The chain's wall-clock cost is unknown until Stage 0 measures it on an
   A30. Any schedule built on T4x2 timings is fiction.
5. **Friend SFT artifacts unaudited (404, no access).** No conclusion about
   "fine-tune quality" from that source is admissible (§1.2). If access
   arrives, Thread A's audit checklist applies before any number from it
   enters a comparison.
6. **Small decision-test strata.** ask_only n = 7 and empty n = 14 on
   decision-test: stratum regressions on these cells are noisy. The protocol
   keeps the > 5pp stratum gate (§8.4) but requires the paired table to be
   inspected before a stratum gate alone rejects a candidate (a 1-sample
   swing in ask_only is 14pp — the gate must be read with its n, not
   applied blindly).
7. **History-transcript provenance.** History turns in the data are ASR
   output; their error rate vs gold history is unmeasured (no gold history
   transcripts exist in the data). Any cell using ASR history inherits an
   unquantified error source — reported as a limitation on every G1/A0
   result, not assumed away.
8. **Template vs behaviour leakage asymmetry (§1.3).** Text templates are
   near-unique but behaviour templates repeat heavily. A random inner split
   measures "new requests, familiar behaviours". Truly unseen behaviours
   are estimated only by the underpowered `test_unseen_seq` slice (§3.7).
   Do not overclaim generalisation from the primary number alone.

## 11. Evidence ledger (what Thread C actually read)

- `lifemate/configs/baseline.json`, `lifemate/configs/recommended.json` —
  checkpoint/revision/decoding/budget (§1.1).
- `lifemate/scoring.py` (docstring + matching rules) — proxy definition and
  its UNVERIFIED items (§1.1, §4.3).
- `lifemate/config.py` — PipelineConfig defaults, budget assertions.
- `lifemate/splits/train_dev_heldout.json` — counted values only
  (dev 1237 / held-out 308); **no held-out row opened, no held-out id listed
  in this document**.
- `lifemate/run.py` — subcommands (`replay-gold`, `score`, `make-split`,
  `infer`, `check-submission`, `fake-run`) and `--ids-file` selection,
  cited for the Stage 0/4/5 run pattern.
- Train data, **dev rows only** (filtered by the split file before any
  analysis): `~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl`
  and `train_tools_catalog.json` (147 tool specs, kind field) — for §1.3
  statistics and the §3 overlap procedures. No raw data, audio, or
  held-out content is copied into this document.
- `/tmp/t3_v10_shadow.json`, `/tmp/t3_v11_shadow.json`,
  `/tmp/t3_v13_shadow.json` (summaries + row counts) — guard shadow
  baselines (§1.2, §5); row-identical claim verified against the Round 3
  paired re-run record (14/14, 10/10, 29/29).
- `research/lifemate/round10-fix-report-round3.md` (present in the clone) —
  Round 3 guard numbers, phone-branch findings, 6-PR/6-EX corrections.
- Prior-result values (E0/V10/V11/V13, guard rates, friend-harness numbers)
  are taken from the task context's verified summary, labelled with their
  evidence class in §1.2, and were **not** re-derived by Thread C (no GPU,
  no re-run).
- **Not read / not verified by Thread C:** the friend SFT repo (404, no
  access); organiser rules beyond the repo's own statements (all such rules
  are marked UNVERIFIED in §7); any A30 or T4 timing log (none available to
  this thread — hence §7 C6 BLOCKED, not estimated).
- **Git note:** the local clone's HEAD reports `8d4721e` (stale vs the
  branch state in the task context: Round 3 branch commit `61d84390`,
  main `219d7fec`). Thread C performed no git operation and cites branch
  commits from the task context, not from the local clone. No file outside
  this document was created or modified by Thread C.

## 12. Reproduction commands (procedures, not runs)

```bash
# Dev statistics for §1.3 (dev rows only; the filter must precede analysis)
python3 - <<'EOF'
import json
split = json.load(open("lifemate/splits/train_dev_heldout.json"))
dev_ids = {k for k, v in split.items() if v == "dev"}
# ... analyse only rows whose id is in dev_ids; never print held-out ids
EOF

# Inner-split manifest (to be generated by main/Codex; Thread C did not create it)
# Inputs: dev ids, stratum table §2.1, seed 1337, §3 checks as assertions.
# Output: analysis/overnight_capability_audit/inner_split_seed1337.json
#   {sample_id: "inner_train" | "inner_val" | "inner_test", ...}
#   + {generator command, stratum counts, overlap-check report}

# Stage 0 baseline (pattern; exact --config/--ids-file flags per lifemate/run.py)
python3 -m lifemate.run infer --data <extracted dir> --split train \
  --config lifemate/configs/baseline.json --ids-file <inner_test_ids.txt> \
  --out <stage0_baseline_test.json>
python3 -m lifemate.run score --data <extracted dir> --split train \
  --submission <stage0_baseline_test.json> --out <stage0_scores.json>
python3 -m lifemate.run replay-gold --data <extracted dir> \
  --out <stage0_gold_replay.json>   # state-hash exact rate must be 1.0

# Guard shadow over saved proposals (pattern from the Round 3 paired re-run)
python3 analysis/model_trace_shadow.py --trace <saved_trace.json> --version <v> \
  --train-jsonl <train.jsonl> --split lifemate/splits/train_dev_heldout.json \
  --out-json <shadow_out.json>
```

---

*Thread C deliverable ends here. Synthesis, direction selection, and any
push are the main thread's responsibility; this document proposes no
direction and adopts no candidate.*
