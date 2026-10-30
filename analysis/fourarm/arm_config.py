"""Four-arm configuration contract for Phase 3 (LifeMate only).

This module is the ONLY place that defines what an "arm" is. It does
not load weights, does not read data, and does not read gold calls.

Arm contract (Phase 2 supplies the partner pins; this file must be
the shape Phase 2 fills in, not a guess at its values):

    arm = {
      "arm": "A" | "B" | "C" | "D",
      "asr": {"backend": str, "checkpoint": str, "revision": str,
              "decode": {"beam_size": int, "language": str, "greedy": bool}},
      "llm": {"base": str, "adapter": str | null, "merged": str | null,
              "revision": str | null, "tokenizer": str, "template": str,
              "stop": [str], "context": int,
              "decoding": {"temperature": float, "seed": int, "max_tokens": int},
              "backend": str},
    ("revision" is the HF revision of the checkpoint actually loaded:
    for the own LLM it is cdbee75; for a partner merged checkpoint
    Phase 2 must pin it -- a merged checkpoint without a revision
    is refused in real mode, never guessed.)
      "shared": { ... frozen for all four arms ... },
    }

Arm meanings (exactly one named component changes per arm step):
    A = own ASR + own LLM
    B = partner ASR + own LLM      (only asr differs from A)
    C = own ASR + partner LLM      (only llm differs from A)
    D = partner ASR + partner LLM  (both differ from A)

Shared block (identical in all four arms, enforced by validate_arms):
    sample order = the frozen manifest order; runtime = lifemate/agent.py
    AgentLoop via lifemate/run.py's infer path (real mode) -- the
    harness never reimplements the loop; prompt policy = the loop's
    base prompt (build_base_prompt, history V2 OFF) with the tool
    catalog filtered by installed_apps for the sample
    (catalog_tools_for_sample); seed 42; decoding temperature 0;
    max_steps 12; max_repeats 2; grounding True (recommended.json);
    shadow_observer True for main runs (record only, never block);
    pending_ask_stop False; selective_reads True;
    verification_read_after_write False.
    ASR applies to EVERY user audio turn (history + current), never
    to a gold transcript: a gold transcript is never agent input in
    this harness. The Tier 1a history-fixed design is NOT reused
    here, deliberately: four-arm measures the full ASR arm, and on
    public_test there is no transcript to fall back to anyway.

Partner pins are currently UNPINNED (null). That is a real-run
BLOCKER, not a default: validate_arms(real_mode=True) refuses any
arm whose partner slot is null, and the real runner refuses an LLM
with adapter set but merged null, because lifemate/llm.py has no
adapter-merge step -- Phase 2 must supply a merged checkpoint (or a
merge command the coordinator approves) before a real C/D run.

Own pins (from lifemate/configs/recommended.json, verified by
preflight SHA 71d5f38f...):
    ASR: vinai/PhoWhisper-small, faster-whisper, greedy beam 1,
         language vi, revision "" (recommended.json records no ASR
         revision; the checkpoint string is the pin, as in Tier 1a).
    LLM: Qwen/Qwen3-4B-Instruct-2507, revision cdbee75, vLLM
         (transformers fallback), model's own chat template,
         stop = template stop token + {"stop": true}, context 16384,
         temperature 0.0, seed 42, max_tokens 512.
"""
from __future__ import annotations

import json
from pathlib import Path

ARMS = ("A", "B", "C", "D")

OWN_ASR = {
    "backend": "faster-whisper",
    "checkpoint": "vinai/PhoWhisper-small",
    "revision": "",
    "decode": {"beam_size": 1, "language": "vi", "greedy": True},
}

OWN_LLM = {
    "base": "Qwen/Qwen3-4B-Instruct-2507",
    "adapter": None,
    "merged": None,
    "revision": "cdbee75",
    "tokenizer": "Qwen/Qwen3-4B-Instruct-2507",
    "template": "model_chat_template",
    "stop": ["template_stop_token", '{"stop": true}'],
    "context": 16384,
    "decoding": {"temperature": 0.0, "seed": 42, "max_tokens": 512},
    "backend": "vllm",
}

# Partner slots: deliberately null until Phase 2 pins them. Do NOT
# fill these in with a guessed checkpoint.
PARTNER_ASR_UNPINNED = {
    "backend": None,
    "checkpoint": None,
    "revision": None,
    "decode": {"beam_size": None, "language": "vi", "greedy": None},
}

PARTNER_LLM_UNPINNED = {
    "base": None,
    "adapter": None,
    "merged": None,
    "revision": None,
    "tokenizer": None,
    "template": None,
    "stop": None,
    "context": None,
    "decoding": None,
    "backend": None,
}

SHARED = {
    "runtime": "lifemate.agent.AgentLoop",
    "prompt_policy": "build_base_prompt, history_presentation_v2=False, "
        "catalog filtered by installed_apps",
    "tool_catalog": "catalog_tools_for_sample per sample",
    "seed": 42,
    "decoding_temperature": 0.0,
    "max_steps": 12,
    "max_repeats": 2,
    "grounding": True,
    "shadow_observer": True,
    "pending_ask_stop": False,
    "history_presentation_v2": False,
    "selective_reads": True,
    "verification_read_after_write": False,
    "scorer": "lifemate.scoring.score_sample (official-style, NOT organiser evaluator)",
    "asr_scope": "all user audio turns (history + current); gold transcript never input",
}


def build_arms(partner_asr=None, partner_llm=None):
    """Return the four arm dicts. Partner defaults are the unpinned
    placeholders; a caller that wants a real run must pass real pins
    and then pass validate_arms(real_mode=True)."""
    pasr = partner_asr if partner_asr is not None else PARTNER_ASR_UNPINNED
    pllm = partner_llm if partner_llm is not None else PARTNER_LLM_UNPINNED
    return {
        "A": {"arm": "A", "asr": OWN_ASR, "llm": OWN_LLM, "shared": SHARED},
        "B": {"arm": "B", "asr": pasr, "llm": OWN_LLM, "shared": SHARED},
        "C": {"arm": "C", "asr": OWN_ASR, "llm": pllm, "shared": SHARED},
        "D": {"arm": "D", "asr": pasr, "llm": pllm, "shared": SHARED},
    }


def _is_pinned(component):
    """True only if every non-optional field is present. Unused by
    validate_arms (which reports per-field errors); kept as the
    single definition of 'pinned' for callers that need a boolean."""
    if not isinstance(component, dict):
        return False
    return all(v is not None for k, v in component.items()
               if k not in ("adapter", "merged"))


def validate_arms(arms, real_mode=False):
    """Enforce: exactly A/B/C/D; shared block identical across arms;
    B differs from A only in asr; C differs from A only in llm;
    D differs from A in asr+llm and equals B's asr + C's llm.
    In real_mode, also require every pin present and every LLM to be
    runnable through lifemate/llm.py (merged checkpoint, or base with
    adapter null; adapter-without-merged is refused, not silently
    downgraded). Returns a list of error strings (empty = valid)."""
    errors = []
    if set(arms) != set(ARMS):
        errors.append(f"arms must be exactly {ARMS}, got {sorted(arms)}")
        return errors
    shared = [json.dumps(arms[a]["shared"], sort_keys=True) for a in ARMS]
    if len(set(shared)) != 1:
        errors.append("shared block differs between arms; all arms must share it")
    a, b, c, d = arms["A"], arms["B"], arms["C"], arms["D"]
    if b["llm"] != a["llm"]:
        errors.append("arm B must share arm A's llm exactly")
    if c["asr"] != a["asr"]:
        errors.append("arm C must share arm A's asr exactly")
    if d["asr"] != b["asr"] or d["llm"] != c["llm"]:
        errors.append("arm D must equal B's asr and C's llm")
    if b["asr"] == a["asr"]:
        errors.append("arm B asr must differ from arm A asr")
    if c["llm"] == a["llm"]:
        errors.append("arm C llm must differ from arm A llm")
    if not real_mode:
        return errors
    for name in ARMS:
        arm = arms[name]
        asr, llm = arm["asr"], arm["llm"]
        if not asr.get("checkpoint") or not asr.get("backend"):
            errors.append(f"arm {name}: asr checkpoint/backend unpinned")
        elif asr["backend"] != "faster-whisper":
            errors.append(
                f"arm {name}: asr backend {asr['backend']!r} has no "
                "implementation in lifemate/asr.py (faster-whisper only)")
        if not llm.get("base") and not llm.get("merged"):
            errors.append(f"arm {name}: llm base/merged unpinned")
        if llm.get("adapter") and not llm.get("merged"):
            errors.append(
                f"arm {name}: llm adapter set without merged checkpoint; "
                "lifemate/llm.py has no adapter-merge step, so a real "
                "run cannot use this arm until Phase 2 supplies a "
                "merged checkpoint")
        if (llm.get("merged") or llm.get("base")) and not llm.get("revision"):
            errors.append(f"arm {name}: llm checkpoint without revision; "
                          "Phase 2 must pin the revision, never guess it")
        if llm.get("backend") not in ("vllm", "transformers"):
            errors.append(f"arm {name}: llm backend {llm.get('backend')!r} "
                          "not in lifemate/llm.py (vllm/transformers)")
        if llm.get("context") and llm["context"] > 16384:
            errors.append(f"arm {name}: llm context exceeds 16384")
        # Phase 2 expressibility (see to_p2_config): a real arm must
        # not claim a decode/tokenizer/stop/temperature the current
        # constructors cannot realise. These are errors in real
        # mode, not warnings, because a silent downgrade would make
        # the arm label false.
        _, gaps = to_p2_config(arm)
        for gap in gaps:
            errors.append(f"arm {name}: Phase 2 gap: {gap}")
    return errors


def to_p2_config(arm):
    """Map one four-arm arm onto the Phase 2 checkpoint-config
    schema v1 (analysis/checkpoint/checkpoint_config_schema.json in
    the p2-checkpoint branch, commit 30555b1 -- read, not edited,
    from that branch's report). Returns (config_dict, gaps), where
    gaps names every four-arm field the P2 loader cannot express
    today, instead of silently dropping it. Field mapping:
      asr.backend -> asr.kind ("faster-whisper" only buildable;
        "transformers" is declarable but UNBUILDABLE, GAP A1)
      asr.checkpoint -> asr.checkpoint (local dir preferred; a
        transformers-format dir is not loadable via FasterWhisperASR)
      asr.revision -> asr.revision, BUT P2 GAP A2: any non-null
        revision is a GAP (FasterWhisperASR takes no revision);
        "" is treated as null -- the checkpoint string/dir is the
        pin, exactly as for the own ASR.
      asr.decode.beam_size/language/greedy -> asr.beam_size/
        language/greedy, BUT P2 GAP A3: only beam 1 / "vi" / True
        are expressible (transcribe() hardcodes them); anything
        else is a GAP, as are hotwords/initial_prompt (not in the
        four-arm contract at all, so they map to null).
      llm.base/merged -> llm.checkpoint + llm.load_kind:
        base with adapter null -> "full"; merged set -> "merged";
        adapter without merged -> "adapter", UNBUILDABLE, GAP L1.
      llm.revision -> llm.revision (informational for a local dir).
      llm.tokenizer -> llm.tokenizer_source, BUT P2 GAP L2: it
        must be null or equal to the checkpoint (generators use
        the checkpoint's own tokenizer); anything else is a GAP.
      llm.template -> llm.chat_template_source, same GAP L2 rule;
        the four-arm value "model_chat_template" means "the
        checkpoint's own template" and maps to null.
      llm.stop -> llm.stop, BUT P2 GAP L4: any non-empty list is
        a GAP (stopping is the template stop token plus the
        {"stop": true} rule in parse_model_output). The four-arm
        stop list ["template_stop_token", '{"stop": true}'] is
        descriptive of that rule, so it maps to null, not to a
        custom stop list.
      llm.context -> llm.max_context_tokens (<= 16384, validated
        by loader/PipelineConfig only, not by generators, GAP L5).
      llm.decoding.temperature/seed/max_tokens -> llm.temperature/
        seed/max_tokens, BUT only temperature 0.0 is expressible
        (GAP L3), and for kind=transformers seed/max_tokens are
        ignored (hardcoded greedy/512, GAP L6).
      llm.backend -> llm.kind.
    The coordinator merge must resolve every gap in this list
    before a real C/D run; this function is the checklist."""
    asr, llm = arm["asr"], arm["llm"]
    gaps = []
    llm_checkpoint = llm.get("merged") or llm.get("base")
    if llm.get("adapter") and not llm.get("merged"):
        load_kind = "adapter"
        gaps.append("L1: adapter without merged checkpoint is unbuildable")
    elif llm.get("merged"):
        load_kind = "merged"
    else:
        load_kind = "full"
    if asr.get("backend") == "transformers":
        gaps.append("A1: transformers ASR has no class in lifemate/asr.py")
    if asr.get("revision"):
        gaps.append("A2: ASR revision is not a FasterWhisperASR parameter; "
                    "pin by local directory instead")
    dec = asr.get("decode") or {}
    if dec.get("beam_size") not in (None, 1) or dec.get("language") not in (None, "vi") \
            or dec.get("greedy") not in (None, True):
        gaps.append("A3: only ASR beam 1 / language vi / greedy True are "
                    "expressible; transcribe() hardcodes them")
    tok = llm.get("tokenizer")
    if tok not in (None, llm_checkpoint):
        gaps.append("L2: tokenizer_source differs from checkpoint; generators "
                    "use the checkpoint's own tokenizer")
    tmpl = llm.get("template")
    if tmpl not in (None, "model_chat_template", llm_checkpoint):
        gaps.append("L2: chat_template_source differs from checkpoint; "
                    "generators use the checkpoint's own template")
    stop = llm.get("stop")
    if stop and set(stop) - {"template_stop_token", '{"stop": true}'}:
        gaps.append("L4: custom stop tokens are not a generator parameter")
    decoding = llm.get("decoding") or {}
    if decoding.get("temperature") not in (None, 0.0):
        gaps.append("L3: only temperature 0.0 is expressible (vLLM hardcodes "
                    "0.0, transformers hardcodes greedy)")
    if llm.get("backend") == "transformers" and (
            decoding.get("max_tokens") not in (None, 512)
            or decoding.get("seed") not in (None, 42)):
        gaps.append("L6: TransformersGenerator ignores seed/max_tokens "
                    "(hardcoded greedy/512)")
    config = {
        "schema_version": 1,
        "asr": {"checkpoint": asr.get("checkpoint"), "kind": asr.get("backend"),
                "beam_size": dec.get("beam_size", 1),
                "greedy": dec.get("greedy", True),
                "language": dec.get("language", "vi"),
                "hotwords": None, "initial_prompt": None,
                "revision": asr.get("revision") or None,
                "device": "cuda", "compute_type": "float16"},
        "llm": {"checkpoint": llm_checkpoint, "kind": llm.get("backend"),
                "load_kind": load_kind,
                "revision": llm.get("revision") or "",
                "seed": decoding.get("seed", 42),
                "max_tokens": decoding.get("max_tokens", 512),
                "max_context_tokens": llm.get("context", 16384),
                "temperature": decoding.get("temperature", 0.0),
                "tokenizer_source": None, "chat_template_source": None,
                "stop": None, "device": None},
    }
    return config, gaps


def load_arms(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    arms = doc["arms"] if "arms" in doc else doc
    return arms


def arms_snapshot(arms):
    return json.dumps(arms, sort_keys=True, ensure_ascii=False)
