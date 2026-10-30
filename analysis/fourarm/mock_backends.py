"""MOCK backends for smoke ONLY -- never a model, never a score.

MockASR returns a FIXED transcript per (asr_kind, wav_sha). MockLLM
returns a FIXED tool-JSON sequence per (llm_kind, sample_id). The
mock loop simulator applies the same mechanical rules the smoke is
meant to exercise -- tool-name validation against a mock catalog,
execution in order, stop / max_steps termination -- but it is NOT
AgentLoop, NOT zaic_tools, and its outputs are NEVER reported as
model results. Every mock artifact is labelled "MOCK ONLY" in its
own fields (mode="mock") and in every report that touches it.

Smoke design (4 samples x 4 arms = 16 traces):
  mock_001: empty case. Own and partner LLM both stop at once.
    Transcript differs by ASR kind only in wording, not in digits.
  mock_002: digit-slot case. Own ASR transcript keeps gold digit
    "0901234567"; partner ASR transcript says "0901234568".
    Both LLMs emit a contacts.search with the transcript digit.
    -> slot_heard_wrong fires for B/D only, in the mock score phase.
  mock_003: wrong-tool case. Own LLM emits contacts.search;
    partner LLM emits contacts.update (wrong tool, wrong args).
    -> wrong_tool fires for C/D only, in the mock score phase.
  mock_004: early-stop case. Own LLM emits contacts.search then
    stop; partner LLM emits contacts.search, contacts.search again
    (duplicate = extra call) then stop.
    -> extra_call fires for C/D, and the mock score fixture gives
    mock_004 two gold calls so own LLM is also incomplete.

The mock score fixture (written by mock-smoke into the OUT dir,
never into the repo) supplies, per mock sample: gold tool calls,
label class, and gold current transcript. It is a synthetic fixture
for plumbing, not real gold, and score_fourarm.py labels any report
built from it MOCK ONLY.
"""
from __future__ import annotations

import hashlib

MOCK_SAMPLES = ["mock_001", "mock_002", "mock_003", "mock_004"]

# wav_sha values are fixed synthetic strings, not real file hashes.
MOCK_WAV_SHA = {
    "mock_001": "mockwav001",
    "mock_002": "mockwav002",
    "mock_003": "mockwav003",
    "mock_004": "mockwav004",
}

MOCK_TRANSCRIPTS = {
    # (asr_kind, sample_id) -> transcript
    ("own", "mock_001"): "xin chao",
    ("partner", "mock_001"): "xin chao a",
    ("own", "mock_002"): "goi cho Lan so 0901234567",
    ("partner", "mock_002"): "goi cho Lan so 0901234568",
    ("own", "mock_003"): "tim Lan",
    ("partner", "mock_003"): "tim Lan",
    ("own", "mock_004"): "tim Lan roi cap nhat",
    ("partner", "mock_004"): "tim Lan roi cap nhat",
}

# LLM sequences: list of dicts, or None for stop. Own vs partner.
MOCK_LLM_SEQUENCE = {
    ("own", "mock_001"): [None],
    ("partner", "mock_001"): [None],
    ("own", "mock_002"): [
        {"name": "contacts.search", "arguments": {"phone": "0901234567"}},
        None],
    ("partner", "mock_002"): [
        {"name": "contacts.search", "arguments": {"phone": "0901234567"}},
        None],
    ("own", "mock_003"): [
        {"name": "contacts.search", "arguments": {"query": "Lan"}},
        None],
    ("partner", "mock_003"): [
        {"name": "contacts.update", "arguments": {"contact_id": "c999", "amount": 1}},
        None],
    ("own", "mock_004"): [
        {"name": "contacts.search", "arguments": {"query": "Lan"}},
        None],
    ("partner", "mock_004"): [
        {"name": "contacts.search", "arguments": {"query": "Lan"}},
        {"name": "contacts.search", "arguments": {"query": "Lan"}},
        None],
}

MOCK_CATALOG = {"contacts.search", "contacts.update",
                "sys.ask_missing_info"}

MOCK_GOLD = {
    "mock_001": {"label_class": "empty", "gold_calls": [],
                 "gold_transcript": "xin chao"},
    "mock_002": {"label_class": "normal",
                 "gold_calls": [{"name": "contacts.search",
                                 "arguments": {"phone": "0901234567"}}],
                 "gold_transcript": "goi cho Lan so 0901234567"},
    "mock_003": {"label_class": "normal",
                 "gold_calls": [{"name": "contacts.search",
                                 "arguments": {"query": "Lan"}}],
                 "gold_transcript": "tim Lan"},
    "mock_004": {"label_class": "normal",
                 "gold_calls": [{"name": "contacts.search",
                                 "arguments": {"query": "Lan"}},
                                {"name": "contacts.update",
                                 "arguments": {"contact_id": "c001"}}],
                 "gold_transcript": "tim Lan roi cap nhat"},
}

# Partner LLM emits the transcript digit for mock_002, not the gold
# digit, in the real mock run: the sequence above for partner
# mock_002 is replaced at run time by the ASR-digit sequence, so the
# slot error actually propagates through the mock LLM input. This is
# done in mock_run_sample, not hidden in the table.
MOCK_LLM_USES_TRANSCRIPT_DIGIT = {"mock_002"}


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class MockASR:
    def __init__(self, kind):
        assert kind in ("own", "partner")
        self.kind = kind

    def transcribe(self, sample_id):
        return MOCK_TRANSCRIPTS[(self.kind, sample_id)]


class MockLLM:
    def __init__(self, kind):
        assert kind in ("own", "partner")
        self.kind = kind
        self._pos = {}

    def generate(self, sample_id, transcript):
        pos = self._pos.get(sample_id, 0)
        self._pos[sample_id] = pos + 1
        seq = MOCK_LLM_SEQUENCE[(self.kind, sample_id)]
        if pos >= len(seq):
            return None
        call = seq[pos]
        if call is None:
            return None
        # Digit propagation for mock_002: the emitted phone is the
        # phone heard in THIS arm's transcript, not the gold digit.
        if sample_id in MOCK_LLM_USES_TRANSCRIPT_DIGIT:
            import re
            digits = re.findall(r"[0-9]+", transcript or "")
            if digits and call["name"] == "contacts.search":
                call = {"name": call["name"],
                        "arguments": {"phone": digits[0]}}
        return call


def mock_run_sample(sample_id, arm, asr_kind, llm_kind, shadow_observer):
    """Simulate one sample-run. Returns a trace in the fixed schema.
    shadow_observer is recorded in the trace but NEVER changes
    execution -- that is the property check-off-on tests. Seconds are
    synthetic (0.01 per generation) and are labelled mock; the
    late_time flag in a mock report is plumbing only."""
    asr = MockASR(asr_kind)
    llm = MockLLM(llm_kind)
    transcript = asr.transcribe(sample_id)
    generations = []
    executed = []
    step = 0
    termination = "max_steps"
    while step < 12:
        step += 1
        call = llm.generate(sample_id, transcript)
        if call is None:
            termination = "stop"
            generations.append({
                "prompt_sha256": sha256_text(f"mock-prompt-{sample_id}-{step}"),
                "raw_output": '{"stop": true}',
                "raw_output_reason": None,
                "raw_output_token_count": 4,
                "prompt_token_count": 20,
                "token_count_reason": None,
                "parsed_call": None,
                "error": None,
                "seconds": 0.01,
                "observation_following": None,
                "observation_kind": None,
            })
            break
        # Mock validation: name must be in the mock catalog.
        valid = call["name"] in MOCK_CATALOG
        if not valid:
            generations.append({
                "prompt_sha256": sha256_text(f"mock-prompt-{sample_id}-{step}"),
                "raw_output": None,
                "raw_output_reason": "mock: invalid tool name, not executed",
                "raw_output_token_count": None,
                "prompt_token_count": 20,
                "token_count_reason": None,
                "parsed_call": call,
                "error": "validation_failed_not_executed",
                "seconds": 0.01,
                "observation_following": "validation failed (NOT executed, NOT submitted)",
                "observation_kind": "validation_failure_observation",
            })
            continue
        executed.append(call)
        obs = f"ok: {call['name']} executed (mock)"
        generations.append({
            "prompt_sha256": sha256_text(f"mock-prompt-{sample_id}-{step}"),
            "raw_output": None,
            "raw_output_reason": "mock: raw output not captured; parsed call only",
            "raw_output_token_count": None,
            "prompt_token_count": 20,
            "token_count_reason": None,
            "parsed_call": call,
            "error": None,
            "seconds": 0.01,
            "observation_following": obs,
            "observation_kind": "observation",
        })
    else:
        termination = "max_steps"
    if generations and generations[-1]["observation_kind"] == "observation":
        generations[-1]["observation_following"] = None
        generations[-1]["observation_kind"] = None
    trace = {
        "sample_id": sample_id,
        "split": "dev",
        "arm": arm,
        "mode": "mock",
        "asr": {"kind": asr_kind, "mock": True},
        "llm": {"kind": llm_kind, "mock": True},
        "shared": {"seed": 42, "max_steps": 12, "mock": True},
        "transcript_current": transcript,
        "transcript_source": "mock_asr",
        "wav_path": None,
        "wav_sha256": MOCK_WAV_SHA[sample_id],
        "prompt_sha256": sha256_text(f"mock-base-{sample_id}"),
        "generations": generations,
        "grounding_log": [],
        "observer_log": [{"shadow_observer": shadow_observer,
                          "note": "mock: observer recorded only, never blocks"}],
        "tool_calls": executed,
        "state_hash": sha256_text(str(executed)),
        "termination": {"kind": termination,
                        "n_generations": len(generations)},
        "seconds": round(0.01 * len(generations), 4),
        "run_error": None,
    }
    return trace
