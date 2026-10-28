# E7 Phase 0 shadow audit — CPU_NOT_READY

**Result: do not integrate this guard or launch E7 GPU.** A lightweight three-valued prototype catches5/6 registered fill cases but cannot positively resolve most legitimate gold sources. This is an implementation/coverage finding, not a refutation of provenance guards or a model capability ceiling. No inference module, parser, seed/config, simulator, scorer or split changed; no model/GPU run and no held-out assessment.

## Final v3 evidence

| Screen | Result |
|---|---|
| V13 coverage | All40 traces;29 proposed writes including rejected proposals |
| Proposed-write scope | 17 writes/19 arguments monitored;12 writes have no present monitored argument |
| V13 decisions with actual ASR | 8 BLOCK,9 UNKNOWN,0 ALLOW among17 scoped proposals |
| Fixed known fills | 5 BLOCK,1 UNKNOWN;not6/6 BLOCK |
| Dev gold coverage | 1,237 dev samples;1,389 writes;459 monitored writes/511 arguments |
| Monitored gold decisions | **31 ALLOW,428 UNKNOWN,0 BLOCK** |
| Positive gold coverage | **31/459 = 6.75%**;UNKNOWN is not a passed gold write |
| Other gold writes | 930 outside this guard's present-argument scope |
| Synthetic tests | 33/33;guard-module coverage87% |
| ASR/gold paired checks | 19 V13 argument occurrences:8 BLOCK->BLOCK,11 UNKNOWN->UNKNOWN |
| Gold-write ASR cache | Unavailable for all1,389 writes in the remaining dev;not silently replaced by gold |
| Key=value reporting | 2 true positives,17 ordinary prose negatives,0 false positives;parser unchanged |

The20 E5 samples all have gold ask-only traces, so the positive-write screen necessarily uses the rest of dev. The rows outside scope are not evidence that a guard understands or allows their sources. Date/time lists, quantities, thresholds, amounts and due/start/end variants were discovered from catalog metadata/property names;not a list of probe IDs.

## Known-fill manifest and unresolved case

The six frozen diagnostic identities are five trial first time proposals (0219,0220,0287,0360,0780) plus0353-control's history-matching time. Each manifest entry pins arm,generation,tool,proposed arguments and both ASR/gold-text decisions. These IDs never enter guard.assess.

0219/0220/0287/0360 trial and0353 control are BLOCK under supported absence-of-request-hour checks.0780 remains UNKNOWN: the gold request references latest instructions and the noisy ASR also contains an indirect reference. The prototype cannot prove field-level supersession or resolve the intended instruction. It does **not** erase all history simply because 'latest' appears. This is the required-fill gate failure, not a case silently treated as blocked.

WATCH0823's calendar start/end are UNKNOWN in both arms because its compound request is not slot-bound by this implementation. It is not counted as a successfully blocked fill. Subsequent proposed calendar mutations with no monitored arguments remain outside scope. All29 write proposals are recorded, so neither missing required time nor out-of-scope changes disappear from the audit.

## What the implementation actually supports

The module is pure and shadow-only. It accepts call/catalog/current request/visible context/past successful observations/history, never sample labels,IDs,hidden state or future results. It recognizes a limited set of Vietnamese numeric/time/date expressions,explicit now/offsets,one pointed-event shift,unit conversions,bill-type/name pointing,and half of a uniquely observed base. An observed ID or matching number alone is insufficient evidence of current intent.

ALLOW requires implemented positive source binding. BLOCK is emitted only by a supported conflict/absence check. Unsupported clause/slot binding,implicit refer-back,field supersession,arithmetic/ranges,date inheritance and multi-valued times abstain as UNKNOWN. Atomic write status aggregates argument decisions;missing required fields remain the simulator validator's responsibility. Reads/asks and undeclared/unknown tools remain outside this provenance layer.

This limited lexical matcher is **not** a general semantic resolver. Matching text and call IDs are still heuristic evidence,not proof of intent. Counterfactual later calls after a hypothetical block are not simulated:the shadow compares the fixed V13 prefixes and cannot measure recovery,block->ask,termination changes or end-to-end success.

## Development history — all versions retained

| Version | Synthetic tests | Gold ALLOW | Gold UNKNOWN | Gold BLOCK | Known fills BLOCK/UNKNOWN |
|---|---:|---:|---:|---:|---:|
| v1 | 23 | 46 | 373 | 40 | 5/1 |
| v2 | 32 | 29 | 429 | 1 | 5/1 |
| v3 | 33 | 31 | 428 | 0 | 5/1 |

V1's40 gold BLOCKs were candidate false-blocks;none had a failed gold tool result. Examples of implementation causes:partial amount parsing,unbound event-end duration,period-before-hour syntax,compound numeric slots and refer-back dates. Some require deeper semantics rather than more date arithmetic. V2 mostly converted unsupported decisions to UNKNOWN;the falling BLOCK count is **not** a rise in coverage. V3 fixes a separate lexical bug where an ordinary word was tokenized as a number plus h.

The independent G5 reviewer derived expectations before reading code and found four synthetic failures:relative event shift containing 'nữa' incorrectly anchored to now,numeric values borrowed from other slots/tasks,a dropped weekday modifier,and substring ID matching. They were regression-tested and fixed;the follow-up reproduced their resolution on final guard hash02562c37bf8c98dd5dddb1b06f6706208513cdacade9bdbb2309c26072102295. This closes those findings only. It is not certification of every possible ALLOW/BLOCK. The review and concrete examples are in analysis/e7_shadow/REVIEW.md.

Regressions motivated by dev are explicitly development evidence,not independent validation. No held-out was opened for this audit. No gold labels or sample IDs were added to the guard to force a passing gate. The small number of recognized positive examples and the many UNKNOWNs preclude the claim 'zero over-rejection'.

## Gate interpretation and brief corrections

G1:guard/spec contain generic rules and synthetic examples,no contest IDs/values;diagnostic runner manifest keeps the fixed sample identities separate. G2:FAIL — one known fill unresolved and428 monitored gold writes not positively allowed. G3:33 synthetic tests and bounded review findings pass;there is no live loop integration to claim attempt-count behavior has been tested. G4:runtime lifemate tree is byte-unchanged from a472006;initial prompt/parser/cache/config frozen;future feedback would necessarily change later prompts. G5:independent counterexamples closed,but broad semantic completeness remains unproven.

The Phase0 label is **CPU_NOT_READY**, not E7 REFUTED:the proposed model block->ask hypothesis has not been run. There is no simulator execution in the shadow runner;gold observation prefixes use label results only after the corresponding gold step. Actual V13 prefixes use only preceding observed tool events. Replacing ASR text by gold text is a diagnostic intervention on those fixed prefixes,not a claim the model would have reached the same trace with gold input.

The reporting gate uses17 prose negatives and2 key=value positives from the19 V13 plain stops. It does not widen the real parser or convert text to calls. Registered E5 scores/verdict are unchanged.

## Practical next decision

Do not spend GPU to evaluate this broad partial implementation. Do not write a larger exception list just to turn428 UNKNOWNs into ALLOW. Two honest follow-ups are available for a separately frozen design:

1. Narrow the intervention to a small,explicitly recognizable source/slot family with a stated abstention policy and measure that coverage separately;do not keep calling it a universal time/amount guard.
2. If broad coverage is required,first specify/test a structured task/slot/reference representation (including supersession and valid arithmetic). That is a semantic component with its own error/cost evaluation,not a free deterministic consequence of JSON schema validation.

The audit does not select a new live policy for UNKNOWN and does not demonstrate recovery. It does not justify training,RPO,RL,ASR changes or automatic28-sample expansion. Muse can use the summary and UNKNOWN breakdown to propose one narrower next experiment,rather than treating the shadow's0 BLOCK as success.

## Source, artifacts and commands

Analysis-only source:experiment branch commit f2727921476775d9aecb197c443d994dc61e646a. Guard SHA25602562c37bf8c98dd5dddb1b06f6706208513cdacade9bdbb2309c26072102295. V13 ZIP SHA256f1cd3df132622660765d03412a9defa84a225fc9e80c44994acbf5daa7d6ac71;split hash unchanged eefd0faa163285b23d2634bc4cc04f515b58367a2344599e46e85d48818280aa. Original inference base remains a472006.

Commands executed, from the repository:scoped git status/diff/fetch/show;Python loader/catalog inventory on dev;unittest analysis.e7_shadow.test_guard (RED then GREEN);coverage run/report on guard;run_shadow.py with separate v1/v2/v3 output directories;19-stop reporting verification;git diff --exit-code a472006 -- lifemate;analysis-only commits/push. Tests33/33 and guard coverage87%;all models_run/gpu_jobs/heldout_assessed counters0. The source README gives exact reproducible commands and explicit path overrides.

Touched source files:analysis/e7_shadow/{guard.py,test_guard.py,run_shadow.py,reporting.py,SPEC.md,README.md,REVIEW.md}. Generated local outputs:artifacts/lifemate-e7-shadow/{v1,v2,v3};publish staging separate. No raw labels,full gold call sequences,transcripts,state,audio or weights are published. Public derived V13 decisions contain model proposals and diagnostic classifications only,never agent input.
