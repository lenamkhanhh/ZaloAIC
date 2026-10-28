# Thread B — Methods research for the LifeMate capability audit (overnight)

**Thread:** B (methods only). No coordination with Threads A/C; synthesis is the main thread's job.
**Scope discipline:** No training, no model inference/GPU, no paid models/APIs, no Kaggle
actions, no git operations, no changes to inference / simulator / scorer / guard /
benchmark config, no held-out data (held-out samples were not opened at all).
**Baseline facts used (from the task brief, not re-derived):** 147-tool simulator
catalog (write 84, read 62, meta 1); baseline PhoWhisper-small + Qwen3-4B-Instruct-2507
= 4.244B; constraints system <6B, LLM <5B, context ≤16,384 tokens, ≤30 s/sample on
1× A30, fully offline, deterministic decoding, open-source models released before
2026-10-26. Organizer questions (checkpoint eligibility of derived weights, vLLM /
XGrammar permission, parameter counting, Q-L/Q-D) are **UNVERIFIED** — nothing below
treats them as settled.
**Date of research:** 2026-10-29. Sources are cited with the version/date actually read;
anything not read in this thread is marked as such.

## 0. The decision this thread informs, and its single most important correction

The question is not "does SFT work in general" but "which learning signal fixes
*our* errors, in *our* harness, under *our* caps". The error inventory that methods
must map to (from real traces, per the brief):

| # | Real error class | What is actually known about it (scoped) |
|---|------------------|------------------------------------------|
| E1 | **FILL-ACT** | E5 V13: targets 0/7 → 1/7; the model fills a missing time from context (current_time, next-round hour, unrelated history) so "ask when missing" never fires. Decisive nuance: E5 ran with the **gold current transcript** in the evaluated arm family, so fill-act is primarily an **LLM decision error**, not an ASR error. Any method that only fixes transcription cannot claim to fix E1. |
| E2 | **Format / pseudo-call failures** | E6-C V11 confirmed **channel-scope only** (narrow lowercase `app.tool(` prefix). The rest of the format failure family is unmeasured. |
| E3 | **Prerequisite skipping** | E1: prerequisite score 5/21 → 4/21 after format fixes — format work did **not** improve it. Reading/searching before writing is a planning failure, not a syntax failure. |
| E4 | **Intent-wrong but existence-valid calls** | G2 passes them by design: the guard checks existence/derivation, not entity choice. No method that only proves existence fixes E4. |
| E5 | **Monitored-slot gaps** | threshold_kwh, channel, free text are outside guard scope by design. Guard work cannot fix these; only model-side or grammar-side work can. |
| E6 | **ASR errors, incl. history turns** | E0 kept ASR history while the current transcript was gold, and proxy stayed 0.125. That result says: *gold current transcript alone does not fix the proxy*. It does **not** say "ASR is not a bottleneck" — the history-ASR contribution is still unmeasured, and no slot-level ASR error attribution exists yet. |

**Old conclusions, re-scoped (do not quote them unscoped):**

- "Prompt/format work hit its ceiling" — FALSE as a general claim. What is true:
  format work improved a narrow channel (E6-C) and did not move prerequisites
  (E1 5/21 → 4/21). The ceiling claim was never tested on the decision classes
  E1/E3/E4.
- "ASR is not a bottleneck" — UNPROVEN. E0's design cannot support it (see E6).
- "Fine-tune is bad" — UNPROVEN for LifeMate. The only fine-tune numbers in
  context are a friend's harness/split (not comparable, SFT effect not isolated)
  and an inaccessible private repo (audit stopped). No SFT has been run or
  measured in this repo's harness. Treat "SFT bad" as an open question, not a fact.

## 1. The three deep directions (at most three, as instructed)

### Direction 1 — Simulator-verified trajectory SFT (STaR / RFT style, APIGen verification ladder)

**Idea.** Train on trajectories that *provably* end in the gold simulator state,
not on trajectories that merely look like gold. Two sources, both inside dev 1237:
(a) gold trajectories replayed through ToolEnv and kept only if the final
state-hash matches gold; (b) self-generated trajectories (sampled from the current
model at temperature > 0, greedy eval untouched) kept only if they also reach the
gold state-hash **and** satisfy the ask-shape / prerequisite checks (the same
checks Thread C / the guard already implement on CPU). This is STaR's loop
(generate → keep only what reaches the right answer → fine-tune → repeat) with
the "right answer" replaced by a *simulator-verified final state*, and APIGen's
verification ladder (format check → actual execution → semantic check) with the
simulator as the execution oracle.

**Primary sources (read this thread).**

- STaR, Zelikman et al., arXiv:2203.14465v2 (20 May 2022). Loop: generate
  rationales few-shot; if wrong, rationalize *given* the correct answer;
  fine-tune only on rationales that yielded correct answers; repeat. Source
  result (math/commonsense QA, not tool use): beats direct-answer fine-tuning
  and approaches a 30× larger model on CommonsenseQA. **Inference for LifeMate:**
  the rationalization step maps to "given the gold state, generate the missing
  read/ask prefix" — but rationalized trajectories must still pass the
  simulator replay, otherwise rationalization manufactures false-positive
  paths (the same failure mode the ReSTEM paper warns about: rationalization
  increases false-positive solutions with correct answers but wrong reasoning).
- RFT, Yuan et al., arXiv:2308.01825v2 (13 Sep 2023). Rejection sampling on an
  SFT model, keep correct reasoning paths, fine-tune the base model on them.
  Source results: LLaMA-7B GSM8K 35.9% (SFT) → 49.3% (RFT, multi-model samples);
  the key factor is the *number of distinct correct paths*, and gains are larger
  for weaker models. **Inference for LifeMate:** distinct-path count is the
  metric to track for the self-generated pool (deduplicate by tool-sequence +
  final state, not by surface text); a pool of near-identical gold copies adds
  little.
- APIGen, Liu et al., arXiv:2406.18518 (NeurIPS 2024). Three-stage verification:
  format checking → actual function execution → semantic verification; 3,673
  executable APIs, 60k released entries (Salesforce/xlam-function-calling-60k,
  CC BY 4.0 per the downstream README cited in §5); 7B models trained on it
  reach BFCL state-of-the-art in their report. **Inference for LifeMate:** copy
  the ladder, not the data — our "actual execution" is ToolEnv replay, our
  "semantic verification" is state-hash + ask-shape + prerequisite checks, all
  CPU-side and already built in this repo.
- APIGen-MT, Prabhakar et al., arXiv:2504.03601v4 (19 Jul 2025). Two phases:
  verified task blueprints with ground-truth actions (committee review) →
  complete multi-turn trajectories via simulated agent–human interplay; 5k
  trajectories released (Salesforce/APIGen-MT-5k); xLAM-2-fc-r models (1B–70B)
  beat GPT-4o/Claude 3.5 on τ-bench and BFCL in their report, with smaller
  models *surpassing larger ones in multi-turn settings*. **Inference for
  LifeMate:** multi-turn trajectories (not single-turn call/response pairs) are
  the right training unit — our history turns are part of the input, and the
  ask/read/write decision at each turn is the label. Single-turn SFT data
  (Tool Zero §3: single-turn training fails to transfer to multi-turn) is a
  known failure mode to avoid.

**Error mapping.** E3 (prerequisite skipping) — directly: only trajectories
that perform the prerequisite read/search survive the filter, so the model sees
read-before-write as the *normal* pattern instead of an exception. E2 (format)
— directly: unparseable trajectories are rejected by the format stage. E4
(intent-wrong) — partially: a wrong-entity trajectory that still reaches the
gold state is a *false positive* of this filter (state-hash equality is
necessary, not sufficient, for intent correctness); it does not fix entity
choice. E1 (fill-act) — only weakly: gold ask trajectories teach the ask shape,
but SFT never *penalizes* the fill-act continuation, so the decision boundary
is not learned. That gap is exactly why Direction 2 exists. E5 (monitored-slot
gaps) — no: SFT data covers them only if gold trajectories contain them, and
the guard still cannot check them.

**Data needs.** Dev 1237 only (inner split per Thread C; held-out stays locked).
Gold trajectories (replay-verified) + self-generated rollouts (k samples per
dev sample at temperature > 0; k is a hyperparameter to pilot, not a claim).
No new human annotation. No model-generated data from paid models (banned);
rollouts come from our own 4B model.

**Compute needs (honest).** Rollout generation reuses the existing Kaggle T4×2
generation path (already used for V10/V11/V13); filtering is CPU-only. SFT cost
for a 4B model is **unmeasured in this repo** — no number is claimed here.
LoRA vs full fine-tune is an open choice for the pilot (LoRA reduces optimizer
memory and keeps the base weights intact, which matters for the derived-
checkpoint eligibility question; full fine-tune is the STaR/RFT default).
Codex must pilot on a small slice (e.g. one epoch on ~100 trajectories) and
report wall-clock + memory before committing to a full run. No A30 latency
number is claimed or extrapolated from T4.

**Training/inference contract sketch (for the main thread's brief).**
Serialization must be *byte-identical* to the runtime's native chat/tool format
(the same format the agent parses at inference); any train/serve skew here
repeats the E1 lesson (format work that does not transfer). Loss on assistant
turns only (tool-call tokens + ask-turn tokens); mask user turns, tool
observations, and system prompts — otherwise the model learns to *emit*
observations. Keep the existing 3-attempt / parser contract at inference
unchanged for the first comparison (change one thing at a time). Context:
multi-turn trajectories with full history can exceed 16,384 tokens; the pilot
must report the truncation rate and the truncation policy (drop oldest history
turns first, never drop the current request or the tool schemas).

**Disqualifiers / conditions that kill it.**
- If the derived-checkpoint eligibility question comes back "derived weights
  not allowed" from the organizers, D1 (and D2) are dead for submission
  regardless of proxy gains — this is the single biggest blocker, and it is
  UNVERIFIED. Ask before training, not after.
- If train/serve serialization differs, results are uninterpretable (do not
  run the comparison until the serialization is diffed).
- If the verified pool collapses to near-identical gold copies (distinct-path
  count ~1 per sample), RFT's own finding says gains will be small — add
  rollout diversity (temperature, k) before scaling epochs.
- If SFT improves inner-dev proxy but fill-act rate is unchanged, D1 has
  taught form, not decisions — escalate to D2 rather than training longer.

**Reproducibility.** STaR/RFT/APIGen/APIGen-MT papers + datasets are public
(see §5); the LifeMate-side pipeline (ToolEnv replay, state-hash, ask-shape
checks) already exists in-repo on CPU. No new checkpoint is proposed as a base
here — the base stays Qwen3-4B-Instruct-2507 (already in use; its exact
revision's licence file must be re-checked before any derived submission).

**Falsifier.** SFT on verified trajectories, evaluated on inner-dev with the
unchanged harness: if proxy does not move *and* prerequisite rate does not
move, D1 is rejected in favour of D2 + inference-side work (grammar/guard).
If proxy moves but fill-act does not, D1 is *partially* adopted (format +
prerequisite gains) and D2 becomes the priority for the decision boundary.

### Direction 2 — Act / ask / stop preference training on the model's own errors (Step-DPO + Hammer-style abstention negatives)

**Idea.** SFT teaches "what gold does". It does not teach "what not to do when
gold would ask". Direction 2 builds *pairs* from a shared prefix: the
**chosen** continuation is the verified-correct next step (ask turn, read-first
trajectory, or correct call); the **rejected** continuation is the model's own
observed failure from the same prefix (fill-act write with a hallucinated time,
wrong-entity call, prerequisite-skipping write). Optimize only the first
divergent step (Step-DPO), not the whole trajectory — because penalizing a
whole trajectory also penalizes its correct prefix, which is exactly the noise
Step-DPO was built to remove. Add Hammer-style abstention negatives: pairs
where the correct action is *not* to call (no suitable tool / missing required
argument) so the model learns the stop/ask side, not just the act side.

**Primary sources (read this thread).**

- DPO, Rafailov et al., arXiv:2305.18290 (2023). Directly optimizes the policy
  on (prompt, chosen, rejected) pairs via the policy/reference log-ratio, no
  separate reward model, no PPO loop. Source result: alignment quality
  competitive with RLHF at lower complexity. **Inference for LifeMate:** DPO
  is the cheapest preference method to pilot (same model + one reference copy);
  its failure mode for us is *off-policy pairs* — see Step-DPO below.
- Step-DPO, Lai et al., arXiv:2406.18629 (2024). Treats individual reasoning
  steps as the preference unit; optimizes only the first erroneous step
  against the correct step from the same prefix. Source results (math, 70B
  models): 10k step-wise pairs, <500 training steps, ~+3% on MATH; and the
  critical data finding: **self-generated pairs beat human- or GPT-4-generated
  pairs** because foreign data is out-of-distribution for the policy.
  **Inference for LifeMate:** pairs MUST come from our own model's traces
  (V10/V11/V13 + new rollouts) paired against verified corrections from the
  same prefix. Importing preference pairs from another model/harness is
  predicted to underperform — this is a falsifiable claim the pilot can check
  (but do not waste the pilot on it; build self-generated pairs first).
  Code + data: github.com/dvlab-research/Step-DPO (reported in the paper).
- Hammer, Lin et al., arXiv:2410.04587v2 (ICLR 2025). Two ideas: (i) function
  masking (randomize function/parameter names during training so the model
  reads descriptions, not names); (ii) an **irrelevance-augmented dataset**
  (7,500 instances where the correct function is deliberately excluded, label
  `[]` = call nothing) that teaches abstention. Source result: Hammer-7B
  83.92% on BFCL in their report, with masking-robustness (xLAM-1.3B-fc
  collapses under masking; Hammer-1.5B holds). **Inference for LifeMate:**
  copy the irrelevance idea, not the checkpoint (Hammer-7B is 7.61B — over
  our 5B LLM cap — and Hammer-2.0's base is Qwen2.5-Coder-7B, also over cap).
  Our irrelevance negatives are: required argument missing → ask (not a
  write); no suitable tool → stop/answer-without-call; prerequisite unmet →
  read first (not the write). Function masking is a *secondary* trick: it
  may help entity-choice robustness (E4) by forcing description-reading, but
  it changes the training serialization, so it must be piloted separately
  and never combined with D1 in the first run.
- Learning to Ask / Ask-when-Needed (AwN), Wang et al., arXiv:2409.00557v4
  (29 Apr 2026; abstract + v2 fragments read, full-text method details NOT
  re-read in this thread — see ledger). Core claim, directly on our E1:
  "due to the next-token prediction training objective, LLMs tend to
  arbitrarily generate the missed argument" — i.e. fill-act is the *default*
  behaviour of next-token training, not a quirk of our prompt. Their remedy
  is prompting (AwN) + a benchmark (NoisyToolBench) + ToolEvaluator. **Inference
  for LifeMate:** prompting alone was already tried in our E5 family and
  failed (0/7 → 1/7) — so AwN-as-prompting is *not* the proposal. The proposal
  is AwN-as-*training-signal*: the ask behaviour must be learned from pairs
  where fill-act is the rejected continuation, because the base objective
  actively rewards filling.
- SpeakRL, Acikgoz et al., arXiv:2512.13159v1 (15 Dec 2025; full text read
  §§1–3). GRPO with two verifiable rewards (format compliance + LLM-as-judge
  clarification quality), structured `<think>` / `<clarify>` tokens, user
  simulator, 25k synthetic SpeakER dialogues. Source results (MultiWOZ 2.4):
  base 25.63% → SpeakRL 46.17% success, turns 8.12 → 5.82; SFT 28.78% vs GRPO
  46.17%; DPO 45.73% vs GRPO 46.17%. **Two transferable claims, one
  non-transferable setup.** Transferable: (a) "SFT overfits to dialogue
  trajectories — imitating structure without learning when or why to ask" —
  this is the mechanism behind our E5 result and the reason D1 alone is
  insufficient; (b) turn count + ask quality must be measured alongside
  success, or the model learns to ask everything. **Not transferable:**
  their user simulator is Claude Sonnet 4 (paid, banned here) and their
  clarification reward is LLM-as-judge (paid, banned here). Our replacement:
  the deterministic simulator + gold ask-shape as the reward (ask = correct
  iff gold asks / the required argument is genuinely missing; act = correct
  iff state-hash matches). Do not cite their +20.5pt as an expected LifeMate
  gain — different task, different simulator, different scale.
- When2Call, Ross et al. 2025 (via secondary summaries + a follow-up paper's
  §1, not the original paper — see ledger). Four-way decision eval: call /
  answer directly / ask follow-up / abstain. Single-turn track: 3,109
  instances (1,226 call / 873 clarify / 1,010 abstain) after filtering.
  **Inference for LifeMate:** adopt the *taxonomy* for our own eval (Thread C),
  not the dataset (different tools, English, no simulator state). Every
  LifeMate decision can be labelled in these four classes, which is what
  makes ask-rate / over-ask measurable instead of anecdotal.

**Error mapping.** E1 (fill-act) — primary target: fill-act continuations are
the rejected side of the pairs. E3 (prerequisite skipping) — direct: the
rejected side is the write without its prerequisite read; the chosen side is
the read-first continuation from the same prefix. E4 (intent-wrong) — direct:
wrong-entity calls are rejected continuations; but note the limit — DPO
teaches "not this entity", it does not teach *which* entity is right beyond
what the chosen continuation shows; entity disambiguation still needs the
retrieval/roster evidence at inference. E2 (format) — indirect: format-failed
continuations can be rejected pairs, but grammar (surveyed below) is cheaper
for pure format. E5 (slot gaps) — partial: pairs can cover threshold_kwh /
channel / free-text decisions if gold trajectories contain them; the guard
still cannot verify them, so these pairs rely on state-hash alone.

**Data needs.** Same dev 1237 + own-model rollouts. Pair construction (CPU,
from existing traces + new rollouts):
- Fill-act pairs: prefix where a required argument is missing → chosen = gold
  ask turn (or a verified ask turn reaching the same state after the user's
  scripted answer — but note: our traces end at the ask; the "after answer"
  continuation is not in the data, so the chosen side is the ask turn itself,
  and the reward is ask-shape correctness, not downstream completion).
- Prerequisite pairs: prefix where gold reads first → chosen = the read,
  rejected = the model's direct write.
- Wrong-entity pairs: prefix where the model called the wrong entity →
  chosen = gold call, rejected = model call (same prefix, first divergent step).
- Abstention pairs (Hammer-style): missing-argument prefixes → chosen = ask,
  rejected = any write; no-suitable-tool prefixes → chosen = stop/answer,
  rejected = any write. **Balance requirement:** for every ask-chosen pair,
  include act-chosen pairs from prefixes where gold acts — otherwise the
  policy collapses to asking everything (SpeakRL's turn-count lesson; monitor
  ask-rate as a first-class metric, not an afterthought).
- Exclusion: pairs must not use held-out samples, must not use gold/sample-
  specific rules in runtime, and must not train on the evaluation slice
  (Thread C's inner split governs which dev samples may be trained on).

**Compute needs (honest).** DPO needs the policy + a frozen reference copy in
memory during training (2× 4B weights + optimizer states for the trainable
part; LoRA-DPO reduces this sharply). Exact memory/time is **unmeasured** —
pilot first (one DPO run on a few hundred pairs, report steps/sec + memory).
Inference cost is unchanged (same 4B weights, no extra model). No paid judge,
no frontier simulator.

**Training/inference contract sketch.** Reference = the D1 SFT checkpoint
(DPO-after-SFT, not DPO-from-base — DPO from the raw instruct model is
unstable in the literature and wastes the SFT investment). β (KL coefficient)
and the ask/act pair ratio are the two hyperparameters to sweep in the pilot;
do not present any value as tuned. Keep greedy deterministic decoding at eval.
Keep the guard OFF for the first D1-vs-D2 comparison (measure the model's own
decision boundary; the guard is a separate safety layer measured by Thread C),
then re-measure with the guard on as a second arm.

**Disqualifiers / conditions that kill it.**
- Derived-checkpoint eligibility (same UNVERIFIED blocker as D1).
- If pair construction cannot produce enough *first-divergent-step* pairs
  (e.g. most failures share no prefix with a verified correction), Step-DPO
  degrades to whole-trajectory DPO and its credit-assignment advantage is
  lost — measure pair yield before training.
- If ask-rate inflates > X (threshold set by Thread C, not here) without
  proxy gain, the pair balance is wrong — fix balance, do not add more pairs.
- If DPO destabilizes format (parse failures rise), β is too low or the
  reference is wrong — stop, do not "train through it".

**Reproducibility.** DPO/Step-DPO/Hammer code and data are public (see §5).
The LifeMate-side pair construction is CPU work on existing traces; no new
infrastructure beyond a pair-builder script (main thread's scope, not this
thread's — this thread writes no code per its owned path).

**Falsifier.** On inner-dev with the unchanged harness: if fill-act rate does
not fall *while* ask-rate stays within the Thread C band and proxy does not
regress, D2 is rejected and the decision boundary is declared
prompt/guard/grammar territory, not learned-policy territory. If fill-act
falls but proxy does not rise (asks are correct but downstream completion
fails), the bottleneck has moved to the *post-ask* continuation — a different
problem (user-simulator / multi-turn completion) that needs its own design.

### Direction 3 — ASR decoding-side adaptation + slot-level error measurement (measure first, adapt without a new model)

**Idea.** Do not swap the ASR model yet and do not fine-tune it yet. First
measure *which* ASR errors change the LLM's decision, then fix only those
classes at decode time with zero new parameters: (a) session-conditioned
`initial_prompt` / hotwords from runtime-legitimate context (the sample's own
installed apps, history text, and — as a design question, not a decision —
the address book, which would require ASR-time state access the current
pipeline does not have); (b) n-best rescoring with slot-aware constraints
(digit-word → digit normalization, entity-lexicon preference); (c) explicit
handling of Vietnamese spoken numbers ("không chín tám bảy…" → digits) at the
transcript layer, because the phone-number residual in Round 3 shows
user-spoken digit-words are a real pattern the guard cannot yet handle.

**Primary sources (read this thread).**

- PhoWhisper, Le et al., ICLR 2024 Tiny Paper (OpenReview PDF, Table 2 read).
  PhoWhisper-small (244M): WER 11.08 (CommonVoice-Vi), 6.33 (VIVOS), 15.93
  (VLSP Task-1), 32.96 (VLSP Task-2). PhoWhisper-medium (769M): 8.27 / 4.97 /
  14.12 / 26.85. PhoWhisper-large (1.55B): 8.14 / 4.67 / 13.75 / 26.68. Trained
  on 843.79 h of Vietnamese speech. **Inference for LifeMate:** the
  small→medium step buys ~1.4 WER points on VIVOS and ~1.8 on VLSP-1 in their
  report — but those are *general* benchmarks, not LifeMate audio, and the
  medium swap (4.769B total) is already the "try now" combo from the earlier
  LLM/ASR selection research. Do not re-litigate the swap here; this direction
  is about what decoding-side work adds *on top of either* size, and whether
  it is worth doing before any fine-tune.
- Whisper decoding parameters (faster-whisper / Whisper docs, via secondary
  documentation read this thread): `initial_prompt` (text prepended as
  preceding context — style, spelling, vocabulary priming) and `hotwords`
  (terms to bias decoding toward). Both are *prompt conditioning only*, not
  hard constraints — they can overcorrect (the round-4 note already flags
  overcorrection measurement as mandatory). **Caveat for the pilot:** verify
  `hotwords` exists in the *pinned* faster-whisper version in the runtime
  before relying on it; `initial_prompt` is the safer, widely-supported knob.
  Overcorrection must be measured on dev ASR predictions (gold cannot
  calibrate it — same lesson as the 88/8 fuzzy thresholds).
- N-best rescoring literature (abstracts read this thread): Futami et al.,
  arXiv:2110.01857 (ELECTRA rescoring + phone-attentive variant for error
  detection); Zhang et al. 2024 (server-side rescoring of entity-centric
  queries: sub-word NNLM trained on domain data was the best single rescorer,
  +30%/+34% accuracy on tail/torso entities in their report; combining
  multiple rescoring LMs helped further); LLM second-pass rescoring with only
  a domain prompt (zero-shot domain adaptation work: LLaMA-7B rescoring of
  N-best lists reduced WER out-of-domain, with deep LLM-fusion better for
  entity/OOV recall). **Inference for LifeMate:** the cheapest transferable
  form is *lexicon-constrained* rescoring, not a new neural rescorer: rerank
  the ASR n-best list by (acoustic score + slot-lexicon bonus), where the
  lexicon comes from runtime-legitimate state (contacts, places, app names)
  and the digit-word normalizer. A neural rescorer (even a small one) costs
  parameters and latency budget we have not measured — defer it.
- The friend-harness ASR claim (NOT verified, do not use): README claim
  "WER 29.4% → 9.6%" with no weights/log/submission. This thread does not
  rely on it for any recommendation. The audit gap stands: no access, no
  manifest, no conclusion.

**Error mapping.** E6 (ASR) — primary: entity names, spoken numbers, negation
("không", "đừng"), conditionals ("nếu … thì …") are the classes to attribute.
E1 (fill-act) — only via the interaction: if ASR drops a slot (e.g. mishears
a time), the LLM sees a missing slot and fills — but E5 shows fill-act happens
even with gold transcripts, so ASR work can only *reduce* E1's frequency, not
eliminate it. Do not let D3 cannibalize D2's budget on the promise of fixing
E1. E4 (intent-wrong) — partial: entity misrecognition is one cause of
wrong-entity calls; the rest is LLM-side.

**Data needs.** Dev audio + gold current transcripts (1237 current turns;
history-turn gold transcripts are NOT established — history `audio_text` in
the data is ASR output per the E0 design, so history-turn ASR fine-tuning
data does not exist in verified form). ASR predictions on dev audio from the
current pipeline (PhoWhisper-small, and medium if the swap lands) — these are
the measurement inputs. No held-out audio.

**Compute needs (honest).** Decoding-side work is CPU/GPU-light: n-best
generation + rescoring runs on the existing ASR path; the cost is one extra
ASR pass per sample at most (measure it; do not claim a number). ASR
fine-tuning is explicitly DEFERRED: it needs verified audio–gold pairs
(current turns only, narrow) + a training run whose cost is unmeasured +
the same derived-checkpoint eligibility question (a fine-tuned PhoWhisper is
also a derived checkpoint). If D3's measurement shows history-ASR errors
dominate, the correct next step is a *data* question (how to get gold history
transcripts), not a bigger ASR model.

**Contract sketch.** ASR stage stays offline, deterministic (greedy or fixed
beam; no sampling). `initial_prompt` content is built only from
runtime-legitimate context (current session state the pipeline already holds
— never from gold labels or held-out data). Digit-word normalization is a
deterministic text transform applied to the transcript *before* the LLM sees
it, with a unit-test suite (Vietnamese number words, including the phone
patterns from Round 3). N-best rescoring, if piloted, must keep the 1-best
fallback: if rescoring changes the transcript, log the change (auditability),
and measure both WER and downstream proxy — WER alone is not the metric,
decision-change rate is.

**Disqualifiers / conditions that kill it.**
- If slot-level attribution shows ASR errors rarely change the LLM's decision
  (decision-stable errors: the model recovers from context, or the error is
  on a non-slot word), D3 is deprioritized entirely — the measurement is the
  gate, and it comes first.
- If `initial_prompt`/hotwords overcorrect (gold-correct transcripts get
  worse), the conditioning vocabulary is too broad — narrow it to the
  session's own entities or drop the knob.
- If the address-book-at-ASR-time design requires pipeline surgery (ASR
  before state load), defer that variant; session-text conditioning
  (history + installed apps) needs no surgery.

**Reproducibility.** PhoWhisper weights + paper are public (VinAI); Whisper
decoding parameters are documented in faster-whisper / Whisper docs;
n-best rescoring is textbook. The LifeMate-side measurement (slot attribution)
is CPU work on dev audio + existing transcripts.

**Falsifier.** On dev: if the ASR-side pilot reduces slot-error rate but the
LLM proxy (with gold history, to isolate current-turn ASR) does not move,
current-turn ASR is not the bottleneck — stop ASR work and reallocate to
D1/D2. If it moves proxy but history-ASR errors dominate the residual, the
next step is the history-transcript data question, not more decoding tricks.

## 2. Surveyed but NOT selected for deep analysis (and why)

| Candidate | Why not deep (one line each) |
|-----------|------------------------------|
| Dynamic per-turn grammar / constrained decoding (vLLM `GuidedDecodingParams` json/regex/choice/grammar; backends xgrammar / outlines / lm-format-enforcer / guidance) | Already researched in Round 9 (G&G v2 architecture); it is the right *adjunct* for E2/E5 (missing-slot writes ungeneratable) but it cannot teach decisions (E1/E3/E4) and its organizer permission (XGrammar on the submission path) is UNVERIFIED. Revisit only after D1/D2, as a complement — never as a substitute for learning the boundary. |
| Tool shortlisting / retrieval (reduce the 147-tool prompt space) | Plausible adjunct for E4 (fewer distractors → fewer wrong-entity calls) and context pressure, but **not verified in this thread** (no primary source read) and it changes the prompt contract, which would confound the D1/D2 comparison. Pilot separately, after the decision-boundary result. |
| Pure RL from scratch (Tool Zero, GG-GRPO) | Strongest counter-evidence to naive SFT (see §3) and the most ambitious direction — but it needs a stable rollout + reward infrastructure we do not have yet, and its 7B/32B source results do not transfer to a 4B budget. Defer until D1+D2 exist as the cold start it would replace or extend. |
| LLM verifier / self-correction (Reflexion-style) | Round 9 already excluded an LLM verifier under 6B/30s without counting params/latency; extra turns also cost latency budget we have not measured. No new evidence this thread overturns that. |
| ReFT (PPO after SFT warmup, Luong et al. 2024) | Same family as SpeakRL/GRPO but PPO-based (more moving parts, less stable than GRPO/DPO per the literature cited in SpeakRL §2). If RL is pursued after D2, GRPO with verifiable rewards is the better-documented path for this setting; PPO is a fallback, not a separate direction. |
| ASR model swap (small → medium, or Qwen3-ASR) | Already decided in earlier selection research (medium = "try now" combo at 4.769B); Qwen3-ASR's release date / licence / param-count treatment are unverified here and it is Thread A's territory. D3 covers what is *new*: decoding-side work + measurement. |

## 3. Counter-evidence that constrains all three directions (read, not assumed)

- **Tool Zero** (Zeng et al., arXiv:2511.01934v1, full text §§1–3 read).
  SFT on ToolACE data: BFCL-Live 61.1 → 78.6 (in-distribution gain) but
  Non-Live / Multi-Turn negligible or regressing (9.6 → 7.8); cross-dataset,
  xLAM-7B-fc tops BFCL but is worst on average elsewhere, while foundation
  models are more consistent. Their conclusion: SFT imitates surface patterns
  and memorizes trajectories rather than internalizing reasoning. Tool-Zero-7B
  (pure RL, GG-GRPO) beats ToolACE-8B by 7.14% and ToolRL-7B by 7.18% in their
  report. **Constraint for us:** D1 must be designed *against* this failure —
  multi-turn trajectories (not single-turn pairs), distinct-path diversity,
  inner-dev validation on *unseen templates* (Thread C), and a pre-registered
  rule: if inner-dev gains do not survive a template-held-out slice, D1 is
  memorization, not learning. The +7% numbers are 7B/BFCL-family results and
  are **not** expected LifeMate gains.
- **SpeakRL's SFT ablation** (above): SFT 28.78% vs GRPO 46.17% on MultiWOZ 2.4
  — same mechanism, different task. **Constraint:** D1's success criterion
  must include the decision classes (fill-act rate, ask-rate, prerequisite
  rate), not just proxy — otherwise a proxy gain can hide a decision
  failure.
- **Step-DPO's data finding** (above): self-generated > foreign pairs.
  **Constraint:** do not import preference pairs from other harnesses, other
  models, or the friend's repo (even if access appears later) without a
  head-to-head against self-generated pairs — and do not let that comparison
  consume the pilot budget; self-generated first is the default.
- **AwN's mechanism claim** (above): next-token training *defaults* to
  filling. **Constraint:** any proposal that relies on prompting alone to
  fix E1 must explain why E5 (prompting, 0/7 → 1/7) does not already refute
  it. D2 exists precisely because prompting does not move this boundary.

## 4. What would change the ranking (for the main thread's synthesis)

1. Organizer answers "derived checkpoints allowed" vs "not allowed": if not
   allowed, D1 and D2 are both dead for submission and the ranking collapses
   to D3 + grammar/guard (inference-side only). This question outranks all
   modelling preferences.
2. Thread A finds that dev gold trajectories for a whole error class are
   systematically anomalous (e.g. a template whose gold itself fills): then
   D1's verified pool for that class is poisoned and D2's chosen side is
   wrong — fix the data contract first, do not train.
3. Thread C's inner split shows a whole template family has < N trainable
   samples: then D1/D2 cannot learn that family and the honest recommendation
   for it is guard/grammar coverage, not more training.
4. D3's measurement shows history-ASR errors dominate and current-turn ASR
   is decision-stable: then D3's decoding work is deprioritized and the
   history-transcript data question becomes the ASR item.
5. D1 pilot shows proxy gain with unchanged fill-act rate: D2 becomes the
   priority and D1 is kept only as D2's cold start (exactly the SFT→DPO
   order in the contract above).

## 5. Evidence ledger (only what this thread actually read, 2026-10-29)

Papers / docs read (abstract + relevant sections, unless noted):

| # | Source | Version / date read | What was taken from it | What was NOT taken |
|---|--------|---------------------|------------------------|---------------------|
| L1 | STaR, Zelikman et al., arXiv:2203.14465v2 | v2, 20 May 2022 | Loop (generate → rationalize given answer → fine-tune on correct only → repeat); direct-answer SFT comparison | Any tool-use number (none exists in STaR — QA/math only) |
| L2 | RFT, Yuan et al., arXiv:2308.01825v2 | v2, 13 Sep 2023 | Rejection-sampling pipeline; distinct-path-count finding; 35.9% → 49.3% (LLaMA-7B, GSM8K, multi-model) | Transfer of GSM8K gains to LifeMate (not claimed) |
| L3 | APIGen, Liu et al., arXiv:2406.18518 | NeurIPS 2024 paper | 3-stage verification ladder; 3,673 APIs; 60k dataset; 7B BFCL claim | BFCL rank as LifeMate evidence (different harness) |
| L4 | APIGen-MT, Prabhakar et al., arXiv:2504.03601v4 | v4, 19 Jul 2025 | Blueprint → multi-turn trajectory pipeline; 5k trajectories; xLAM-2-fc-r multi-turn finding | Any τ-bench/BFCL score as LifeMate evidence |
| L5 | DPO, Rafailov et al., arXiv:2305.18290 | 2023 | Policy/reference log-ratio objective; no reward model / PPO | — |
| L6 | Step-DPO, Lai et al., arXiv:2406.18629 | 2024 (ar5iv HTML) | First-erroneous-step objective; 10k pairs / <500 steps / ~+3% MATH (70B); self-generated > foreign data; code github.com/dvlab-research/Step-DPO | MATH gains as LifeMate gains (not claimed) |
| L7 | Hammer, Lin et al., arXiv:2410.04587v2 | v2, 10 Oct 2024; ICLR 2025 | Function masking; 7.5k irrelevance instances with `[]` labels; BFCL 83.92% (7B) claim; code github.com/MadeAgents/Hammer; data MadeAgents/XLAM-7.5k-Irrelevance | Hammer checkpoints (over cap) as candidates |
| L8 | Learning to Ask / AwN, Wang et al., arXiv:2409.00557v4 | v4, 29 Apr 2026 — **abstract + v2 fragments only; full-text method details NOT re-read** (PDF mirror fetch failed; not retried) | Next-token → arbitrary missed-argument generation; AwN prompting framework; NoisyToolBench; ToolEvaluator | AwN's detailed method, ablations, and scores (not read — do not quote) |
| L9 | SpeakRL, Acikgoz et al., arXiv:2512.13159v1 | v1, 15 Dec 2025; §§1–3 + abstract read | GRPO + format + LaaJ rewards; `<think>`/`<clarify>` tokens; SpeakER 25k; MultiWOZ 2.4 numbers (base 25.63 / SFT 28.78 / DPO 45.73 / SpeakRL 46.17; turns 8.12 → 5.82); "SFT imitates structure without learning when/why to ask" | Any MultiWOZ gain as LifeMate gain; the Claude-simulator + LaaJ setup (banned here) |
| L10 | Tool Zero, Zeng et al., arXiv:2511.01934v1 | §§1–3 read | SFT OOD failure (Live 61.1→78.6 vs Multi-Turn 9.6→7.8); cross-dataset inconsistency table; GG-GRPO dynamic reward; Tool-Zero-7B +7.14% vs ToolACE-8B / +7.18% vs ToolRL-7B (their report) | Any BFCL number as LifeMate evidence; 7B/32B checkpoints (over cap) |
| L11 | τ-bench, Yao et al., arXiv:2406.12045 | 2024 (via prior-thread citation + secondary summaries this thread) | Tool-agent-user loop; final-state success; policy + interaction as part of the eval object | τ-bench scores as LifeMate evidence |
| L12 | ToolGuards, arXiv:2507.16459 | 2025 (via prior-thread citation; abstract-level this thread) | Deterministic pre-execution policy validators; "gates read operational state, no model, no ground truth" | Any ToolGuards precision claim for LifeMate (mechanism only, per Round 3) |
| L13 | ReFT, Luong et al., arXiv:2401.08967v3 | v3, 13 Dec 2024 (abstract read) | SFT warmup → online PPO on sampled paths with answer-derived rewards; beats SFT on GSM8K/MathQA/SVAMP in their report | PPO as the recommended RL algorithm (GRPO preferred here; see §2) |
| L14 | PhoWhisper, Le et al., ICLR 2024 Tiny Paper | Table 2 read | WER table (small 244M / medium 769M / large 1.55B); 843.79 h Vietnamese training | Any LifeMate-audio WER (unmeasured) |
| L15 | Whisper decoding params (faster-whisper / Pipecat / WhisperX docs, secondary) | Read 2026-10-29 | `initial_prompt` = preceding-context priming; `hotwords` = decode bias; both are conditioning only, overcorrection risk | `hotwords` availability in the pinned runtime version (must verify) |
| L16 | N-best rescoring (Futami et al. arXiv:2110.01857; Zhang et al. 2024 entity rescoring; LLM second-pass rescoring work) | Abstracts read | Rescoring-by-lexicon/LM improves entity/tail accuracy; domain sub-word NNLM best single rescorer in Zhang et al. | Any WER gain as LifeMate gain; neural rescorer as a proposal (deferred) |
| L17 | When2Call, Ross et al. 2025 | **Original paper NOT read**; taxonomy + 3,109-instance split via follow-up papers' §1 summaries | Four-way decision taxonomy (call / answer / ask / abstain); single-turn counts 1,226 / 873 / 1,010 | When2Call data as training data (different tools/language) |
| L18 | vLLM structured output docs (secondary: Ray / vLLM guides) | Read 2026-10-29 | `GuidedDecodingParams` (json/regex/choice/grammar); backends xgrammar / outlines / lm-format-enforcer / guidance | Any latency overhead % as a LifeMate measurement (secondary guides claim 5–15%; unmeasured here) |
| L19 | xLAM family, Zhang et al., arXiv:2409.03215 | Abstract read | Unified/augmented/synthesized pipeline; 1B–8x22B family; BFCL claims | xLAM checkpoints as candidates (licence + Vietnamese + cap all need separate verification; xLAM-2-3b-fc-r already flagged licence-blocked in prior research) |

**Explicitly NOT verified in this thread (unknowns, not gaps to fill by assertion):**

- U1. Organizer: derived-checkpoint eligibility (SFT/DPO/ASR fine-tune weights),
  vLLM/XGrammar permission on the submission path, parameter counting
  (total vs non-embedding), Q-L/Q-D answers. All UNVERIFIED.
- U2. Friend's SFT repo / checkpoints / manifest: inaccessible (404), audit
  stopped per user instruction. No conclusion about "friend SFT quality" is
  drawn anywhere in this report.
- U3. SFT/DPO training cost, memory, and wall-clock for a 4B model on the
  available hardware: unmeasured. No number is given.
- U4. A30 latency of any configuration (including grammar overhead and ASR
  n-best rescoring): unmeasured. No T4→A30 extrapolation is made.
- U5. LifeMate-audio WER (current or history turns) and slot-level ASR error
  attribution: unmeasured. D3's measurement is the gate.
- U6. Whether `hotwords` exists in the pinned faster-whisper runtime version.
- U7. APIGen-MT-5k dataset licence; ToolACE dataset licence beyond the CC BY
  4.0 note for xlam-function-calling-60k in a downstream README.
- U8. Qwen3-4B-Instruct-2507 revision licence file for derived-weight
  submission (re-check before any submission use).
- U9. AwN full-text method details, ablations, and scores (abstract-level only).
- U10. When2Call original paper (taxonomy via secondary sources only).
- U11. Tool shortlisting / retrieval primary sources (surveyed, not verified).

## 6. Recommendation to the main thread (Thread B's position, for synthesis)

Rank the three by *falsifiability per GPU-hour*, not by literature hype:

1. **D2 first in the pilot order — but D1 as its cold start.** The pilot
   sequence is: D1-lite (verified-trajectory SFT on a small slice, just enough
   to be a stable reference) → D2 (Step-DPO pairs from the model's own
   errors). Rationale: E1 is the dominant, decision-shaped error; SFT alone
   is mechanistically predicted (AwN + SpeakRL + Tool Zero, three independent
   sources) to imitate the ask shape without learning the boundary. Running
   D1 alone to completion and only then discovering the boundary did not move
   is the most expensive mistake available.
2. **D3's measurement runs in parallel on CPU** (it needs no GPU and no
   training decision): slot-level ASR attribution on dev. Its *interventions*
   (initial_prompt / rescoring) wait for the measurement gate.
3. **Grammar/guard work continues as the safety layer, not the learning
   layer** — it bounds the damage from E2/E5 while D1/D2 address decisions,
   and its hard-enforce decision stays with Round 3's evidence (shadow-ready,
   not hard-enforced; phone branch residual open).

If the organizer answers kill derived checkpoints, this whole ranking is void
and the fallback is: D3 + grammar + guard, with the model frozen at the
current instruct checkpoint. That fallback must be stated in the final
synthesis, not discovered after training.
