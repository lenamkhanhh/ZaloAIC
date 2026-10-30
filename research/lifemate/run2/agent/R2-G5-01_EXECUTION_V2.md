# R2-G5 — Agent/History execution path + real-B0 P1 V2 instantiation
Role: Lead, Group 5 Agent and History, RUN 2. Parent: coordinator main chat.
Freeze: 13:41 Asia/Saigon 2026-10-30. LifeMate only. Source pin: ff7a288e668f37e96c03bf9318d974e3a8e6d2a4.
Scope separation (read first): this task is NOT the R2-G5 review task
described in MEMORY (review of G3 round 4 + G4 rerun, parent lead Nhom 1,
deliverable R2-G5-01_REVIEW.md). That review task is PAUSED per L5
reassignment and belongs to chat C3-G5 Proof Review; it is NOT started
here, no review on an unordered commit is made here, and no code edit
is made to lifemate_callback_negation.py or any G&G module here.
This task is execution-path checking + V2 prompt instantiation, owned
files only: agent/prompt/control flow (lifemate/agent.py,
lifemate/config.py, lifemate/tests/test_r2g5_agent_execution.py, this file).
No simulator/scorer/split edit, no merge main, no force-push, no GPU,
no model run. Model compliance is NOT_RUN.

## Before (B0 at ff7a288e, verified from code, not from memory)
- Prompt: lifemate/agent.py build_base_prompt — flat history, no turn
  index, no status, assistant calls only (no tool_results), current
  transcript last. Tool list = sample-filtered catalog, sorted.
- Observation: render_observation_prompt after EVERY executed call,
  ALL executed + results, output repr truncated to 300 chars, outcome
  only ok vs error (ok:true, done:false reads as "ok").
- Validation: env.validate before every call, not logged, no state
  change. Attempts: for _attempt in range(3) (1 generation + up to 2
  retries); invalid JSON re-prompts with base + error (no observation);
  validation fail re-prompts with observation and call=None; after 3
  attempts the trace returns as-is.
- Guard: LoopGuard max_repeats=2, exact-JSON key, record() receives
  state_progress but does not use it; caller passes
  state_progress=bool(result.get("ok")). Pre-block, then replan_once,
  then stop.
- Termination: generator None / {"stop": true}, max_steps=12, guard
  stop, validation exhaustion, or caller completion (infer passes
  None, so no completion predicate in the real infer path).
- Ask: sys.ask_missing_info is executed via env.call, logged, touches
  no state, and the loop CONTINUES to the next generation — ask is
  NOT terminal in B0.
- Multi-call in one response: generator protocol returns ONE dict or
  None. A list / multi-call object is not a dict with "name", so it
  goes down the invalid-JSON path, is re-prompted, and is NOT split
  and NOT executed.
- Prompt budget: PipelineConfig llm_max_context_tokens=16384 is
  checked only for params/context limits in check_budget(). No code
  in agent.py/run.py measures a rendered prompt, and no output
  reserve is accounted for in the loop. selective_reads /
  verification_read_after_write are config-only (not used in any .py).
- P1 V2 builder check (previous run): builder PASS on 18 cases /
  19 prompt blocks, but B0/tool lines in the archive used placeholders
  — that check proved builder shape, not a real instantiated prompt.

## After (this branch, variant OFF by default)
Branch (local only, see Push note): muse/chat3/agent-r2g5-v2-instantiation
Base: ff7a288e668f37e96c03bf9318d974e3a8e6d2a4
Files changed:
- lifemate/agent.py: + build_v2_prompt(), + _history_result_status(),
  + measure_prompt_budget(), and AgentLoop.run() chooses V2 base only
  when config.history_presentation_v2 is True, otherwise B0 exactly.
  No change to B0 prompt, observation, guard, validation, or G&G hooks
  when the flag is False (covered by test_v2_default_off_preserves_b0).
- lifemate/config.py: + history_presentation_v2: bool = False,
  + prompt_output_reserve_tokens: int = 1024 (measurement only).
  Old configs still load (dataclass defaults); check_budget unchanged.
- lifemate/tests/test_r2g5_agent_execution.py: new, 12 tests, fake
  generator + StubEnv simulator stub only.
- This file.

V2 builder, real instantiation (not the placeholder archive):
- build_v2_prompt() uses the SAME B0 context lines (current time,
  timezone, user name/city) and the SAME tool-list format, filled
  from a real Sample object and a real tools dict — no "<from
  context>" / "<timezone>" / "..." placeholders in the produced prompt.
- Past block: turn indices, order preserved, user audio_text or
  "[audio, no transcript available]", assistant calls + result=
  (ok only for a parsed list all ok:true, otherwise "not shown",
  never rendered output content).
- Open block: rendered ONLY from an explicit caller-supplied list;
  in all 18 synthetic cases that list is empty -> "Open requests: none."
  The builder never fills it from an imperative verb or proximity.
- No V1 slot, no V3 tag, no history tool output content in the prompt.
- measure_prompt_budget() is measurement only: estimated_tokens =
  ceil(chars/4), labelled ESTIMATE (not a tokenizer count),
  available = max_context - output_reserve (16384 - 1024 = 15360 by
  default). It never truncates or rewrites a prompt. Real tokenizer /
  rendered-template accounting is NOT_RUN until a tokenizer runtime
  check (Codex).

## Commands and results (CPU only, fake generator, stub env)
In the isolated copy ~/workspace/chat3/r2-g5-work/ZaloAIC, branch
muse/chat3/agent-r2g5-v2-instantiation:
- python3 -m unittest lifemate.tests.test_r2g5_agent_execution -v
  -> Ran 12 tests, OK (0 failures, 0 errors).
  Covers: observation step order (observation section scoped, not the
  tool list — an early test assertion that checked the whole prompt
  for "phone.call" was wrong and was fixed in the test, not in the
  loop code); history order + no future info (label sentinel absent
  from B0 and V2 prompts); ask then stop / stop dict; multi-call list
  rejected not split, and valid call on retry runs; validation retry
  then success; validation exhaustion preserves prior calls;
  max_steps=3 caps execution at 3; guard exact repeat executes at
  most 2 then stops after replan; prompt budget with reserve
  (4000 chars -> 1000 est. tokens, available 15360, remaining 14360,
  over=False; over-budget case over=True); V2 OFF preserves B0;
  V2 real-B0 all 18 cases pass B1-B4; open block only from explicit
  caller state.
- python3 -m unittest lifemate.tests.test_lifemate
  -> Ran 17 tests, OK (skipped=7). Skipped tests are data-dependent
  (dataset not extracted); skipped is NOT counted as pass.
- Before/after for the two test bugs found during this run (test bugs,
  not loop bugs): (1) StubEnv.validate crashed on a list argument
  (params list unhashable in a set check) — fixed in the test to a
  string-equality check; (2) observation test scoped its no-future
  assertion to the whole prompt, which legitimately contains the tool
  list — fixed in the test to scope to the observation section.
  No loop code was changed to make a test pass.

## Execution-path findings (B0, for coordinator / Group 4 file lock)
1. Observation is step-correct: each next prompt contains all prior
   executed calls/results in order, and its observation section
   contains no future call. The tool list in the same prompt does
   name future tools — that is catalog, not execution, and must not
   be misread as future-info leakage.
2. History order is preserved by construction (iteration order), and
   the loop never reads sample.label — a label sentinel does not
   appear in either prompt. Future-info leakage, if any, would have
   to come from data preparation (history containing a later turn),
   not from AgentLoop.run().
3. Ask is not terminal in B0; stop/None are terminal; a multi-call
   response is rejected, not split. Any "ask as terminal" or
   "split multi-call" behaviour must be a separate, flagged variant
   (cf. L4 T1 / multi-call), not a silent change here.
4. Prompt budget is not enforced in B0. This variant only measures
   it, with a chars/4 estimate. Do not report the estimate as a
   tokenizer count, and do not claim a prompt is within budget until
   a real tokenizer check is run.
5. Group 4 file lock: no dedicated Group 4 lock chat was found in
   chat.list for Run 2 in this turn, and no lock was obtained via a
   live message. To avoid collision, all work was done in an isolated
   copy (r2-g5-work) on a separate branch, not in a shared checkout,
   and no push was attempted. Coordinator/Group 4 must confirm the
   lock before any merge/integration of agent.py/config.py.

## Push note (do not substitute)
Branch is LOCAL ONLY in this VM copy. Push was NOT attempted in this
run, following the known VM push block recorded for G3 (HTTPS no
credential helper, gh not logged in, SSH egress blocked, MCP snapshot
push would create a different SHA/history). Do NOT substitute a
snapshot/MCP commit for this branch's commit. Coordinator must supply
a push route if the branch is to be reviewed remotely; the local
commit SHA is in the report to coordinator, not in this file, because
this file is committed before the final SHA is known — coordinator
should read the SHA from the report / git log, not from here.

## Open errors / residuals (not hidden)
- Catalog values: tool description/required strings in the new tests
  are fixtures for prompt-structure checking, NOT verified against
  the extracted <split>_tools_catalog.json (dataset not extracted).
  Real-B0 here means real Sample/context/history/transcript/tool
  names/kinds/open-block handling, not verified real catalog text.
  A real-sample instantiation check is still required before V2
  implementation is considered done — this is the same residual as
  the G4 builder check, narrowed but not closed.
- History tool_results shape: the "parsed list all ok:true -> ok,
  otherwise not shown" rule is conservative and test-defined. Real
  train history tool_results shapes (list vs repr-string vs other)
  must be audited against real data before this rule is treated as
  production-correct.
- Model compliance: NOT_RUN. Nothing here proves a model follows V2,
  asks instead of picking, or stops correctly. Fake-generator passes
  are mechanics only.
- V3: NOT_APPROVED, not built, not in this branch.
- R2-G5 review task: PAUSED, owned by C3-G5 Proof Review, NOT done
  here. Do not confuse this execution report with that review.
- Freeze: if coordinator does not confirm the Group 4 lock / push
  route by 13:41 Asia/Saigon 2026-10-30, freeze this branch as-is
  (local commit, report sent) and do not loop or push by another route.
