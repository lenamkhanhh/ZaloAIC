# Audited model traces for Muse

Read V7_AUDIT_2026-10-28.md first, then v7_diagnostic_trace.json and V6_AUDIT_2026-10-28.md.
These are diagnostic artifacts, never agent inputs or training examples.

## Exact code and experiment identities

- Main contains these reports and Muse research. Main inference code differs
  from the executed agent: do not review it as if it produced these traces.
- V6 executed core a9d48d24021cb91efef7d50cbc3d18ad98ed5b89: five fixed dev IDs,
  cached-ASR current vs gold-current arms, identical cached ASR history.
- V7 executed core a2e832b9bdbef63d6d7b5d1573a8d303a48f2664 on
  codex/lifemate-baseline-integration: eight dev IDs, live current/history ASR.
- Agent change documentation: lifemate/AGENT_FIX_2026-10-28.md on the Codex branch.
- ASR: vinai/PhoWhisper-small revision a86b604c346caf7148c37512eafe783a16420adb.
- LLM: Qwen/Qwen3-4B-Instruct-2507 revision cdbee75f17c01a7cc42f958dc650907174af0554.
- Greedy/seed42; Transformers4.57.6; same FP16/T4x2 placement and efficient
  attention in both runs. This is not official A30 runtime evidence.

## Verified comparison

V6: 10/10 independent replay/hash and proxy checks; V7:8/8. ZIP CRCs pass.
On the five common IDs, V7 current/history ASR texts exactly match V6 cached
inputs. Common-five proxy mean is0.2 ->0.2, so no score improvement demonstrated.
V7's eight-example mean0.125 is a different denominator, not evidence of a
regression from0.2. V7 hash agreement3/8 does not establish correct intent:
0116asks the wrong question;0004reaches the correct device state but its trace
differs from gold. Scorer is ENGINEERING_PROXY_NOT_OFFICIAL.

## Highest-priority research questions

1. V7 0003 repeatedly emits ask parameters at the JSON top level;0116 asks
   phone.call/contact_id instead of reminders.create/time. Inspect the exact
   executed prompt/schema/output parser contract. Research the official
   Qwen model's native chat/tool-calling integration and propose a minimal
   controlled comparison. Distinguish format repair from wrong intent.
2. V7 0008 writes before checking weather despite policy;0004 repeats an
   already successful write. Explain where a plan/decision representation,
   tool-message structure, or execution policy could help, with primary-source
   evidence. Preserve legitimate repeated reward actions; no blanket dedup.
3. ASR corrupts0025/0016/0049 heavily. Define a separate small-vs-medium ASR
   experiment measuring intent/condition/negation/name/money/time, alongside
   downstream effects. V6 gold-current did not solve the original four action
   cases, so do not present an ASR upgrade alone as sufficient.
4.0004is a scoring/semantic-equivalence caveat: filtered read, extra optional
   power arg and duplicate write get strict proxy0 despite correct hash.
   Keep unresolved official read/optional-argument semantics explicit.

Deliver a ranked failure ledger (ASR/format/intent/prerequisite/termination/
proxy mismatch), concrete source-backed remedies, and one minimal next
experiment per competing hypothesis. Avoid broad model lists or an unsupported
SOTA claim. Do not change inference code, hardcode probe answers, run models,
or use heldout. Keep artifact analysis and research claims distinct.

The trace JSON contains model-generated ASR, raw generated output, executed
calls and observed tool feedback, with full prompts/gold labels excluded.
Use the local verified train release to inspect references, by sample ID.
