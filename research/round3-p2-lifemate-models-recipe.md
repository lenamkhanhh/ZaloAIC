# Round 3 — Priority 2: LifeMate model + recipe to replace the Qwen prompt-only baseline

**Scope.** Zalo AI Challenge 2026, LifeMate track only. Research draft, written outside the repo
(`~/workspace/zalo-aic-round3` was NOT edited). No contact with organisers, no training run,
no submission, no dataset download in this pass.
**Baseline commit for comparison:** `8d4721e` (repo `lenamkhanhh/ZaloAIC`).
**LifeMate constraints (unchanged):** whole system < 6B parameters, LLM < 5B, context ≤ 16,384 tokens,
models released before 2026-10-26, ≤ 30 s/sample on 1× A30, fully offline, deterministic decoding.
Never read `state.json` or any `<split>_environment/` file.

**Read-level labels used below.** `CARD` = Hugging Face model card text read. `CONFIG` = `config.json`
read. `PAPER` = paper text read. `CODE` = source file read line by line. `README` = repo README read.
`SECONDARY` = a third-party page/table quoting a primary source (never promoted to a primary fact).
`SNIPPET` = search-result text only. Anything not labelled as read is **unverified** and is stated as such.

---

## 1. What the repo already knows, and the exact gap

**Repo-known (baseline `8d4721e`, do not re-litigate):**

- Baseline: Qwen3-4B-Instruct-2507 + PhoWhisper-small = 4.244B. Qwen3-4B card, Apache 2.0,
  commit `cdbee75`, 4.0B total / 3.6B non-embedding, 36 layers, native context 262,144.
- xLAM-2-3b-fc-r and Hammer2.1-3b were OUT of the main shortlist **only** because card / licence /
  date were unverified on the original HF card — not because of size or capability.
- Hammer v1 vs Hammer 2.1 were conflated in earlier notes and must be kept separate.
- Qwen3-4B's tool-conversation format, inference template, and stateful-evidence separation
  still needed completion.
- Deep-dive 01 (constrained decoding) already covers XGrammar-via-vLLM / Outlines fallback and the
  Guidance licence conflict; this draft does not repeat it.

**Exact gap this draft closes:**

1. Provenance for the four named checkpoints: card, config, tool format, inference template,
   release date, total parameters, licence — resolved where a primary source was actually read,
   stated precisely where it was not.
2. Code-level reading of the Hammer training/evaluation pipeline (previously README-only).
3. A recipe that converts to ZAIC data without the circularity trap: running tools successfully
   does NOT prove the trajectory matches user intent, and `state_hash` taken from your own
   generated calls is NOT independent gold.
4. The smallest experiment that discriminates prompt-only / few-shot / retrieval / small-SFT
   on ZAIC-shaped evidence, not on transferred single-call scores.

**Shortlist verdict up front (detail in §3): NO checkpoint earns promotion into the main
shortlist in this pass.** Qwen3-4B stays the baseline. xLAM-2-3b-fc-r and Hammer2.1-3b stay
A/B-only pending an original-card licence read. Hammer-4B stays A/B-only (its base is now
identified from its own paper, but its own checkpoint licence is still unread, and its training
format is single-turn). One genuinely new screened candidate appears — Hammer2.0-3b, which
exists (10/2024) — but it is also single-turn-era and licence-unread, so it is screened, not
promoted. The direction that DOES change is the recipe: from "SFT on agent rollouts" to
**blueprint-first, pre-fixed gold, rejection-sampled trajectories** (APIGen-MT pattern) with
Hammer masking + irrelevance mixing as the augmentation layer — still unmeasured on ZAIC data.

---

## 2. Sources actually read

| # | Source | URL | What was read | Level |
|---|---|---|---|---|
| S1 | Qwen3-4B-Instruct-2507 card, commit `cdbee75` | https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/cdbee75f17c01a7cc42f958dc650907174af0554/README.md | Full card text: metadata, architecture, highlights, quickstart, Agentic Use, deployment notes | CARD |
| S2 | xLAM-2 official collection | https://huggingface.co/collections/Salesforce/xlam-2-67ef5be12949d8dcdae354c4 | Collection listing: repo ids, sizes, update stamps | CARD (collection) |
| S3 | xLAM series card (8B GGUF) | https://huggingface.co/Salesforce/Llama-xLAM-2-8b-fc-r-gguf | Series table + usage code (via search snippets in the prior pass; this pass: collection listing S2) | SNIPPET |
| S4 | APIGen-MT paper, arXiv 2504.03601v4 | https://arxiv.org/html/2504.03601v4 | Abstract, §1, §3 (framework), §4 (τ-bench case study), §5 (experiments), §6 (limitations), Appendix A/B headings; searched for "learning rate" (no hit) | PAPER |
| S5 | APIGen-MT dataset | https://huggingface.co/datasets/Salesforce/APIGen-MT-5k | Linked from paper abstract; dataset files NOT opened | PAPER-link only |
| S6 | Hammer paper, ICLR 2025, arXiv 2410.04587v1 | http://arxiv.org/html/2410.04587v1 | Abstract, §1, Tables 1/2/3/5, §5.4–5.6 ablations, §6 | PAPER |
| S7 | Hammer repo README + root listing, commit `ff415d9998180b5a68bbfdda3309ec04b472fb49` | https://github.com/MadeAgents/Hammer | Full README text incl. News (release timeline), Usage (vLLM client + built-in + Transformers), Fine-Tuning, Evaluation, Licenses headings; root file list | README |
| S8 | Hammer `train/data_processing.py` (293 lines) | https://github.com/MadeAgents/Hammer (cloned depth-1, `/tmp/hammer-src/train/data_processing.py`) | Entire file, line by line | CODE |
| S9 | Hammer `evaluation/evaluate.py` (118 lines) | https://github.com/MadeAgents/Hammer (cloned depth-1, `/tmp/hammer-src/evaluation/evaluate.py`) | Entire file, line by line | CODE |
| S10 | Hammer2.1-3b card | https://huggingface.co/MadeAgents/Hammer2.1-3b | Full card text (403 lines extracted); sidebar licence metadata did NOT render | CARD (licence metadata missing) |
| S11 | Dataloop Hammer2.1-3b page | https://dataloop.ai/library/model/madeagents_hammer21-3b/ | Licence label "MadeAgents other"; sibling pages for 0.5b/7b (cc-by-nc-4.0) and 2.0-0.5b/7b + Hammer-7b/1.5b (cc-by-4.0) | SECONDARY (mirror) |
| S12 | Zicos on Salesforce "open source" APIGen/xLAM | http://en.zicos.com/tech/i31988340-Decoding-Salesforces-open-source-APIGen-xLAM-for-enterprises.html | Quote of Salesforce senior AI research manager Shelby Heinecke: APIGen and xLAM released under "Creative Commons Attribution Non Commercial 4.0 International"; note that this "technically does not completely make these products open source" | SECONDARY |
| S13 | ToolACE paper + hub (via prior pass + Tool-R0 summary) | https://huggingface.co/Team-ACE ; https://huggingface.co/datasets/Team-ACE/ToolACE | Paper claims via search snippets; no ToolACE code file opened in this pass | SNIPPET |
| S14 | Qwen2.5-Coder-3B-Instruct card metadata (mirror quote) | RichardErkhov quant page quoting the original card (prior pass) | Card metadata "license: other, license_name: qwen-research"; Qwen2.5 table: 3B = "Qwen Research" while 0.5B/1.5B/7B/14B/32B = Apache 2.0 | SECONDARY |
| S15 | Oct 2026 SLM roundup tables (multiple) | Various secondary tables (prior pass) | Phi-4-mini, SmolLM3-3B, Ministral 3 3B, Granite 4.2 3B, Gemma 4, Qwen3.5, Nemotron 3 Nano 4B, MiniCPM5-2B, LFM2.5 | SECONDARY only |

**Explicitly NOT read in this pass (do not cite as read):** `config.json` for any candidate;
the original HF card licence metadata for xLAM-2-3b-fc-r, Hammer2.1-3b, or Hammer-4b; the
Hammer2.1 training code (no 2.1 training script exists in the Hammer repo — see §3.4);
APIGen-MT code (no public code repository was found — the paper links only the model
collection S2, the dataset S5, and https://apigen-mt.github.io/); any ToolACE code file;
any Vietnamese tool-use measurement for any candidate.

---

## 3. Model comparison

### 3.1 Table

| Candidate | Date (release / evidence) | Total params | Licence | Tool format / inference | Multi-step + irrelevance + recovery evidence | Verdict |
|---|---|---|---|---|---|---|
| **Qwen3-4B-Instruct-2507** (baseline) | July 2025 series ("2507"); exact first-commit date **unverified** at day precision — but July 2025 predates the 2026-10-26 cutoff by a wide margin, so not a blocker | 4.0B total / 3.6B non-embedding, 36 layers (CARD S1); native ctx 262,144, capped to 16K by ZAIC | Apache 2.0 (CARD S1) | Transformers `AutoModelForCausalLM`/`AutoTokenizer` + `apply_chat_template`; vLLM ≥ 0.8.5 / sglang ≥ 0.4.6.post1; Qwen-Agent recommended for agentic use (CARD S1). Non-thinking only, no `<think>` blocks | Card-claimed tool-usage improvement + BFCL-v3 61.9 (author-reported, single-call family). τ numbers on the card (TAU1 Retail 48.7 / Airline 32.0; TAU2 Retail 40.4 / Airline 24.0 / Telecom 13.2) state NO pass version, policy on/off, or trial count — **not comparable** with APIGen-MT's τ numbers (§3.5). No clarification, irrelevance, or recovery measurement on the card | **STAYS BASELINE.** Cleanest provenance of any candidate. Weakness is evidence type (general instruct model, no ZAIC-shaped stateful proof), not provenance |
| **xLAM-2-3b-fc-r** | Existence before cutoff strongly evidenced: BFCL v3 table dated 04/03/2025 in the APIGen-MT paper includes the 3B; series card BFCL table "as of 04/02/2025". Exact HF first-commit date **unverified** | 3B (collection S2); context 32k (max 128k via YaRN, series card SNIPPET); Qwen-2.5-based | **UNVERIFIED on the original card.** All secondary signals point to CC BY-NC 4.0 (S12 quote of Salesforce's Heinecke; Socket "Non-permissive License" flag; 2026 roundup stating CC-BY-NC-4.0 rules out commercial use for the 8B sibling). Whether NC satisfies ZAIC's "open-source model" rule is an **organiser question, not an assumption** | Canonical repo id resolved this pass: **`Salesforce/xLAM-2-3b-fc-r`** (collection S2). The `Llama-xLAM-2-3b-fc-r` form seen in the 8B GGUF card's usage code is a naming inconsistency — 70B/8B use the `Llama-` prefix, 1B/3B/32B use `xLAM-2-`. Do not download until the card itself is opened. vLLM: `--enable-auto-tool-choice --tool-call-parser xlam`; Transformers `apply_chat_template(messages, tools=tools)` (SNIPPET) | **Strongest stateful evidence of any challenger.** APIGen-MT paper (PAPER S4), Tables 1–2, pass@1 averaged over ≥ 5 trials, "only with the benchmark's think tool and no prompt optimizations": BFCL v3 overall 65.11 (single-turn non-live AST 82.94, Exec 81.88, live AST 58.69, multi-turn 56.00, relevance 94.44, **irrelevance 57.94**); τ-bench retail 44.4, airline 32.0, overall 38.2. **Counter-evidence in the same paper:** irrelevance 57.94 is weak vs ToolACE-2-8B 90.11 and GPT-4o FC 83.15 in the same table — good at calling relevant tools, comparatively poor at refusing irrelevant ones, which cuts directly against LifeMate's ask/refuse layer. τ overall 38.2 trails the 8B (46.7), 32B (54.6), 70B (56.2) siblings and GPT-4o (52.9) — the abstract's "small beats frontier" claim does NOT hold for the 3B. No recovery-after-failed-call measurement. No Vietnamese measurement | **A/B-ONLY.** Do not promote until (a) the original card's licence is read, and (b) the organiser confirms whether NC counts as "open-source" for a cash-prize competition. If both resolve favourably, it is the first A/B candidate because its τ evidence is genuinely stateful |
| **Hammer2.1-3b** | Exact release date **unverified**. Card note "New Update (June 2025)" is an update note, NOT a release date. Repo News (README S7) dates Hammer2.1 release 12/2024 — that is the generation's release window, not the 3B checkpoint's first-commit date | 3B class (card S10); Qwen 2.5 coder series base (card S10) | **UNVERIFIED for the 3B itself.** Dataloop mirror (S11) says "MadeAgents other" for the 3B, cc-by-nc-4.0 for 2.1-0.5b and 2.1-7b. The pattern makes CC-BY-NC highly likely for the 2.1 generation, but a sibling's licence is NOT the 3B's licence — do not assert CC-BY-NC-4.0 for Hammer2.1-3b as fact | Three paths on the card (S10) / README (S7): (1) Hammer client over vLLM (`HammerChatCompletion`/`HammerConfig`, user/assistant/tool roles, assistant tool calls as JSON object inside ``` fences, optional `respond` tool for final replies); (2) vLLM built-in (`--enable-auto-tool-choice --tool-call-parser hermes`, OpenAI-compatible `tools` array); (3) Transformers chat template (`apply_chat_template(messages, tools=tools, …)`). BFCL-v3 results on the card are **images only** — no numeric 3B values readable from card text | Card-claimed (S10) multi-step calling (multiple internal calls per request, active planning/gathering), multi-turn calling (continuous, context-aware), and "enhanced irrelevant-information inspection" (non-function-call response when functions are irrelevant). **These are card claims, not measurements read in this pass** — no BFCL numbers, no τ numbers, no recovery measurement, no Vietnamese measurement, and no 2.1 training code in the repo (§3.4). Shape is right; evidence is not | **A/B-ONLY.** Best-shaped Hammer candidate on paper, weakest evidence of the three named challengers. Promote only after its own card licence + date are read AND a ZAIC-shaped A/B (see §6) shows it beating the baseline on irrelevance/ask behaviour, not just on call accuracy |
| **Hammer-4B** (v1 generation) | Existence before cutoff evidenced: BFCL table "as of date 09/20/2024" in the paper (S6) includes Hammer-4B; repo News (S7) dates Hammer v1 release 09/2024. Exact HF first-commit date **unverified** | 4B class (paper S6). Base identified this pass from paper Table 5: **Qwen1.5-4B-Chat** (ablation pairs Qwen1.5-4B-Chat → Hammer-4B; Qwen2-7B-Instruct → Hammer-7B; Qwen2-1.5B-Instruct → Hammer-1.5B). Base licence NOT re-checked here — do not assume it from the pair | **UNVERIFIED for the 4B itself.** Dataloop pattern for the v1 generation is cc-by-4.0 (Hammer-7b, Hammer-1.5b pages, S11), which would be permissive — but no Dataloop page for Hammer-4b was found, and a sibling's licence is not the 4B's licence. Possible permissive dark horse IF its own card confirms CC-BY-4.0 + pre-cutoff date | Same Hammer client / vLLM / Transformers paths as 2.1 (README S7), but the **v1 SFT format is single-turn** (see §3.4): prompt block → JSON list, no tool-observation role in training. Do not assume the 2.1 multi-turn template applies to the v1 checkpoint | Paper (S6), BFCL v2 era, "as of 09/20/2024": overall 76.05, AST 69.59, Exec 80.82, **irrelevance 68.66**, relevance 90.24. Academic benchmarks: F1 Func+Args average 71.35 (API-Bank L-1/L-2, Tool-Alpaca, Seal-Tools single-tool, Nexus Raven — per-call F1, NOT final-state success). **No τ-bench, no multi-turn stateful evidence, no recovery measurement.** Single-turn-era by design: the 2.1 card says 2.1 "maintains" 2.0's single-turn functionality while ADDING multi-step/multi-turn — i.e. v1 lacks them | **A/B-ONLY, lower priority than xLAM-2-3b.** Its only edge is the possible permissive licence. Its format is the worst fit for LifeMate's multi-step shape. Test only if its own card confirms CC-BY-4.0 |
| **Hammer2.0-3b** (newly screened) | Generation released 10/2024 (repo News, S7: "lightweight Hammer 2.0 models (0.5B, 1.5B, 3B, 7B)"). Checkpoint's own first-commit date **unverified** | 3B class | **UNVERIFIED** (no card opened; Dataloop pattern for 2.0-0.5b/7b is cc-by-4.0, S11 — not proof for the 3B) | Presumably the Hammer client / hermes-parser paths (S7), but the 2.0-3b card itself was NOT opened | Single-turn-era by the same 2.1-card logic as Hammer-4B. No numbers read for the 3B | **SCREENED, NOT PROMOTED.** Existence confirmed; everything else unverified. Only worth a card read if a permissive-licence 3B tool model is needed and Hammer2.1-3b's licence fails |
| **Qwen2.5-Coder-3B-Instruct** (as SFT base, not as tool checkpoint) | — | 3.09B total / 2.77B non-embedding, 36 layers, ctx 32,768 (SECONDARY S14) | **NOT Apache 2.0.** Card metadata "license: other, license_name: qwen-research" (SECONDARY S14); Qwen2.5 table lists the 3B as "Qwen Research" while 0.5B/1.5B/7B/14B/32B are Apache 2.0 | — | — | **CORRECTION to any Apache assumption.** If the SFT base must be permissively licensed, Qwen2.5-Coder-3B is NOT a clean Apache base — this strengthens Qwen3-4B (Apache 2.0, CARD) as the SFT base. Budget if it were used: 3.09B + PhoWhisper-small 0.244B = 3.334B; + medium 0.769B = 3.859B (arithmetic from round-2 sizes, not a new measurement). Licence status vs ZAIC's "open-source" rule is itself an organiser question |
| **Phi-4-mini-instruct** (control only) | Announced Feb 2025 / published early Mar 2025 (SECONDARY S15) | 3.8B, 128K ctx, text-only (SECONDARY S15) | MIT (SECONDARY S15) | Dedicated function-calling format (SECONDARY S15) | No stateful tool-use evidence read; no Vietnamese measurement | **CONTROL ONLY for prompt-only comparison, not a tool-specialised challenger.** Promote only after its original card is read |
| **SmolLM3-3B, Ministral 3 3B, Granite 4.2 3B, Gemma 4 E2B/E4B, Qwen3.5 family, Nemotron 3 Nano 4B, MiniCPM5-2B, LFM2.5** | 2026 dates claimed in roundups for several families — **unverified against original cards** | Totals in roundups include encoders where present (the roundup itself warns Hub totals include vision/audio encoders) — **do not use for budget arithmetic** | Apache 2.0 claimed in roundups for several — **secondary only** | Tool claims (XML/Python-style calls, hermes/mistral parsers) — **secondary only** | No ZAIC-shaped evidence read for any | **SCREENED, NOT PROMOTED.** None may enter the shortlist on the basis of secondary tables. Each needs its own card + config + date check, and VL/audio-encoder parameter accounting, before any claim |

### 3.2 What "stateful" means here, and why the table separates it

- **Single-call evidence** = one prompt → one call list, scored against gold calls (BFCL AST/Exec,
  Hammer's `evaluate.py` per-call P/R/F1). It says nothing about dependency chains, observation
  use, or final-state correctness.
- **Stateful evidence** = multi-turn interaction against a live environment, scored on final
  state / task completion (τ-bench pass@1, LifeMate's `state_hash` gate + tool F1). Only
  xLAM-2-3b (via APIGen-MT's τ results) has stateful evidence among the challengers — and it is
  still not ZAIC evidence (different tools, policies, language, no `state_hash` gate).
- **Never transfer** a BFCL number to LifeMate. BFCL's irrelevance category is the closest
  analogue to LifeMate's ask/refuse behaviour, and even there xLAM-2-3b's 57.94 warns against
  assuming a tool-specialised model refuses well.

### 3.3 Qwen3-4B: what is now complete, what is not

- **Complete (CARD S1):** licence Apache 2.0 with licence link; 4.0B/3.6B, 36 layers, GQA
  32 Q / 8 KV heads (card text), native context 262,144; non-thinking mode only; card-claimed
  improvements in instruction following, reasoning, text comprehension, maths, science, coding
  and tool usage, plus long-tail multilingual coverage (a claim, not a Vietnamese measurement);
  Transformers quickstart + `apply_chat_template`; vLLM/sglang deployment; Qwen-Agent
  encapsulation of tool-calling templates and parsers.
- **Not complete:** `config.json` was NOT opened (a secondary DeepWiki matrix lists hidden 2560,
  FFN 9728, 32/8 heads — SECONDARY, do not upgrade it); exact first-commit/release date at day
  precision NOT read (July 2025 series is enough for the cutoff, not enough for a dated citation);
  the card's τ numbers lack pass version / policy / trial count, so they cannot be ranked
  against APIGen-MT's τ numbers.

### 3.4 Hammer code: what `CODE` reading actually established (S8, S9)

Repo: `MadeAgents/Hammer`, Apache-2.0 (repo code licence — **not** the checkpoint licence),
commit `ff415d9998180b5a68bbfdda3309ec04b472fb49`, created 2024-10-02, 125 stars.
Directories: `client/`, `data/`, `evaluation/`, `scripts/`, `train/`.

**`train/data_processing.py` (293 lines, CODE):**

- Inputs (not in the repo, must be downloaded): `data/train/xlam_function_calling_60k.json`
  and `data/train/XLAM-7.5k-Irrelevance.json`. Note the filename forms differ across sources
  (README link `MadeAgents/XLAM-7.5k-Irrelevance`, dataset page `MadeAgents/xlam-irrelevance-7.5k`
  per prior pass, code filename `XLAM-7.5k-Irrelevance.json`) — resolve at download time, do not
  assert one form.
- Pipeline: concatenate 60k + 7.5k, shuffle, repeat **3×** (`data_three`); then per instance,
  with probability 2/3 (code comment: "Masking ratio p=1-1/3=0.67"), apply the full masking chain,
  else keep the instance unchanged. **Discrepancy to note:** the paper's ablation varies the
  share of masked instances (e.g. "mask 0.33" = 33% of instances masked) and finds high ratios
  slow same-task learning while helping cross-task generalisation; the shipped script masks
  2/3 of instances, and masks them fully. The paper's ablation number is not the script's number.
- `replace_function_names_new`: every tool name replaced by a random 5–15 character string
  from `[A-Za-z0-9_.]`; answers renamed consistently; tools deduplicated, then padded with
  random duplicates if dedup shrank the list, then shuffled.
- `replace_param_names_new`: every parameter name replaced by a random 4–10 character string,
  answers renamed consistently; same dedupe/pad/shuffle.
- `replace_param_default_values_news`: only when an answer's argument equals the tool's
  `default` value does it replace the default (int +1..4, float +random, string random 5 chars)
  and rewrite the parameter description and the query occurrences — this is the
  "default-value trap" fix: the model must read the query, not copy the default.
  (`check_default_values_news` is the variant that also requires the default to be absent
  from the query.)
- **Prompt format (`get_hammer_prompt`) is single-turn:** `[BEGIN OF TASK INSTRUCTION]`
  (3 tasks: call tools; if none usable, refuse; if parameters missing, point it out) +
  `[BEGIN OF AVAILABLE TOOLS]` + `[BEGIN OF FORMAT INSTRUCTION]` (strict JSON list, empty
  list `[]` if no call) + `[BEGIN OF QUERY]`; output = label JSON inside ``` fences.
  **There is no multi-turn history and no tool-observation role in the v1 training format.**
  This is the decisive format limitation for LifeMate: Hammer v1 teaches one-shot call
  generation, not observation-conditioned chaining.
- Random seed: `random.seed(12)` (set twice). Training itself is delegated to LLaMA-Factory
  (README S7: download LLaMA-Factory into `train/`, replace `<MODEL>`); no Hammer training
  hyperparameters are in this repo.

**`evaluation/evaluate.py` (118 lines, CODE):**

- Parses predictions by stripping ```json / ``` fences and unwrapping a `tool_calls` key;
  computes P/R/F1 separately for API names and parameters with exact string match after
  `str()` conversion, skipping empty-string parameters; picks the best-matching gold call
  per predicted call.
- **Quirk that matters for reuse:** format errors and empty predictions hit `continue` before
  contributing to predicted counts (gold counts were already accumulated), so an empty
  prediction penalises recall but not precision, and irrelevance is NOT measured by this
  script — it must be measured elsewhere. Do not reuse this script as a LifeMate scorer:
  LifeMate needs the `state_hash` gate + tool F1 + ask/empty handling, none of which this
  script implements.

**What the repo does NOT contain:** any Hammer 2.1 training script, any multi-turn trajectory
format, any recovery/clarification training data, any ZAIC-shaped evaluation. The 2.1 card's
multi-step/multi-turn claims therefore have **no code in this repo** to inspect. The client
(`client/hammer.py`) was not read line by line — README usage (S7) is sufficient for the
inference paths and is labelled README, not CODE.

**Hammer irrelevance data construction (PAPER S6 + CODE S8):** 7,500 instances sampled from
xLAM-60k with the ground-truth function removed from the candidate list and relabelled as
irrelevant (empty list). Paper §5.6 ablation (10,000 sampled instances, varying mix): an
**inverse relationship** between irrelevance detection and function-calling capability, with
optimal overall performance at **~10% irrelevance share** — hence the 7.5k target. The paper
also states the underlying trade-off explicitly: fine-tuning only on function-calling data can
REDUCE irrelevance detection. For ZAIC, the 10% figure is a starting ratio to A/B, not a
transferred optimum — ZAIC's ask/refuse surface (meta tool `sys.ask_missing_info`) differs
from Hammer's empty-list refusal.

### 3.5 The τ-number comparability trap (read this before quoting any τ score)

- APIGen-MT τ numbers (PAPER S4): pass@1 averaged across **at least 5 trials**, "only with the
  benchmark's think tool and no prompt optimizations". xLAM-2-3b: retail 44.4, airline 32.0,
  overall 38.2.
- Qwen3-4B card τ numbers (CARD S1): TAU1 Retail 48.7 / Airline 32.0; TAU2 Retail 40.4 /
  Airline 24.0 / Telecom 13.2 — with **no pass version, policy on/off, or trial count stated**.
- These two sets **cannot be ranked against each other**. Any draft, table, or message that
  puts Qwen3-4B's 48.7 above xLAM-2-3b's 44.4 (or vice versa) without this caveat is wrong.
  The same applies to the repo's round-2 τ-bench notes: τ numbers must always carry pass
  version + policy on/off + domain + backbone (e.g. GPT-4o pass¹ with policy: retail 61.2 /
  airline 33.2; without policy: 56.8 / 10.8).

---

## 4. Prompt-only vs few-shot vs retrieval vs small-SFT

| Approach | What it reuses (source) | Cost / risk for LifeMate | When it wins |
|---|---|---|---|
| **Prompt-only (current baseline)** | Qwen3-4B card template + Qwen-Agent parsers (S1); repo deep-dive 01 constrained decoding (XGrammar/Outlines) for schema validity | Cheapest; no training; no licence question beyond Apache 2.0. Weakness: no learned irrelevance/clarification/recovery behaviour; every behaviour must be elicited by prompt + validator + loop guard, and the validator cannot teach intent | If the §6 experiment shows prompt-only within noise of SFT on hash-correct rate AND on ask/irrelevance accuracy, keep it — SFT's marginal gain would not justify its licence + data risk |
| **Few-shot (in-context trajectories)** | APIGen-MT blueprint trajectories (S4) reformatted as exemplars; Hammer prompt format (S8) as the exemplar shape | Context cost: each exemplar eats from the 16K budget; multi-turn exemplars are long. Risk: exemplar tool names leak into outputs (the exact failure Hammer masking was designed to prevent — see §5.4). Mitigation: mask exemplar names the Hammer way, or use exemplars only for the ask/clarify shape, not for tool names | If SFT is blocked (licence, time, GPU) but prompt-only fails specifically on the ask/clarify shape, few-shot is the cheapest patch for that one behaviour |
| **Retrieval (RAG over train gold + catalog)** | ZAIC train samples + tool catalog (repo-known: train ~1,600 labelled samples with transcripts + gold tool_calls/final_state, per 2026-10-26 portal notes — **to be verified by unzipping**); RECOVER-style closed candidate retrieval (prior round: N-best 5 + closed retrieval from tool reads in the same sample) | Retrieval must be inside the 6B budget (embedding model counts if it runs at inference — budget rule from round 2: total inference ≤ 6B including auxiliaries; whether the organiser counts embeddings is itself an open question in gaps.md). Risk: retrieved gold-adjacent trajectories can leak entities into the current sample; retrieval must be keyed on tool/dependency shape, not on entity values | If the failure mode is tool selection among many similar tools (catalog-scale), not argument filling. Retrieval helps selection; it does not teach recovery or refusal |
| **Small-SFT (the recipe in §5)** | APIGen-MT filtered BC (S4) + Hammer masking + irrelevance mix (S8, S6) + ToolACE dual verification as a process pattern (S13, SNIPPET) | Highest upfront cost (data build + training + licence diligence), highest ceiling: it is the only option that can teach irrelevance, clarification, AND recovery as behaviours rather than prompt tricks. Risks: (1) licence of the base (Qwen3-4B Apache is clean; Qwen2.5-3B is Qwen Research — §3.1); (2) circular gold (§5.1); (3) catastrophic narrowing to train tool names (mitigated by masking); (4) fine-tune checkpoint cutoff interpretation is UNVERIFIED (gaps.md) — a fine-tuned checkpoint's "release date" for the pre-2026-10-26 rule needs an organiser answer before training | If the §6 experiment shows a behaviour gap (ask accuracy, irrelevance accuracy, or recovery rate) that prompt/few-shot/retrieval do not close, AND the base licence + cutoff questions resolve. SFT on Qwen3-4B (Apache) is the only SFT path recommended here |

**Reusable sources, ranked by reusability for ZAIC:**

1. **APIGen-MT (S4)** — the only source with a complete, validated multi-turn data pipeline
   (blueprint → committee → interplay → rejection sampling). Reuse the pipeline, not the data
   (τ-bench retail/airline data does not transfer to ZAIC's Vietnamese apps).
2. **Hammer (S6, S8, S9)** — reuse the masking implementation and the irrelevance-mix ratio
   as a starting point, and the evaluation script's per-call P/R/F1 as a diagnostic (not as the
   LifeMate scorer). Do NOT reuse the single-turn prompt format for LifeMate trajectories.
3. **ToolACE (S13, SNIPPET)** — reuse only the process ideas: multi-agent dialogue generation
   guided by a formalised thinking process + complexity evaluator, and dual-layer (rule-based +
   model-based) verification. Its 8B checkpoint is over the 5B LLM cap and is excluded.
   Its BFCL v3 rows must not be merged: ToolACE-8B overall 87.54 single-turn but multi-turn
   7.75 in one listing; ToolACE-2-8B overall 68.39, multi-turn 36.88, irrelevance 90.11 in
   another — the original ToolACE-8B's multi-turn weakness is a caution against transferring
   single-turn strength to LifeMate.

---

## 5. The ZAIC recipe (blueprint-first, no circular gold)

### 5.1 The integrity rule, stated operationally

- **Gold is fixed before any student trajectory exists.** A blueprint = (user instruction `q`,
  ground-truth action sequence `a_gt`, expected final outputs `o_gt`) authored and validated
  independently of the student model. This is APIGen-MT Phase 1 (S4).
- **Success is judged against that pre-fixed gold**, never against a state the student itself
  produced. In ZAIC terms: the evaluator's `state_hash` must never be computed from the
  student's own calls and then treated as an independent label. A trajectory is kept only if
  its final environment state matches the blueprint's expected final state AND its final
  responses match `o_gt` (APIGen-MT Phase 2 rejection sampling: keep only `r = 1`, up to 3
  attempts per task, union of unique successful trajectories).
- **What this means for reusing ZAIC train gold:** train samples already carry gold
  `tool_calls`/`final_state` (per 2026-10-26 portal notes — verify by unzipping). Using those
  as SFT labels is NOT circular in the forbidden sense, because the gold was authored by the
  organisers, not by the student. What IS forbidden is: generating new trajectories with the
  student, taking their resulting state as gold, and training on that. New synthetic blueprints
  must go through the §5.3 validation before their trajectories become labels.
- **Failed trajectories are not gold.** APIGen-MT discards them (paper §6 suggests they could
  be contrastive signal — a suggestion, not a validated recipe). For ZAIC, failed-then-fixed
  rollouts may be used ONLY as recovery training data where the FIX is verified against the
  pre-fixed gold (§5.5), never where the failed path itself is labelled correct.

### 5.2 Data

1. **Primary: ZAIC train gold** (~1,600 labelled samples, transcripts + gold tool_calls/final_state
   — verify by unzipping; sizes/counts unverified until then). Split as in round 2: train_fit /
   train_cal / train_holdout, preferring a business/type split; leave-one-business-type-out
   prioritised. Public test is for format/latency + official sanity submission only — never
   tune thresholds from the leaderboard, never train on it.
2. **Synthetic blueprints (only if train gold is insufficient for a behaviour):** built from
   the ZAIC tool catalog + domain policies, following APIGen-MT Phase 1 (S4):
   - Model APIs as a directed dependency graph (edge A→B if B's inputs can depend on A's
     outputs and the pair is policy-permitted); random walks on the graph.
   - Samplers: APIs (distinguish state-exploring `read` APIs from state-changing `write` APIs;
     sample `write` APIs as the core of `a_gt`, leave `read` use flexible), policies (domain
     rules sampled per domain; complexity driven by number of write calls + policy
     constraints), domain data (sampled with metadata, not whole tables, to bound context),
     personas (PersonaHub-style descriptions), few-shot examples.
   - Generator output per task: `<thought>`, user `<instruction>` (`q`), ground-truth
     `<actions>` (`a_gt`), expected final `<outputs>` (`o_gt`).
   - **Reverse Task Recombination** for complexity: concatenate independently validated simpler
     tasks (same persona), re-run the policy check on the combined sequence, synthesise a
     combined instruction, re-validate from Stage 2 (Stage 1 skipped for constituents, policy
     re-check still required).
   - APIGen-MT collection statistics (PAPER S4, for scale planning only): task-config success
     70% with agentic feedback vs 28% without; trajectory success 67%; 1–29 turns per
     trajectory; avg 7 tool calls, 6 user turns per trajectory; avg 12 turns for a strong
     model (gpt-4o) to complete a task. Teacher models used by the paper were gpt-4o and
     DeepSeek V3 (S4 §4.3) — proprietary teachers are a cost/licence note for reuse, but the
     generated ZAIC trajectories are grounded in ZAIC's own simulator, not in teacher weights.
3. **What NOT to use as data:** public/private test samples for training; the student's own
   rollouts as gold; invented entities in ASR-noise variants (see §5.4).

### 5.3 Label verification (four gates, all must pass)

Adapted from APIGen-MT Phase 1 validation (S4), mapped onto ZAIC's own tooling:

1. **Format gate:** required components present, valid JSON calls, string outputs.
2. **Execution gate:** simulate each `a_gt` action in `zaic_tools` on a **fresh simulator
   state**; capture the cumulative state effect as a diff (APIGen-MT's `diff_patch`, git-diff-like).
   A blueprint whose gold does not execute cleanly is rejected, not repaired by hand-editing
   the expected state to match a broken action.
3. **Policy/intent gate:** domain policies translated into checks run against the simulated
   trace — this catches cross-action violations (e.g. action B invalid given action A's state
   change) that single-call checks miss. Intent check: the trace must satisfy the instruction
   `q`, not merely execute without error. Execution success ≠ intent match (this is the
   integrity rule restated as a gate).
4. **Committee gate:** diverse-model judges scoring Correctness, Completeness, Satisfaction,
   Creativity against the diff vs `q`, majority vote per metric (APIGen-MT Stage 2). Tasks
   above threshold are accepted; failures return consolidated committee feedback to the
   generator for reflection (paper: max 3 reflection turns retail, 5 airline — ZAIC should
   pick its own cap and record it, not copy these numbers blindly).
5. **Trajectory gate (Phase 2):** simulated human (LLM guided by `q` + persona, revealing
   details turn by turn) interacts with a test agent; keep ONLY trajectories achieving the
   goal (`r = 1`) against the pre-fixed gold, up to 3 attempts per task. Human stability:
   Best-of-N (N = 4) + self-critique for the human LLM (paper: validated on τ-bench test set
   for cross-trial consistency). Paper limitations (S4 §6) that carry over: Best-of-N +
   self-critique reduces but does not remove human-simulation stochasticity; multi-stage
   validation incurs computational overhead; RL/self-improvement is future work, not part
   of the validated recipe.

### 5.4 Conversation format (map ZAIC onto the chosen base's template — do not invent a new one)

- **Qwen3-4B (recommended base):** standard Qwen chat template via `apply_chat_template`
  with `tools` (S1); tool observations as `tool`-role messages; final answer as the
  `respond`-shaped assistant message. The submission itself is ZAIC `tool_calls` JSON, not chat
  text — the template must be adapted so the model's emitted text parses exactly to the
  submission JSON (deep-dive 01's constrained decoding is the enforcement layer, not the
  format itself).
- **Hammer2.1 (if A/B'd):** Hermes-style JSON-in-code-fence via its chat template, or the
  Hammer client conversation shape (user/assistant/tool roles, §3.1). Its `respond` tool is
  the analogue of ZAIC's final response — but ZAIC's meta tool is `sys.ask_missing_info`,
  which is NOT the same as Hammer's `respond`: `ask` is a request for missing information
  before acting, `respond` is a final reply. Map them explicitly; do not conflate them.
- **xLAM-2 (if A/B'd):** xLAM chat template + `tools` via `apply_chat_template`, vLLM
  `xlam` parser (SNIPPET). Same ask-vs-respond mapping warning applies.
- **Training loss (APIGen-MT §5.1, PAPER S4):** split trajectories at every assistant
  response; train to predict ONLY assistant response tokens, with prompt and other messages
  masked; joint training with single-turn function-calling data + other agentic data is the
  paper's recipe. Framework in the paper: LLaMA-Factory, full fine-tuning, DeepSpeed ZeRO
  stage 3, FlashAttention 2, bf16, AdamW, at most 3 epochs on an H200 node. **Learning rate
  and batch size were NOT found in the arXiv HTML v4 text (searched "learning rate": no hit)
  — do not invent them; they are build-time choices to be recorded in `requirements.lock`
  style, not copied from this draft.**
- **Augmentation (Hammer-derived, ZAIC-mapped):**
  - **Function masking (S8):** apply the shipped masking chain (rename tools 5–15 chars,
    rename params 4–10 chars, rewrite defaults that equal answer values) to a starting
    share of SFT instances. Start from the paper's ablation lesson, not the script's 2/3:
    high mask ratios slow same-task learning and help cross-task generalisation (S6 §5.5),
    so start low (the paper's ablation grid includes 0.33; the script's 0.67 is the shipped
    default, not a recommendation) and A/B the ratio on the held-out split. Masking forces
    the model to read tool descriptions, which is exactly the defence against memorising
    ZAIC tool names from train.
  - **Irrelevance mix (S6 §5.6):** start at ~10% irrelevance examples (paper optimum on its
    ablation), built the Hammer way — remove the correct tool from the candidate list and
    label the correct behaviour (ZAIC: empty list / `ask` per the meta tool, NOT Hammer's
    `[]` alone — the label must be ZAIC's ask shape, or the model learns the wrong refusal).
    A/B the ratio; the paper's inverse trade-off (more irrelevance data ↔ weaker calling)
    means the ratio is a tunable, not a constant.
  - **Clarification examples:** where a slot is ungroundable from transcript + reads, the
    label is `sys.ask_missing_info` for exactly that slot — never a guessed value, never a
    write with a placeholder. (The evaluator's ask-after-write rule is UNVERIFIED — gaps.md
    Q-L — so clarification examples must be built for the pre-write position only until
    that question resolves. This is a known blocker for the clarification slice of the recipe.)
  - **ASR-noise variants:** only from real train transcripts (audio_text) and their gold
    slots — never invented entities. A noisy variant keeps the same gold; the model must
    learn to ground through noise, not to memorise a cleaned transcript.
  - **Vietnamese:** all synthetic instructions, personas, and clarification texts are
    Vietnamese, matching the audio/transcript language. No candidate has a Vietnamese
    tool-use measurement (§3), so Vietnamese slot accuracy is a first-class metric in §6,
    not an afterthought.

### 5.5 Trajectories, including recovery trajectories

- **Normal trajectories:** blueprint → simulated human-agent interplay → rejection sampling
  vs pre-fixed gold (§5.3 gate 5). Keep the union of unique successful trajectories.
- **Recovery trajectories (the only sanctioned use of failed rollouts):** take a failed
  rollout, then construct a fixed continuation where (a) the failure is identified from the
  tool observation (error, empty result, wrong entity), (b) the corrective action is chosen
  from the blueprint's `a_gt` or from a fresh read whose result is consistent with `a_gt`,
  and (c) the final state matches the pre-fixed expected state. If any of (a)–(c) fails,
  discard the trajectory — do not label the failed path as correct, do not relabel the
  expected state to match what the student did. RECOVER (prior round: N-best 5 + closed
  candidate retrieval from tool reads in the same sample + verify-and-apply; money/date/ID
  never fuzzy) is the retrieval-side complement: at inference, after a failed call, retrieve
  candidate entities from the same sample's reads and verify before re-applying. Recovery
  is a recipe addition, not a checkpoint property — no candidate in §3 has a published
  recovery-after-failed-call measurement.
- **Multi-step dependencies:** blueprints must include at least one dependency chain
  (B's input comes from A's output) per the APIGen-MT graph walk, plus at least one
  policy-constrained chain (B invalid until A changes state). Single-call blueprints alone
  do not teach LifeMate's core skill and must not dominate the mix.

### 5.6 What the recipe deliberately does NOT do

- No training on public/private test. No threshold tuning from the leaderboard.
- No `state_hash` from student rollouts treated as gold (§5.1).
- No masking of money/date/ID values into fuzzy matches (repo deep-dive 02 rule: exact-only).
- No "faster diffusion" or latency optimisation as the paper claim — latency is a constraint
  (≤ 30 s/sample), measured in §6, not a contribution.
- No claim that this recipe works on ZAIC until §6 runs on ZAIC data.

---

## 6. The smallest experiment that discriminates the options

**Design (not yet run — no A30, no ZAIC-data run has happened in this pass):**

- **Data:** one fixed ZAIC train held-out split (train_holdout, business/type split per round 2),
  identical for every arm. No public-test tuning. Greedy decoding, fixed seeds (deterministic
  decoding per ZAIC rules).
- **Harness (identical for every arm):** the same validator, loop guard, selective-read policy,
  and completion predicate from deep-dive 01 / the parent's fix round — the harness must not
  differ between arms, or the comparison measures the harness, not the model.
- **Arms (in order, stop when an arm wins on the decision metric):**
  1. Qwen3-4B prompt-only (baseline).
  2. Qwen3-4B + few-shot (masked-name exemplars, §4).
  3. Qwen3-4B + retrieval (tool/dependency-shape retrieval, §4).
  4. Qwen3-4B small-SFT (§5 recipe, one training run, hyperparameters recorded).
  5. xLAM-2-3b-fc-r prompt-only — **only if** its licence question resolves favourably.
  6. Hammer2.1-3b prompt-only — **only if** its licence question resolves favourably.
- **Metrics (all five, no single-metric decision):**
  1. **Hash-correct rate** (final-state match) — the primary LifeMate outcome.
  2. **Tool F1** (repo selection metric: mean of hash-correct ? tool F1 : 0 — hash-correct
     rate alone is diagnostic only, per round 2).
  3. **Irrelevance / ask accuracy:** on samples where no tool applies or a slot is
     ungroundable, share where the model correctly asks/refuses instead of calling.
  4. **Recovery rate:** on samples where the first call fails (injected failure or natural
     failure in the rollout), share where the model recovers to the correct final state
     without an extra write of a guessed value.
  5. **Latency per sample** (share ≤ 30 s) on the available hardware, reported as a
     constraint check, not as a ranking metric. A30 latency is unmeasured for every arm.
- **Decision rule (proposed, not yet adopted):** promote an arm over prompt-only only if it
  beats the baseline on the §4 decision metric (mean hash-correct ? tool F1 : 0) AND does not
  regress on irrelevance/ask accuracy AND does not regress on recovery rate. A win on call
  accuracy alone, with an irrelevance regression, is a loss for LifeMate (this is exactly the
  xLAM-2-3b trap in §3.1: relevance 94.44, irrelevance 57.94).
- **Vietnamese slice:** report metrics 1–4 separately on the Vietnamese slot subset (names,
  money, dates, IDs exact-only). A model that wins overall but loses on Vietnamese slots
  does not win for LifeMate.

---

## 7. What remains unproven (do not close these by assumption)

1. **Licences on original cards:** xLAM-2-3b-fc-r, Hammer2.1-3b, Hammer-4b, Hammer2.0-3b —
   none read from the original card's licence metadata/LICENSE file in this pass. Secondary
   signals point to CC BY-NC for xLAM-2 and the Hammer 2.1 generation, and to CC-BY-4.0 for
   the Hammer v1/v2.0 generation — all secondary, all needing a card read.
2. **Whether CC BY-NC or Qwen Research licences satisfy ZAIC's "open-source model" rule**
   for a cash-prize competition — an organiser question (gaps.md Q-L/Q-D family, NOT sent).
3. **Exact release dates** at day precision for Qwen3-4B-Instruct-2507, xLAM-2-3b-fc-r,
   Hammer2.1-3b, Hammer-4b. (All are strongly evidenced as pre-cutoff except that day
   precision is missing; the cutoff itself is not at risk for any of them on current evidence.)
4. **`config.json`** for every candidate (total params from config, architecture, context).
5. **Vietnamese tool-use performance** of every candidate — no measurement exists in this pass.
6. **ZAIC-stateful evidence** for every candidate — no candidate has been run on ZAIC data.
7. **Whether train gold may be reused as SFT labels** without re-derivation — §5.1 argues it
   is not circular (organiser-authored gold), but this is a recipe argument, not an organiser
   ruling; confirm before training if there is any doubt.
8. **The evaluator's ask-after-write rule** (gaps.md Q-L) — blocks the clarification slice of
   the recipe until resolved.
9. **Fine-tune checkpoint cutoff interpretation** — whether a checkpoint fine-tuned after
   2026-10-26 from a pre-cutoff base counts as "released before 2026-10-26" (gaps.md, NOT sent).
10. **A30 latency** for every arm, and the total-vs-non-embedding parameter counting rule
    (gaps.md) — Qwen3-4B is 4.0B total / 3.6B non-embedding; which number the organiser counts
    decides headroom for the ASR model (4.0B + 0.244B = 4.244B total-counted; 3.6B + 0.244B =
    3.844B non-embedding-counted — both under 6B, but the rule still needs confirming for
    any future 5B-edge candidate).
11. **APIGen-MT training hyperparameters** (learning rate, batch size) — not found in the
    arXiv HTML v4 text; do not copy numbers from elsewhere without a source.
12. **Hammer2.1 training data/code** — no 2.1 training script in the Hammer repo; its
    multi-step/multi-turn claims rest on its card alone.
13. **The ZAIC dataset itself** — zip sizes, exact business/question counts, full rulebook /
    README / calendar contents, LifeMate catalog, Docker base image, and whether public_test
    truly has no gold are all still unverified (unzipping is the single most important next
    verification, per the repo's gaps.md).

---

## Appendix: corrections this draft makes to earlier notes

- **Qwen2.5-Coder-3B is NOT Apache 2.0** (Qwen Research licence, SECONDARY S14). Any earlier
  note treating the 3B coder as an Apache base is corrected here; Qwen3-4B is the clean
  Apache SFT base.
- **Hammer-4B's base is Qwen1.5-4B-Chat** (paper Table 5, S6) — previously "unverified".
  Its checkpoint licence is still unverified; do not extend the base's licence to the checkpoint.
- **xLAM-2-3b's canonical repo id is `Salesforce/xLAM-2-3b-fc-r`** (collection S2) —
  the `Llama-xLAM-2-3b-fc-r` form is a naming inconsistency in the 8B card's usage code.
- **Hammer2.0-3b exists** (10/2024, repo News S7) — previously unexamined. Screened, not promoted.
- **Hammer masking ratio:** the paper's ablation grid and the shipped script's 2/3 are
  different numbers (§3.4). Quote them separately; never cite "0.67" as the paper's recommendation.
- **ToolACE BFCL rows must not be merged** (§4): original ToolACE-8B multi-turn 7.75 vs
  ToolACE-2-8B multi-turn 36.88 / irrelevance 90.11 are different listings.
- **τ numbers must carry pass version + policy + trials** (§3.5). Qwen3-4B card τ numbers
  lack all three and cannot be ranked against APIGen-MT's pass@1 ≥ 5-trial numbers.
- **Repo code licence ≠ checkpoint licence.** The Hammer repo is Apache-2.0 (S7); that says
  nothing about any Hammer checkpoint's licence.
