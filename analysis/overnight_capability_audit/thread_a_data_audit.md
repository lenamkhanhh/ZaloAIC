# Thread A — Dev data audit for small-model tool-use SFT (LifeMate)

**Scope of this thread:** is the 1237-sample dev set, as it exists today,
a sound basis for SFT of the current runtime? What exactly would the
training data look like, what can it teach, and what can it not teach?
This thread does NOT decide go/no-go on SFT (main thread synthesizes),
does NOT design the evaluation split (Thread C), and does NOT rank
methods (Thread B).

**Headline finding:** dev gold is clean, replay-verified, and
mechanically convertible into runtime-exact SFT examples (prototype
verified, §7) — so data construction is NOT the blocker. The binding
constraints are elsewhere: (1) gold teaches almost no recovery from
`not_done` (exactly 1 such gold call, quarantined); (2) time/date/amount
arguments are mostly *derived*, not copied, so SFT must teach
derivation, not transcription; (3) training on gold transcripts has a
clean-vs-ASR text mismatch at both the current request and history
turns, and no local ASR-prediction cache exists to close it; (4) 63/147
tools have <10 dev gold examples, so SFT can teach skills, not tool
memorization. Every number below is dev-only unless stated otherwise.

## 0. Evidence ledger — what was actually read

| Artifact | Identity / version | What was taken from it |
|---|---|---|
| `lifemate/splits/train_dev_heldout.json` (repo clone) | seed 42, dev 1237 / held-out 308 | Split map. Held-out rows were dropped BEFORE any analysis; no held-out content appears anywhere in this thread's outputs. |
| `train/train.jsonl` (extracted data) | 1545 rows total | Dev rows only (1237 kept, 308 dropped). Sample schema confirmed: `id, audio, audio_text, context{current_time, timezone, location, user_profile, installed_apps}, history[], label{tool_calls, tool_results, final_state}`. |
| `train/train_tools_catalog.json` | schema 2.7.0, 147 tools (write 84, read 62, meta 1), 46 apps | Kind map, required-param counts, fuzzy (`x-match: fuzzy`) params. |
| Worktree `~/workspace/zaic-branch-a2e832b/lifemate/` (read-only) | agent `a2e832b` | Runtime serialization: `agent.py` (prompt, loop, guard), `llm.py` (chat template, JSON-per-turn, stop), `loader.py` (sample/tool filtering, label classes), `config.py` + `configs/baseline.json` / `recommended.json`, `run.py` (`cmd_infer` history-ASR behavior), `scoring.py` (engineering proxy, NOT the official evaluator). |
| `~/workspace/zaic-analysis/context_budget_a2e832b_rows.json` | prior measurement, Qwen tokenizer, 1237 rows | Prompt token sizes (cited as prior measurement, not re-measured here). |
| `analysis/runtime/E5_V13_DEEP_ANALYSIS_AND_NEXT_STEP_2026-10-28.md`, `E1_V10_INTENT_ANALYSIS_2026-10-28.md`, `SOTA_ANALYSIS_ALL_ERRORS_2026-10-28.md` | prior reports | Error taxonomy cross-check only (FILL-ACT, ask behavior). No numbers re-quoted as new evidence. |
| `analysis/asr-sft-verification-brief.md` (local, NOT pushed) | 2026-10-28 | Prior access conclusion for the friend repo (see §6). |
| Round-3 outputs (prover/gates audits, branch `round10-provenance-gates-fixes` @ `61d84390`) | prior work | Cross-checks: duplicate-search rate, message-history contacts, train_1696 anomaly, phone direct-dial pattern. |

**Evidence-class labels used in this report** (per the task):
`[REAL-RUN]` = real model execution; `[GOLD-REPLAY]` = CPU replay of gold
labels through `ToolEnv`; `[CPU-AUDIT]` = this thread's CPU counting on
dev; `[PRIOR-MEAS]` = earlier measurement re-cited, not re-run;
`[HEURISTIC]` = keyword/format proxy, lower bound or approximation;
`[PROPOSAL]` = not run. No number below is upgraded to a stronger class.

**Transcript types, stated precisely.** Train gold `audio_text` = gold
transcript (current request and history user turns). Runtime inference
(`run.py cmd_infer`) transcribes the current request AND any history
user turn lacking `audio_text` with PhoWhisper-small greedy — so at test
time the model sees ASR text in both slots. E0 `[REAL-RUN]` used gold
CURRENT transcript with ASR history: it does NOT isolate ASR, and it
does NOT license "ASR is not a bottleneck" as a general claim.

## 1. Runtime serialization — what SFT data must match exactly

The runtime is **not** native tool-calling. SFT that trains any other
format is a runtime change, not a data change, and would need its own
re-benchmark. The contract (§7) pins this format.

1. **Single user message, plain-text prompt.** `build_base_prompt`
   renders: instruction line + `ACTION_POLICY` + current time/user +
   full `context` JSON + the sample's *filtered* tool list (installed
   apps + `sys.ask_missing_info` only, each spec as JSON with
   name/kind/description/parameters/returns) + history lines + current
   request transcript. Rendered through the Qwen3 chat template as ONE
   user message (`llm.py _render`).
2. **One JSON object per turn.** Target is `{"name": ..., "arguments":
   {...}}` or `{"stop": true}`. No multi-call lists, no narrative, no
   native `<tool_call>` blocks. Max new tokens 512, greedy, seed 42.
3. **Observation after every call.** Next turn's prompt = base prompt +
   `- name(args) -> ok|not_done|error: ...; output=<full result JSON>`
   per executed call (`render_observation_prompt`). Validation failures
   are observations too (not executed, not submitted); up to 2 retries
   per step; loop guard pre-blocks a call repeated ≥2 times (replan
   once, then stop); `sys.ask_missing_info` ends the turn.
4. **History rendering quirk (M2).** Assistant turns render as
   `assistant: {text} calls={json} results={repr}` — Python `repr`,
   not JSON, for results. SFT data built from history must reproduce
   this rendering byte-for-byte, or train/test history format differs.
5. **History text mismatch (M3).** Train gold history user turns carry
   clean `audio_text`; test-time history user turns are ASR
   transcripts (`cmd_infer` transcribes them). SFT on gold history
   text teaches reliance on clean history the model will not get.
   Mitigations (§7): ASR-transcribe train history audio as a GPU
   prerequisite step (no local cache exists — see §6), or accept the
   gap and measure it. Do NOT drop history from training: the infer
   path uses it.
6. **Current-request text mismatch (M4).** Same clean-vs-ASR gap for
   the current request. No local dev ASR-prediction cache was found
   (searched worktree + analysis dirs; the "ASR cache byte-identical"
   note in the verification brief refers to Codex-side runs, not a
   local artifact). ASR-text SFT is therefore a future GPU step, not
   something constructible from local artifacts today.
7. **Grounding is an inference guard, not a target (M5).**
   `recommended.json` has `grounding: true`: `ground_arguments` runs
   after generation, before validation. Gold calls are already in
   grounded form (real ids, int amounts, ISO times), so SFT targets =
   gold calls as-is, and grounding stays ON at inference as a safety
   net. Do NOT train the model to emit ungrounded forms
   (`contact_name`, word amounts) expecting the adapter to fix them —
   that inverts the pipeline's design.
8. **Scorer reality (affects what SFT should optimize).** The shipped
   scorer is an engineering proxy `[PRIOR-MEAS]`: per-sample score =
   tool-call F1 *only if* submitted state_hash == gold state_hash,
   else 0; reads count in F1; fuzzy params match at token-F1 > 0.6.
   The official evaluator is absent. SFT targets must therefore aim at
   *state-equivalent* trajectories, not at matching gold call text:
   extra reads already dilute F1 (measured in prior work: write-only
   1.0 → +1 read 0.667 → +2 reads 0.5), and a correct final state with
   a different-but-valid trajectory can still score 0 under this
   proxy if the hash differs. SFT data should prefer gold trajectories
   verbatim (they hash-match by construction) and treat trajectory
   variants as Thread C's evaluation question, not as training data.

## 2. Dev distributions `[CPU-AUDIT]` (1237 samples, 2843 gold calls)

### Label classes (loader definition)

| Class | n | Meaning for SFT |
|---|---|---|
| normal | 974 | ≥1 call, no ask |
| empty | 89 | 0 calls → target `{"stop": true}` |
| ask_only | 48 | single `sys.ask_missing_info` |
| ask_after | 126 | ask present, never alone |

**Ask is always terminal in gold.** Ask position: only 48, last 126,
middle 0. SFT must teach ask as a *terminating* action; there is zero
gold evidence for ask-then-continue. The 89 empty samples are equally
load-bearing: without them the model never learns to stop with no
action (the "cancelled sole request / unavailable capability" case in
`ACTION_POLICY`).

### Call-count and kind mix

Gold calls per sample: 0: 89, 1: 299, 2: 332, 3: 293, 4: 127, 5: 89,
6: 8. Max 6, well under the agent's `max_steps` 12 — no truncation
pressure from trajectory length.

Kind mix per sample: read+write 634, read 96, write 244, none 89,
meta+read+write 63, meta+read 61, meta 48, meta+write 2. Last gold call:
write 866, read 108, meta 174, empty 89. The 108 read-final samples
matter: SFT must include stop-after-read (a read that answers the
request ends the task), not only stop-after-write.

### Read-before-write in gold order

Write preceded by ≥1 read in the same gold trajectory: 623 samples.
Write with NO prior read: 320 samples. No write at all: 294.
The 320 direct-write samples are not gate violations — their args are
literals or derived values (see §3), not observation ids. SFT must
teach *both* modes and the discriminator between them (does this write
need an id/value from a read, or is everything already in the request?).

### Tool / app coverage and rarity

Top gold tools (calls): `smart_home` app 236, `contacts` 192,
`bill_payment` 190, `sys` 174, `banking` 169, `calendar` 159,
`chat_ott` 143, `reminders` 102. Smallest apps: `fuel_price` 9,
`calculator` 12, `exchange_rate` 16, `tv` 17, `lottery` 24,
`package_tracking` 24, `home_energy` 24.

- Tools NEVER in dev gold (2): `contacts.get`, `smart_home.scene_run`.
- Tools with <5 dev gold calls (26): `alarm.delete`,
  `alarm.update`, `banking.list_transactions`, `calculator.calculate`,
  `chat_ott.call`, `chat_ott.send_location`, `email.read`,
  `email.reply`, `email.send`, `ewallet.pay_qr`, `flights.cancel`,
  `food_delivery.cancel_order`, `home_security.arm`, `music.control`,
  `news.headlines`, `notes.append`,
  `package_tracking.reschedule_delivery`, `podcast_radio.play`,
  `reminders.delete`, `ride_hailing.get_quotes`, `ride_hailing.get_ride`,
  `shopping_list.remove`, `smart_home.switch_set`, `sms.read_recent`,
  `tv.record`, `tv.tune`.
- Tools with <10 dev gold calls: 63 of 147 (43%).

**Implication:** SFT cannot teach tool-specific behavior for nearly
half the catalog. The model must generalize from the catalog
descriptions that are in the prompt. SFT's realistic job is teaching
*skills* (read-first, ask-on-ambiguity, derive-don't-invent, stop),
not tool memorization. Any SFT claim that implies rare-tool mastery
from this data is unsupported.

### Tool sequences / templates

582 distinct gold tool sequences across 1148 non-empty samples. Most
common: `[]` 89, `[ask]` 48, `[bill_payment.list_bills,
bill_payment.pay, bill_payment.pay]` 23, `[reminders.create]` 18,
`[smart_home.get_status, smart_home.light_set,
smart_home.climate_set]` 18, `[bill_payment.list_bills,
banking.get_balance, banking.list_beneficiaries, banking.transfer,
banking.transfer]` 18, `[bill_payment.list_bills,
ewallet.get_balance, bill_payment.pay, contacts.search, sms.send]` 17,
`[alarm.create, contacts.search, ask]` 16,
`[smart_home.get_status, smart_home.light_set, contacts.search,
ask]` 16. First-call leaders: `bill_payment.list_bills` 90,
`smart_home.get_status` 75, `contacts.search` 54,
`calendar.list_events` 53, `sys.ask_missing_info` 48,
`weather.get_forecast` 42.

Sequences repeat heavily (top sequence 23×) while request texts do
not (§5) — the data is template-generated at the trajectory level.
That is good for learning the templates, but it means an inner split
by sample id alone will leak templates across train/validation. The
inner split must stratify by tool-sequence template (Thread C's call;
this thread supplies the counts).

### Catalog schema facts

147 tools: 98 with ≥1 required param, 49 with zero required params
(empty-args calls are legitimate and frequent, e.g. list tools). 32
tools carry fuzzy (`x-match: fuzzy`) params — free-text args
(`content`, `title`, `body`, `subject`, `location`, `address`,
`expression`, `pickup`, `dropoff`, `near`, `label`, `note`, …) that
the proxy scorer matches at token-F1 > 0.6, not exactly. SFT loss on
fuzzy args should therefore not demand byte-exact gold strings as if
they were ids; conversely, exact-match args (ids, times, amounts) need
exactness. A single undifferentiated token loss treats these two
cases identically — the loss-mask proposal in §7 separates them only
in the sense that fuzzy-arg tokens are still trained (they are model
outputs), but evaluation of them must use the fuzzy rule, and
synthetic negatives must never be built by paraphrasing a fuzzy arg
and calling it "wrong".

## 3. Learnability factors — what gold actually demonstrates

### Entity ambiguity: the strongest-learnable pattern in the data

`[GOLD-REPLAY]` on dev: 183 gold `contacts.search` calls; 59 (32.2%)
return same-normalized-name / different-id pairs. Gold's next call
after a duplicate search: `sys.ask_missing_info` 55/59 (93.2%),
`phone.call` 1, `chat_ott.list_chats` 2, `contacts.update` 1.
This reproduces the prior all-train finding (73/234, 94.5% ask) on dev
alone. **Duplicate → ask is gold-confirmed policy with 59 examples.**
SFT positives for ask should overweight this pattern (it is also the
pattern the E5 `[REAL-RUN]` analysis showed the zero-shot model fails
by filling instead of asking — but note the scope: E5's failure was
about *missing time*, not about duplicate names; do not conflate them).

### Contacts-app availability: the direct-dial pattern

`[GOLD-REPLAY]` whole-book probe: **534/1237 dev samples (43.2%) do
not install the contacts app at all** (`contacts.search` returns
`ok: False`, "không thuộc app đã cài"). Cross-check: context
`installed_apps` lists contacts in 703 samples; 534 + 703 = 1237. ✓

17 dev gold samples call `phone.call`/`sms.send` with a
`phone_number` and NO `contacts.search` anywhere in gold
(`train_0451, train_0502, train_0579, train_0657, train_0664,
train_0676, train_0764, train_0834, train_0872, train_0894,
train_0969, train_1131, train_1283, train_1314, train_1442,
train_1662, train_1677`). These are legitimate gold: hotlines,
spoken digit strings, missed-call callbacks, numbers from message
threads. SFT must include them — otherwise the model learns
"phone_number requires a prior search", which is false in 43% of
samples and directly contradicts the phone-branch evidence from
round 3 (roster-only phone gating fires on 17/19 phone-only gold
calls; the call-log source added in round 3 rescues only the
callback subset).

### Time / amount / id sources `[HEURISTIC + GOLD-REPLAY]`

For each gold *write* arg, its value string was checked against:
current request text, history user text, history tool results, prior
gold-call results (real `ToolEnv` replay), context JSON. "Verbatim"
here means the exact string appears; word-form numbers ("hai triệu")
and relative dates ("ngày mai") do NOT match verbatim and fall into
`none_of_those` — that bucket is therefore "derived or paraphrased",
not "unexplainable".

| Slot class | n | verbatim current | history user | history result | gold-prefix result | context | none (derived) |
|---|---|---|---|---|---|---|---|
| entity_id (`*_id`) | 921 | 0 | 0 | 242 | 678 | 0 | 1 |
| contact_ref (`contact_id`/`to`) | 128 | 0 | 0 | 23 | 84 | 0 | 21 |
| amount | 109 | 0 | 0 | 4 | 53 | 0 | 52 |
| time | 330 | 0* | 0 | 19 | 30 | 0 | 281 |
| date | 11 | 0 | 0 | 0 | 0 | 0 | 11 |
| other (free text etc.) | 1165 | 150 | 19 | 94 | 215 | 112 | 575 |

\* Time "verbatim current" is 0 because ISO datetimes never appear
literally in spoken requests; the date-part/HH:MM-part check also
found no matches under the strict string rule — relative expressions
dominate. (A looser normalizer would move some `none` rows into
"derived from current text", but the qualitative point stands.)

Value formats `[CPU-AUDIT]`: amounts are int 109/109 (never strings,
never floats); times are ISO datetime 318/330, time-only `HH:MM`
12/330; dates are date-only 11/11.

**Read this table as the SFT difficulty ranking:**
1. **Ids are solved by reading, not by knowing.** 920/921 entity ids
   come from an observation (prior gold result or history result).
   SFT must teach read → copy-id, and must never teach id memorization
   (ids are per-sample random; memorizing them is impossible and any
   training example that rewards an id without a preceding read in
   context is a leakage artifact, not a skill).
2. **Times/dates are derivation tasks.** 281/330 times and 11/11 dates
   are not verbatim anywhere: relative dates, dayparts, offsets,
   durations composed from `current_time` + request words. This is
   exactly the class round 10's prover attacks with deterministic
   re-derivation — SFT that only copies gold ISO strings will not
   learn the derivation, and worse, will learn to *emit* ISO strings
   without grounding (the FILL-ACT failure mode from E5 `[REAL-RUN]`:
   the model fills a time from context so "ask when missing" never
   fires). Time-derivation examples need the request words + anchor
   time in context (they are, in the prompt) and a loss that does not
   reward guessing.
3. **Amounts split in two.** 53/109 come from a prior result (bill
   amounts, balances — read-first), 52/109 are derived (word-form
   numbers in the request, quantity × price). Both sub-skills need
   coverage; neither is copy-from-request-text.
4. **Contact refs have a 21-case residue** (message-history contacts,
   no roster/search evidence) — these overlap the quarantine set (§4).

### Observations and termination

- Gold tool results in labels: replay shows results are real
  simulator outputs by construction (gold trajectories were produced
  through the simulator). SFT observations MUST be simulator outputs
  from replaying the gold trajectory, never hand-written or
  model-generated summaries. The round-trip prototype (§7) does
  exactly this.
- `not_done` in gold: exactly 1 call (§4). **Gold teaches no recovery
  from `not_done`.** The runtime's replan-after-`not_done` behavior
  (policy item 5: "Change the plan using evidence; do not repeat the
  same failed call") has zero gold demonstrations. Recovery examples
  can only come from real model traces (V10/V11/V13 proposals show
  failures, but those traces' *recoveries* are model behavior, not
  gold) or from simulator-driven synthetic rollouts — both are Thread
  B/C design questions, not something this data supplies.
- Termination signals in gold: stop-after-write (866), stop-after-read
  (108), ask-terminates (174), empty-stop (89). All four must be
  represented in SFT targets; a dataset of "write-only" trajectories
  would teach the model to never stop after a read or an ask.

### History and multi-turn structure

814/1237 samples have history; 583 have ≥4 history turns. Turn-count
distribution: 0: 423, 2: 231, 4: 219, 6: 106, 8: 61, 10: 61, 12: 32,
18: 25, 20: 39, 22: 27, 24: 13 (even counts = user/assistant pairs).
History assistant `tool_results` form in dev gold: list 2384, none
412, repr-string **0**. The repr-string hazard flagged in round 3 is
a *trace-format* issue (model-trace histories), not a property of
gold history — but SFT builders that ingest model traces must still
handle it; builders that ingest gold only do not face it.

`[HEURISTIC]` pattern words (diacritic-folded, lower bounds):
correction/cancel words in request-or-history 414 samples (33%);
conditional words 97 (7.8%); gold contains an `update` tool 41;
gold contains a cancel/delete tool 67. Corrections and conditionals
are common enough to be first-class SFT classes, but the keyword
heuristics undercount (e.g. conditionals expressed without "nếu/khi"),
so these are floors, not totals. Cancellation-as-empty (cancel the
sole request → no calls) is already covered by the 89 empty samples
only if some of them are cancellations — that sub-class was not
separated here and should be checked before claiming empty-sample
coverage of cancellations.

### Context size `[PRIOR-MEAS]`

Qwen-tokenizer prompt sizes on dev (prior context-budget measurement,
1237 rows): base prompt mean 5372 tokens, max 9308; final prompt
(with all observations) mean 5666, max 9874; **0 samples exceed the
16384 − 512 budget**. The per-sample tool catalog dominates (mean
3899 tokens, max 7305). Consequences for SFT: (a) sequences fit, but
mean training sequence ≈ 5.7k tokens — training cost scales with
catalog size, not with trajectory length; (b) any SFT format that
*expands* the catalog (e.g. adding examples per tool) risks the
budget; (c) catalog-filtering by installed apps is load-bearing and
must be preserved in training examples exactly as at inference.

## 4. Gold anomalies and quarantine list

`[GOLD-REPLAY]` full dev gold replay through `ToolEnv`: 2842/2843
calls succeeded (`ok` true, `done` not false); 1 call `ok` true /
`done` false; 0 rejected; 0 exceptions; 1236/1237 samples fully
succeed. Gold is, with one exception, replay-clean — SFT positives
from gold are simulator-valid by construction.

**Quarantine from SFT training (exclude the samples, not just the
calls — trajectories are the unit):**

| Sample(s) | Reason | Evidence |
|---|---|---|
| `train_1696` | Gold write itself fails replay: pos 2 `chat_ott.send_message{chat_id: chat_6142}` → `ok` true, `done` false. Training on it teaches a write the simulator will not execute. | `[GOLD-REPLAY]` this thread; known since round 2 as the gold anomaly |
| `train_1005`, `train_1033`, `train_1319` | Gold `contact_id`s (`c_778`, `c_217`, `c_9526`) come only from message history, never from a roster/search — training on them teaches message-history-as-roster, the exact inference round 2/3 closed for the guard. Cost of exclusion: 3 samples. | Round-2/3 gate audits (gold false-block cases); consistent with §3 contact-ref residue |
| `train_0061`, `train_0066`, `train_0168` | Near-duplicate normalized requests (same digit-masked request text, 3 samples). Not wrong — but they must land on the SAME side of any inner split, or they leak. Flag for Thread C; do not split them apart. | `[CPU-AUDIT]` §5 |

**Not quarantined, but annotated:** the 17 direct-dial samples (§3)
are legitimate gold and must stay in training (they teach the
no-search phone pattern). The 21 contact-ref `none` cases include
the 3 quarantined samples above; the remainder are phone-number and
history-derived refs that are legitimate but should be tagged in the
dataset metadata so Thread C can ablate them.

## 5. Overlap and template structure (input to Thread C, not decided here)

- Normalized requests (diacritic-folded, digits masked, whitespace
  collapsed): **1235 distinct / 1237 samples; exactly 1 group with
  >1 sample** (the triple in §4). Request-text duplication is
  negligible — sample-id splitting does not leak through request
  text, except for that triple.
- Tool-sequence templates repeat heavily (§2: 582 distinct sequences,
  top sequence 23×). An inner split by sample id alone WILL leak
  templates across train/validation. Stratification must consider
  (normalized request, tool sequence) jointly — Thread C's design
  decision; this thread supplies the counts.
- Cross-version trace samples (V10/V11/V13) reuse the same 8–20
  samples across arms/versions. Those are NOT independent samples for
  any evaluation claim — restated here because SFT model selection
  must not count per-arm agreement as independent evidence.

## 6. Friend SFT artifacts — NOT AUDITED (blocker recorded, work not stopped)

- Friend repo `github.com/khoakhoahihi/ZAIC-Track-LifeMate-`:
  **inaccessible, API 404, audit stopped per user instruction.**
  No code, manifest, checkpoint, training log, or submission artifact
  from the friend was seen in this thread. Nothing in this report
  explains, endorses, or disputes any friend number (including the
  README claims of ASR WER 29.4% → 9.6% and public 46.68 reported by
  the user in an earlier session — those are `[README-UNVERIFIED]`
  and are not used anywhere in this audit's reasoning).
- Local SFT artifact search: no training script, LoRA/PEFT config,
  `SFTTrainer` usage, training manifest, or checkpoint exists in
  `zalo-aic-round3/` (analysis/research/lifemate/plans),
  `zaic-branch-a2e832b/lifemate/`, or `zalo-aic/` — only prose
  mentions of SFT in research notes and the local verification
  checklist `analysis/asr-sft-verification-brief.md`, which itself
  concludes access was unavailable and lists what would need to be
  requested (training manifest, version table, SFT data sample).
  **Therefore: model/revision, train/eval overlap, loss masking,
  truncation, tool-message format, parser contract, ASR-augmentation
  effect on intent/slot, and observation authenticity for ANY friend
  SFT are all UNAUDITED, not "clean" and not "flawed".**
- Consequence for this thread: none blocking. The dev audit, the
  data contract, and the prototype below stand on the user's own
  data and runtime alone. The friend comparison, if ever unblocked,
  needs the manifest + data sample listed in the verification brief
  before any claim about it can be made.

## 7. Data contract for SFT (fits the current runtime)

### Construction (dev only, deterministic, no model)

1. **Source:** dev 1237 samples minus quarantine (§4) = 1233
   training-eligible samples before any inner split. Held-out 308
   never enters construction, selection, or debugging.
2. **Per sample, build the trajectory mechanically:**
   a. Render the base prompt with the worktree's own
      `build_base_prompt` (installed-apps-filtered catalog, history
      rendering including the repr quirk, current request text).
   b. For each gold call in order: target = the call JSON exactly as
      gold (or `{"stop": true}` as the final target after the last
      call — and as the SOLE target for the 89 empty samples);
      execute the call in a fresh `ToolEnv`, capture the real result,
      and append the `render_observation_prompt` line as the next
      turn's input. `sys.ask_missing_info` is a target like any call
      and ends the trajectory (it ends the turn at inference).
   c. Simulator-verify every trajectory: replay must reproduce the
      gold call list exactly and every call must succeed, except the
      quarantined `train_1696`. Any trajectory failing verification
      is dropped and counted, never hand-fixed.
3. **Transcript policy (explicit choice, with cost):** default =
   gold transcripts for current request + history (what is
   constructible today). This carries the M3/M4 clean-vs-ASR gap.
   The gap-closing variant (ASR transcripts for train current +
   history audio) is a separate GPU prerequisite step for Codex; it
   must be built by running the production ASR path
   (`cmd_infer`'s history transcription) over train audio, never by
   substituting gold text and calling it ASR. Until that exists, any
   SFT result must be reported as "trained on gold text" and its
   transfer to ASR input treated as unmeasured.
4. **No gold/sample-specific rules in the data.** No per-sample
   instructions, no memorized id lists, no template-specific hints.
   The prompt is the production prompt; the only per-sample content
   is what production already puts there (context, catalog, history,
   request, observations).

### Serialization (pinned)

- Chat format: Qwen3 chat template, ONE user message containing the
  full rendered prompt (same as `llm.py _render`), assistant turns =
  one JSON object each (`{"name", "arguments"}` or `{"stop": true}`).
  Do NOT switch to native function-calling serialization without a
  runtime change + re-benchmark.
- Tool specs: exactly the installed-apps-filtered catalog JSON from
  `catalog_tools_for_sample` (name/kind/description/parameters/
  returns), same key order as production (`json.dumps` default).
- History: reproduce `build_base_prompt` rendering exactly,
  including `results={repr}` for assistant turns.
- Observations: full result JSON on one line per call, with the
  `ok|not_done|error` outcome prefix from `render_observation_prompt`.

### Loss-mask proposal `[PROPOSAL]`

- Train ONLY on assistant-turn tokens (each call JSON and the final
  `{"stop": true}`); mask prompt, catalog, history, context, and
  observation tokens. Rationale: the catalog alone is ~3.9k mean
  tokens — training on it teaches the model to recite the catalog,
  not to act.
- Multi-turn: every assistant turn in the trajectory is a target
  (teacher forcing on gold calls), observations are inputs.
- Do NOT upweight rare tools by duplicating their samples: with
  <10 examples, duplication teaches memorization of specific ids
  (which are per-sample random) rather than the skill. If rare-tool
  coverage is later judged insufficient, the remedy is more data or
  catalog-reading ability, not duplication.
- Fuzzy args (`content`, `title`, `body`, …) are trained as normal
  outputs, but their evaluation must use the proxy's token-F1 > 0.6
  rule — never exact-match — and synthetic negatives must never be
  built by paraphrasing a fuzzy arg.
- `{"stop": true}` targets (empty 89, post-trajectory stops,
  post-ask stops) must keep their natural frequency: dropping them
  teaches the model to always act.

### Positive / negative coverage

- **Positives:** gold trajectories only (§2 classes, all represented:
  normal 974, empty 89, ask_only 48, ask_after 126, read-final 108,
  duplicate→ask 59, direct-dial 17, read-first 623, direct-write 320).
  Minimum viable positive set = all non-quarantined dev trajectories;
  any subsampling must preserve class proportions and is Thread C's
  evaluation question, not a data-construction default.
- **Negatives (only from verified sources):**
  - Real model proposals from existing traces (V10/V11/V13
    `[REAL-RUN]` proposals that the guard blocked or that scored 0)
    may be used as negatives IF paired with the gold trajectory for
    the same sample and labeled by trace/version/arm. They are the
    only negatives that reflect actual model errors (notably
    FILL-ACT: a filled time where gold asks).
  - Synthetic negatives (e.g. swapping an id for another registry's
    id, dropping a prerequisite read) are allowed ONLY if
    simulator-verified (replay shows a different final state or a
    validation rejection) AND labeled synthetic in metadata. Never
    mix unlabeled synthetic negatives with gold positives.
  - **No recovery negatives/positives from gold exist** (`not_done`
    count = 1, quarantined). Any claim that SFT teaches recovery
    needs trace-derived or synthetic-rollout data, explicitly labeled
    as such.
- **Coverage floors to check before training** (assert in the build
  script, fail loudly otherwise): ask_only ≥ 40, empty ≥ 80,
  duplicate→ask ≥ 50, read-final ≥ 100, direct-dial ≥ 15,
  multi-step (≥3 calls) ≥ 400, history ≥ 800. These floors are the
  dev counts rounded down, not tuned targets.

### Simulator-verification step (mandatory, per trajectory)

Fresh `ToolEnv` per sample → execute gold calls in order → assert
call list identical to gold and every call succeeded (or the sample
is quarantined) → capture real results as observation text. This is
the same check that yielded 2842/2843 succeeded on dev. A training
example whose observations are not simulator outputs is not a
training example — it is fiction, and it must not enter the dataset.

### What this contract deliberately does NOT do

- No training, no model-generated data, no held-out use, no Kaggle
  actions, no inference/simulator/scorer/guard/config changes (all
  outside this thread's scope and bans).
- No new serialization invented silently: every format choice above
  is traceable to a named function in the `a2e832b` worktree.
- No decision on inner train/validation split, SFT-vs-alternative
  verdict, hyperparameters, or base-model choice — those belong to
  Threads C/B/main respectively. This contract is compatible with
  any inner split of dev, provided §5's template-leakage warning is
  honored.

## 8. Prototype verification `[CPU-AUDIT]`

`a_serialization_roundtrip.py` renders 4 dev samples through the
worktree's own `build_base_prompt` + `render_observation_prompt`,
executes gold calls in a real `ToolEnv`, and asserts executed calls
== gold calls and every observation line is well-formed JSON:

| Sample | Class | Gold calls | Installed tools | Base prompt chars |
|---|---|---|---|---|
| `train_0003` | normal | 5 | 52 | 24,412 |
| `train_0016` | normal | 5 | 49 | 23,419 |
| `train_0116` | ask_only | 1 | 35 | 20,373 |
| `train_0019` | empty | 0 | 13 | 8,574 |

Result: round-trip OK for all 4 (output `a_roundtrip.json`). This
proves data construction is a deterministic transform of
(sample + gold + simulator outputs) in the exact runtime text format.
It does not prove learnability — that is what the counts in §2–§3
are for.

## 9. Unknowns, blockers, and what would change this thread's conclusions

1. **Friend SFT: NOT AUDITED** (§6). Unblock needs: repo read access
   or a training manifest + version table + SFT data sample. Until
   then, no friend-based SFT conclusion (positive or negative) is
   available to any thread.
2. **ASR-text training set: does not exist locally.** Closing the
   M3/M4 gap needs a GPU pass running production ASR over train
   current + history audio. If that pass shows large WER on
   entities/times/negation, the SFT data decision changes (train on
   ASR text, or add ASR-robustness training); if WER is small, gold
   text training stands. Either way it is currently unmeasured.
3. **Organizer rules UNVERIFIED** (from standing context, not
   re-verified here): param counting (total vs non-embedding),
   derived-checkpoint cutoff interpretation, vLLM/XGrammar permission,
   Q-L/Q-D answers. If derived checkpoints (SFT adapters) were
   ruled ineligible, this entire contract would be moot — that
   question must be answered before any training commitment, and it
   is not answered by any artifact read here.
4. **Official evaluator absent.** All "scores" in prior work are the
   engineering proxy (state_hash-gated F1). SFT success criteria
   defined against the proxy (especially read-count dilution and
   hash-equality) may not transfer to the official metric. Thread C
   owns the evaluation design; this thread's data contract is
   proxy-agnostic by construction (gold trajectories hash-match by
   definition).
5. **Unmeasured in this thread:** gold trajectories with identical
   repeated calls (loop-guard interaction); cancellation-as-empty
   sub-class split; conditional-pattern recall beyond keyword
   heuristics; per-tool arg-value distributions beyond the slot
   classes in §3. None of these blocks construction, but each could
   shift class weights in the training set.
6. **Scope discipline restated:** old conclusions ("prompt ceiling",
   "ASR not bottleneck", "fine-tune bad") are NOT adopted here.
   Each is scoped to its original config/sample in prior reports:
   E0's 0.125 is gold-current + ASR-history on the proxy; E5's
   INCONCLUSIVE is 20 samples / 7 targets; the friend numbers are
   unverified. This audit's counts supersede none of them and are
   superseded by none of them — they measure different things.

## 10. Reproduction

```bash
cd ~/workspace/zalo-aic-round3
python3 analysis/overnight_capability_audit/a_dev_audit.py
# -> analysis/overnight_capability_audit/a_dev_audit.json
#    (dev 1237; held-out 308 dropped first; gold replay via ToolEnv)
python3 analysis/overnight_capability_audit/a_serialization_roundtrip.py
# -> analysis/overnight_capability_audit/a_roundtrip.json
```

Files written by this thread (only owned paths, no other files
modified, no git operations performed):
- `analysis/overnight_capability_audit/thread_a_data_audit.md` (this report)
- `analysis/overnight_capability_audit/a_dev_audit.py`
- `analysis/overnight_capability_audit/a_dev_audit.json`
- `analysis/overnight_capability_audit/a_serialization_roundtrip.py`
- `analysis/overnight_capability_audit/a_roundtrip.json`
