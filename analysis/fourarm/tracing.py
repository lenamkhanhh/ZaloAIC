"""Trace building for the REAL run path (wrapper layer only).

The harness never reimplements AgentLoop. It wraps a real generator
from lifemate/llm.py, runs the real lifemate/agent.py AgentLoop, and
records what the loop itself exposes:

  * generations: one entry per generator call -- prompt, raw model
    output (when the backend exposes it), parsed call, timing, and
    the observation fed back (derived from the prompt sequence,
    exactly as in Tier 1a: the loop renders each observation into
    the NEXT prompt, so the suffix of the next prompt after the base
    prompt IS the observation for that generation);
  * proposal vs executed: parsed_call is the proposal; the
    submission line's tool_calls are the executed calls, in order.
    A generation whose next prompt carries a validation-failure
    observation was NOT executed; its parsed call is recorded with
    error="validation_failed_not_executed". The loop does not expose
    a separate validation-result list, and this module does not
    pretend otherwise -- validation outcome is the observation kind,
    not a re-run of validation;
  * grounding: loop.grounding_log (raw proposal -> grounded call),
    recorded verbatim, never used to alter a call;
  * observer: loop.observer.records (the real ShadowObserver
    attribute), shadow-only, never consulted to alter a call;
  * termination: the loop returns only a submission line, so the
    exact guard termination is NOT exposed. termination.kind is
    "stop" when the last generation returned a stop, "max_steps"
    when max_steps generations ran, and otherwise
    "returned_before_max_steps" with n_generations -- an honest
    label, not an invented guard reason. The mock path (see
    mock_backends.py) has exact termination because it is a
    simulator; the real path must not copy that precision.

Raw output, honestly (Tier 1a wrapper rule): for the vLLM backend
the inner LLM's generate() is shimmed and the raw text is recorded
before parsing; for the transformers backend generated token ids are
captured and the suffix after the templated prompt is decoded. If
neither path is available, raw_output is null WITH an explicit
reason -- raw text is never reconstructed from the parsed call and
never invented. Token counts come from the generator's tokenizer
when available, else null with a reason.

TRACE SCHEMA (one JSON line per sample-run, run phase only -- no
score, no gold call, no gold transcript in a run trace):
    sample_id, split ("dev"), arm, mode ("mock" | "real"),
    asr (arm snapshot), llm (arm snapshot), shared (arm snapshot),
    transcript_current, transcript_source ("arm_asr" | "mock_asr"),
    wav_path, wav_sha256, prompt_sha256,
    generations[]: {prompt_sha256, raw_output, raw_output_reason,
        raw_output_token_count, prompt_token_count,
        token_count_reason, parsed_call, error, seconds,
        observation_following, observation_kind},
    grounding_log, observer_log,
    tool_calls (executed, = submission), state_hash,
    termination {kind, n_generations},
    seconds, run_error

Full prompts are NOT stored in real traces (only prompt_sha256):
prompts contain catalog + history and would bloat traces and leak
sample content into reports. The mock path stores short mock prompts
because they are synthetic. Score phase reads run traces from disk
first, then gold -- it never runs the agent, and the run phase never
feeds a scored trace back into an agent (no trace/gold in prompts).
"""
from __future__ import annotations

import hashlib
import time


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class _VLLMGenerateCapture:
    def __init__(self, inner, recorder):
        self._inner = inner
        self.recorder = recorder

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def generate(self, prompts, sampling_params, *args, **kwargs):
        result = self._inner.generate(prompts, sampling_params, *args, **kwargs)
        try:
            out = result[0].outputs[0]
            self.recorder.append({
                "raw_text": getattr(out, "text", None),
                "token_ids": list(getattr(out, "token_ids", None) or []),
            })
        except Exception as exc:
            self.recorder.append({"raw_text": None, "token_ids": [],
                                  "capture_error": str(exc)})
        return result


class _TransformersGenerateCapture:
    def __init__(self, inner, recorder):
        self._inner = inner
        self.recorder = recorder

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def generate(self, *args, **kwargs):
        result = self._inner.generate(*args, **kwargs)
        try:
            ids = result[0].tolist() if hasattr(result[0], "tolist") else list(result[0])
            self.recorder.append({"generated_ids": ids})
        except Exception as exc:
            self.recorder.append({"generated_ids": [], "capture_error": str(exc)})
        return result


class TracingGenerator:
    """Wrap a real lifemate generator; record generations honestly."""

    def __init__(self, inner):
        self.inner = inner
        self.generations = []
        self.prompts = []  # in-memory only; never written to a trace
        self._raw = []
        self._tok = getattr(inner, "tokenizer", None)
        self._install_capture()
        self.base_prompt = None

    def _install_capture(self):
        llm_obj = getattr(self.inner, "llm", None)
        if llm_obj is not None and not isinstance(llm_obj, _VLLMGenerateCapture):
            try:
                self.inner.llm = _VLLMGenerateCapture(llm_obj, self._raw)
                self._capture_kind = "vllm"
                return
            except Exception:
                pass
        if llm_obj is not None:
            self._capture_kind = "vllm"
            return
        model_obj = getattr(self.inner, "model", None)
        if model_obj is not None:
            if not isinstance(model_obj, _TransformersGenerateCapture):
                try:
                    self.inner.model = _TransformersGenerateCapture(model_obj, self._raw)
                except Exception:
                    self._capture_kind = "unavailable"
                    return
            self._capture_kind = "transformers"
            return
        self._capture_kind = "unavailable"

    def _prompt_token_count(self, prompt):
        if self._tok is None:
            return None, "no tokenizer on generator"
        try:
            templated = self._tok.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=False,
                add_generation_prompt=True)
            ids = self._tok(templated, add_special_tokens=False)["input_ids"]
            return len(ids), None
        except Exception:
            try:
                ids = self._tok(prompt, add_special_tokens=False)["input_ids"]
                return len(ids), "chat-template tokenisation failed; plain prompt count"
            except Exception as exc:
                return None, f"tokenizer failed: {exc}"

    def _raw_for_call(self, index, prompt):
        if self._capture_kind == "unavailable" or index >= len(self._raw):
            return (None, "generator backend does not expose raw output "
                    "through this wrapper", None,
                    "no raw output captured; count unavailable")
        cap = self._raw[index]
        if cap.get("capture_error"):
            return None, f"raw capture failed: {cap['capture_error']}", None, \
                "raw capture failed; count unavailable"
        if self._capture_kind == "vllm":
            raw = cap.get("raw_text")
            toks = cap.get("token_ids") or []
            if raw is not None and toks:
                return raw, None, len(toks), None
            if raw is not None and self._tok is not None:
                try:
                    n = len(self._tok(raw, add_special_tokens=False)["input_ids"])
                    return raw, None, n, None
                except Exception as exc:
                    return raw, None, None, f"tokenizer failed: {exc}"
            return raw, None, None, "no token ids and no tokenizer"
        ids = cap.get("generated_ids") or []
        if not ids or self._tok is None:
            return (None, "transformers capture has no ids or no tokenizer",
                    None, "count unavailable")
        try:
            templated = self._tok.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=False,
                add_generation_prompt=True)
            plen = len(self._tok(templated, add_special_tokens=False)["input_ids"])
            gen_ids = ids[plen:]
            raw = self._tok.decode(gen_ids, skip_special_tokens=True)
            return raw, None, len(gen_ids), None
        except Exception as exc:
            return None, f"transformers decode failed: {exc}", None, \
                "decode failed; count unavailable"

    def __call__(self, prompt, tools):
        if self.base_prompt is None:
            self.base_prompt = prompt
        self.prompts.append(prompt)
        start = time.time()
        out = self.inner(prompt, tools)
        seconds = time.time() - start
        idx = len(self.generations)
        raw, raw_reason, raw_toks, tok_reason = self._raw_for_call(idx, prompt)
        prompt_toks, prompt_tok_reason = self._prompt_token_count(prompt)
        reason = raw_reason or prompt_tok_reason
        error = None
        if isinstance(out, dict) and out.get("name") == "__invalid__":
            error = "invalid_json_output"
        self.generations.append({
            "prompt_sha256": sha256_text(prompt),
            "raw_output": raw,
            "raw_output_reason": raw_reason,
            "raw_output_token_count": raw_toks,
            "prompt_token_count": prompt_toks,
            "token_count_reason": reason if (raw_toks is None or prompt_toks is None) else None,
            "parsed_call": out,
            "error": error,
            "seconds": seconds,
            "observation_following": None,
            "observation_kind": None,
        })
        return out

    def finalise_observations(self):
        """Fill observation kinds from the in-memory prompt sequence,
        then the caller drops self.prompts before writing the trace."""
        self.finalise_observations_from_prompts(self.prompts)

    def finalise_observations_from_prompts(self, prompts):
        """Fill observation_following/kind from the prompt sequence.
        prompts[i] is the prompt of generations[i]."""
        gens = self.generations
        base = prompts[0] if prompts else ""
        for i, gen in enumerate(gens):
            if i + 1 >= len(gens) or i + 1 >= len(prompts):
                continue
            nxt = prompts[i + 1]
            suffix = nxt[len(base):] if nxt.startswith(base) else nxt
            gen["observation_following"] = suffix
            if "validation failed" in suffix:
                gen["observation_kind"] = "validation_failure_observation"
                if gen["error"] is None:
                    gen["error"] = "validation_failed_not_executed"
            elif "not a valid tool call" in suffix:
                gen["observation_kind"] = "invalid_output_reprompt"
            elif "Choose a different" in suffix:
                gen["observation_kind"] = "replan_observation"
            elif "Previous calls and their OBSERVED results" in suffix:
                gen["observation_kind"] = "observation"
            else:
                gen["observation_kind"] = "other_prompt_suffix"


def termination_from_generations(generations, max_steps):
    """Honest termination label for the real loop (see module doc)."""
    if not generations:
        return {"kind": "no_generation", "n_generations": 0}
    last = generations[-1]
    if last.get("parsed_call") is None:
        return {"kind": "stop", "n_generations": len(generations)}
    if len(generations) >= max_steps:
        return {"kind": "max_steps", "n_generations": len(generations)}
    return {"kind": "returned_before_max_steps",
            "n_generations": len(generations)}
