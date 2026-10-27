"""Constrained decoding + schema enforcement + loop guard for LifeMate.

Offline-only design for Zalo AI Challenge 2026 (LifeMate track):

* One NVIDIA A30, at most 30 seconds per sample.
* LLM < 5B: Qwen3-4B-Instruct-2507 (4.0B total). Qwen2.5-Coder-7B-Instruct
  (7.61B total) is NOT eligible as the LifeMate LLM and must not be used here.
* Output must be valid JSON tool calls conforming to ``tools_catalog.json``.
* Calls are executed only through ``zaic_tools`` (never by reading state files).

What constrained decoding guarantees, and what it does not:

* Guaranteed (when the schema and backend are correct): the output parses as
  JSON and matches the schema shape (tool name in enum, per-tool arguments).
* NOT guaranteed: the right tool, the right entity/amount/date, the right
  call order, or the right final state (``state_hash``). Those are enforced by
  the code validator, selective reads, and the loop guard in this module.

This module is importable without a GPU: the vLLM engine is built lazily
inside :func:`build_engine`, so the schema builder, validator, and loop guard
can be unit-tested offline. Only :func:`build_engine` and
:meth:`ToolAgent.generate_tool_call` require vLLM + a GPU.

Evaluator caveat (ASSUMPTION, not verified in this research): whether failed
calls must be submitted, whether read calls count toward tool-call F1, and
what a submission must contain when the agent stops early have not been
verified against the official evaluator/README. The guard below therefore
preserves the executed trace as-is and never filters failed calls or appends
cleanup writes. Verify those rules before finalising a submission.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Literal

# ---------------------------------------------------------------------------
# Catalog model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    """One tool from ``tools_catalog.json``.

    ``parameters`` is the tool's JSON Schema for its arguments (an object
    schema). ``kind`` mirrors the catalog (``read`` / ``write`` / ``meta``).
    ``x_ref`` / ``x_one_of`` style constraints live inside the argument
    schemas and are checked generically by :func:`validate_tool_call`.
    """

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    kind: str = "write"


def normalize_catalog(catalog: dict[str, Any]) -> dict[str, ToolSpec]:
    """Normalise a tools catalog into ``{tool_name: ToolSpec}``.

    Accepted shapes (the real ZAIC catalog shape must be confirmed against
    the downloaded ``<split>_tools_catalog.json`` before shipping):

    * ``{"tools": [{"name": ..., "parameters": {...}}, ...]}``
    * ``{"tool_name": {"parameters": {...}, "description": ...}, ...}``
    * ``{"tool_name": {"input_schema": {...}}, ...}`` (schema under another key)
    """
    tools: dict[str, ToolSpec] = {}
    raw_tools: Iterable[Any]
    if isinstance(catalog.get("tools"), list):
        raw_tools = catalog["tools"]
    else:
        raw_tools = [
            {"name": name, **(spec if isinstance(spec, dict) else {})}
            for name, spec in catalog.items()
        ]
    for raw in raw_tools:
        if not isinstance(raw, dict) or "name" not in raw:
            raise ValueError(f"catalog entry has no tool name: {raw!r}")
        parameters = (
            raw.get("parameters")
            or raw.get("input_schema")
            or raw.get("args_schema")
            or {"type": "object", "properties": {}, "required": []}
        )
        if not isinstance(parameters, dict):
            raise ValueError(f"tool {raw['name']!r} has a non-object schema")
        tools[str(raw["name"])] = ToolSpec(
            name=str(raw["name"]),
            description=str(raw.get("description", "")),
            parameters=parameters,
            kind=str(raw.get("kind", "write")),
        )
    if not tools:
        raise ValueError("catalog contains no tools")
    return tools


def filter_catalog_by_installed_apps(
    tools: dict[str, ToolSpec],
    installed_apps: Iterable[str],
    tool_to_app: dict[str, str],
) -> dict[str, ToolSpec]:
    """Keep only tools belonging to an installed app.

    The mapping ``tool -> app`` must come from the catalog / sample context.
    If a tool has no app mapping, it is dropped: generating a call for an app
    the user does not have installed can only produce a failed call.
    """
    installed = set(installed_apps)
    return {
        name: spec
        for name, spec in tools.items()
        if tool_to_app.get(name) in installed
    }


def schema_fingerprint(schema: dict[str, Any]) -> str:
    """Stable cache key for a compiled schema (avoids recompiling per sample)."""
    blob = json.dumps(schema, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSON Schema construction (one branch per tool)
# ---------------------------------------------------------------------------


def build_tool_call_schema(tools: dict[str, ToolSpec]) -> dict[str, Any]:
    """Build a single-call JSON Schema with one branch per tool.

    Using ``oneOf`` + ``const`` for the tool name binds each tool's argument
    schema to that tool. A flat schema with a shared free-form ``arguments``
    object would allow tool A's arguments under tool B's name -- valid JSON,
    wrong semantics -- so it is only a fallback (see module notes), never
    the default.
    """
    branches: list[dict[str, Any]] = []
    for name in sorted(tools):
        spec = tools[name]
        arguments = dict(spec.parameters)
        arguments.setdefault("type", "object")
        branches.append(
            {
                "type": "object",
                "properties": {
                    "name": {"const": name},
                    "arguments": arguments,
                },
                "required": ["name", "arguments"],
                "additionalProperties": False,
            }
        )
    return {
        "type": "object",
        "oneOf": branches,
        "additionalProperties": False,
    }


def build_fallback_schema(tools: dict[str, ToolSpec]) -> dict[str, Any]:
    """Weaker schema for backends that reject ``oneOf``.

    Constrained decoding then only guarantees parseable JSON and a valid
    tool name; :func:`validate_tool_call` must do the rest. Log loudly
    whenever this fallback is used -- never silently accept a weaker schema.
    """
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string", "enum": sorted(tools)},
            "arguments": {"type": "object"},
        },
        "required": ["name", "arguments"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Code validation (runs after constrained decoding, always)
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single validated tool call ready for ``zaic_tools`` execution."""

    name: str
    arguments: dict[str, Any]


_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "null": lambda v: v is None,
}


def _check_value(
    value: Any,
    schema: dict[str, Any],
    path: str,
    allowed_refs: dict[str, set[str]],
    errors: list[str],
) -> None:
    """Recursively check one value against a (subset of) JSON Schema."""
    expected = schema.get("type")
    if isinstance(expected, str) and not _TYPE_CHECKS[expected](value):
        errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum {schema['enum']!r}")
    if isinstance(value, str):
        if "pattern" in schema and not re.fullmatch(str(schema["pattern"]), value):
            errors.append(f"{path}: {value!r} does not match pattern {schema['pattern']!r}")
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value!r} below minimum {schema['minimum']!r}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value!r} above maximum {schema['maximum']!r}")
    # Catalog-style cross-reference constraints (generic, not tool-specific).
    # ``x-ref`` names a reference set supplied by the caller (e.g. contact
    # ids read from the environment); ``x-one-of`` is a closed value list.
    if "x-ref" in schema:
        allowed = allowed_refs.get(str(schema["x-ref"]), set())
        if allowed and value not in allowed:
            errors.append(f"{path}: {value!r} is not a known {schema['x-ref']}")
    if "x-one-of" in schema and value not in schema["x-one-of"]:
        errors.append(f"{path}: {value!r} not in x-one-of {schema['x-one-of']!r}")
    if isinstance(value, dict) and isinstance(schema.get("properties"), dict):
        for prop in schema.get("required", []):
            if prop not in value:
                errors.append(f"{path}.{prop}: missing required argument")
        for prop, sub in schema["properties"].items():
            if prop in value and isinstance(sub, dict):
                _check_value(value[prop], sub, f"{path}.{prop}", allowed_refs, errors)
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(schema["properties"])
            if unknown:
                errors.append(f"{path}: unknown arguments {sorted(unknown)!r}")


def validate_tool_call(
    obj: Any,
    tools: dict[str, ToolSpec],
    allowed_refs: dict[str, set[str]] | None = None,
) -> tuple[ToolCall | None, list[str]]:
    """Validate a parsed object as a tool call.

    Returns ``(ToolCall, [])`` on success, or ``(None, [errors])`` on failure.
    Never executes anything: validation is strictly pre-call.
    """
    allowed_refs = allowed_refs or {}
    if not isinstance(obj, dict):
        return None, ["top level: expected a JSON object"]
    errors: list[str] = []
    name = obj.get("name")
    if name not in tools:
        return None, [f"name: unknown tool {name!r}"]
    arguments = obj.get("arguments")
    if not isinstance(arguments, dict):
        return None, ["arguments: expected a JSON object"]
    _check_value(arguments, tools[name].parameters, "arguments", allowed_refs, errors)
    if errors:
        return None, errors
    return ToolCall(name=name, arguments=arguments), []


def parse_tool_call(
    text: str,
    tools: dict[str, ToolSpec],
    allowed_refs: dict[str, set[str]] | None = None,
) -> ToolCall:
    """Parse and validate model output text as a tool call.

    Raises ``ValueError`` with all validation errors joined. Constrained
    decoding should make parse failures rare; when they happen, the caller
    must treat them as a failed generation attempt, not silently repair them
    (repairing by guessing an entity or amount is how wrong writes happen).
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"output is not valid JSON: {exc}") from exc
    call, errors = validate_tool_call(obj, tools, allowed_refs)
    if call is None:
        raise ValueError("tool call failed validation: " + "; ".join(errors))
    return call


# ---------------------------------------------------------------------------
# vLLM engine (lazy import: importing this module needs no GPU)
# ---------------------------------------------------------------------------


def build_engine(
    model: str = "Qwen/Qwen3-4B-Instruct-2507",
    max_model_len: int = 16384,
    gpu_memory_utilization: float = 0.85,
    guided_decoding_backend: str = "xgrammar",
) -> Any:
    """Build an offline vLLM engine with XGrammar guided decoding.

    Args:
        model: LifeMate LLM. Must be < 5B total parameters. The default is
            Qwen3-4B-Instruct-2507 (4.0B). Do NOT pass Qwen2.5-Coder-7B here.
        max_model_len: LifeMate context cap is 16K tokens.
        gpu_memory_utilization: fraction of the A30's 24 GB reserved by vLLM.
        guided_decoding_backend: ``"xgrammar"`` (default, fastest in reported
            benchmarks); ``"outlines"`` is the first fallback if xgrammar is
            unavailable or rejects the schema.

    The engine is created once per process and reused across samples: schema
    compilation is cached by the backend, and re-creating the engine per
    sample would waste most of the 30-second budget on model loading.
    """
    from vllm import LLM  # local import: module import must not require a GPU

    return LLM(
        model=model,
        max_model_len=max_model_len,
        dtype="bfloat16",
        gpu_memory_utilization=gpu_memory_utilization,
        guided_decoding_backend=guided_decoding_backend,
    )


def build_sampling_params(schema: dict[str, Any], max_tokens: int = 512) -> Any:
    """Build sampling params with structured output, across vLLM versions.

    vLLM renamed its structured-output API over versions (``guided_*`` fields
    were removed in 0.12 in favour of ``StructuredOutputParams``). This shim
    tries the newest API first and falls back, but it is NOT a substitute for
    pinning exactly one vLLM version in ``requirements.txt`` and testing the
    real schema against it on an A30 before shipping.
    """
    from vllm import SamplingParams

    try:  # vLLM >= 0.12 style
        from vllm.sampling_params import StructuredOutputParams

        return SamplingParams(
            temperature=0.0,
            max_tokens=max_tokens,
            structured_outputs=StructuredOutputParams(json=schema),
        )
    except ImportError:
        pass
    try:  # older guided-decoding style
        from vllm.sampling_params import GuidedDecodingParams

        return SamplingParams(
            temperature=0.0,
            max_tokens=max_tokens,
            guided_decoding=GuidedDecodingParams(json=schema),
        )
    except ImportError:
        pass
    # Oldest style: guided_json passed directly to SamplingParams.
    return SamplingParams(
        temperature=0.0,
        max_tokens=max_tokens,
        guided_json=json.dumps(schema, ensure_ascii=False),
    )


# ---------------------------------------------------------------------------
# Loop guard: stop, replan once, finish the trace as-is
# ---------------------------------------------------------------------------

GuardAction = Literal["continue", "replan_once", "stop"]


@dataclass
class LoopGuard:
    """Detect repetition / no-progress loops and stop them safely.

    Rules (see module notes and the report §4):

    * The same (tool, normalised arguments) a second time is suspicious;
      a third time stops the loop immediately -- it is never executed.
    * Consecutive steps with no state progress also stop the loop.
    * Stopping NEVER appends ``sys.ask_missing_info`` or ``[]`` and NEVER
      filters failed calls. The executed trace is returned as-is.
    * ``sys.ask_missing_info`` and ``[]`` are separate, explicitly checked
      decisions (see :func:`request_missing_info` and
      :func:`empty_if_no_app`), not loop fallbacks.
    """

    max_steps: int = 12
    max_repeats: int = 2  # a call seen this many times triggers replan/stop
    max_no_progress_steps: int = 3

    _seen: dict[str, int] = field(default_factory=dict, init=False)
    _replanned: bool = field(default=False, init=False)
    _no_progress: int = field(default=0, init=False)
    _steps: int = field(default=0, init=False)

    @staticmethod
    def _call_key(call: ToolCall) -> str:
        """Normalised identity of a call (sorted keys, stable JSON)."""
        return json.dumps(
            {"name": call.name, "arguments": call.arguments},
            sort_keys=True,
            ensure_ascii=False,
        )

    def repeat_count(self, call: ToolCall) -> int:
        """How many times this exact call has already been executed."""
        return self._seen.get(self._call_key(call), 0)

    def record(self, call: ToolCall, state_progress: bool) -> GuardAction:
        """Record one executed call and decide what happens next."""
        self._steps += 1
        if self._steps >= self.max_steps:
            return "stop"
        key = self._call_key(call)
        self._seen[key] = self._seen.get(key, 0) + 1
        self._no_progress = 0 if state_progress else self._no_progress + 1
        if self._seen[key] > self.max_repeats:
            return "stop"  # third identical call: never execute it again
        if self._seen[key] == self.max_repeats:
            return "replan_once" if not self._replanned else "stop"
        if self._no_progress >= self.max_no_progress_steps:
            return "replan_once" if not self._replanned else "stop"
        return "continue"

    def mark_replanned(self) -> None:
        """Mark that the single replan has been used."""
        self._replanned = True


def request_missing_info(
    writes_executed: int,
    slot_groundable_by_any_read: bool,
) -> bool:
    """Decide whether ``sys.ask_missing_info`` is legitimate.

    Only valid when nothing has been written yet AND the missing slot cannot
    be grounded by any read. It is a grounding conclusion, never a
    loop-fallback: callers must not invoke this merely because the loop
    guard stopped the agent.
    """
    return writes_executed == 0 and not slot_groundable_by_any_read


def empty_if_no_app(
    request_handled_by_any_installed_app: bool,
) -> bool:
    """Decide whether returning ``[]`` is legitimate.

    Only valid after an explicit catalog check shows no installed app can
    handle the request. This check belongs in pre-flight, before the agent
    loop -- not after a loop has already executed calls.
    """
    return not request_handled_by_any_installed_app


# ---------------------------------------------------------------------------
# Minimal agent loop skeleton (execution is delegated to zaic_tools)
# ---------------------------------------------------------------------------


@dataclass
class ToolAgent:
    """Generate-validate-execute loop with constrained decoding + guard.

    ``execute`` is a caller-supplied callable wrapping ``zaic_tools``: it
    takes a :class:`ToolCall` and returns ``(ok, state_progress)`` where
    ``state_progress`` is True when the call moved the environment toward
    the goal (the caller decides this from the tool result, not from the
    model's opinion of it). This module never reads state files directly.
    """

    engine: Any
    tools: dict[str, ToolSpec]
    execute: Callable[[ToolCall], tuple[bool, bool]]
    guard: LoopGuard = field(default_factory=LoopGuard)
    allowed_refs: dict[str, set[str]] = field(default_factory=dict)

    def generate_tool_call(self, prompt: str, max_tokens: int = 512) -> ToolCall:
        """Generate one tool call under the catalog schema, then validate it."""
        schema = build_tool_call_schema(self.tools)
        params = build_sampling_params(schema, max_tokens=max_tokens)
        outputs = self.engine.generate([prompt], params)
        text = outputs[0].outputs[0].text
        return parse_tool_call(text, self.tools, self.allowed_refs)

    def run(self, prompt: str) -> list[ToolCall]:
        """Run until the guard stops the loop; return the executed trace.

        The returned trace is the submission material: it is returned as-is,
        including failed calls, and nothing is appended after stopping.
        """
        executed: list[ToolCall] = []
        current_prompt = prompt
        while True:
            call = self.generate_tool_call(current_prompt)
            # Pre-execution check: a call already executed max_repeats times
            # is NEVER executed again. This is what makes "third identical
            # call stops the loop" true; checking only after execution would
            # let the third call through.
            if self.guard.repeat_count(call) >= self.guard.max_repeats:
                if self.guard._replanned:
                    return executed
                self.guard.mark_replanned()
                current_prompt = (
                    f"{prompt}\n\nPrevious calls (do not repeat them): "
                    f"{[c.name for c in executed]}. "
                    "Choose a different, evidence-backed action or stop."
                )
                continue
            ok, progress = self.execute(call)
            executed.append(call)
            action = self.guard.record(call, state_progress=progress)
            if action == "continue":
                continue
            if action == "replan_once":
                self.guard.mark_replanned()
                # Replan prompt: only facts already observed (previous calls,
                # their results, cached reads). No new guessed entities.
                current_prompt = (
                    f"{prompt}\n\nPrevious calls (do not repeat them): "
                    f"{[c.name for c in executed]}. "
                    "Choose a different, evidence-backed action or stop."
                )
                continue
            return executed  # "stop": finish the trace as-is


# ---------------------------------------------------------------------------
# Offline demo (no GPU, no vLLM): schema + validation + guard behaviour
# ---------------------------------------------------------------------------

DEMO_CATALOG: dict[str, Any] = {
    "tools": [
        {
            "name": "contacts.search",
            "kind": "read",
            "description": "Search contacts by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "minLength": 1}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "banking.transfer",
            "kind": "write",
            "description": "Transfer money to a contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "x-ref": "contact_id"},
                    "amount": {"type": "number", "minimum": 0},
                },
                "required": ["contact_id", "amount"],
                "additionalProperties": False,
            },
        },
        {
            "name": "sys.ask_missing_info",
            "kind": "meta",
            "description": "Ask the user for a missing slot.",
            "parameters": {
                "type": "object",
                "properties": {"slot": {"type": "string"}},
                "required": ["slot"],
                "additionalProperties": False,
            },
        },
    ]
}


def demo() -> None:
    """Demonstrate schema building, validation, and the loop guard offline."""
    tools = normalize_catalog(DEMO_CATALOG)
    schema = build_tool_call_schema(tools)
    print("schema fingerprint:", schema_fingerprint(schema))
    print("schema branches:", len(schema["oneOf"]))

    refs = {"contact_id": {"c-1", "c-2"}}
    good = parse_tool_call(
        '{"name": "banking.transfer", "arguments": {"contact_id": "c-1", "amount": 50000}}',
        tools,
        refs,
    )
    print("valid call:", good)
    try:
        parse_tool_call(
            '{"name": "banking.transfer", "arguments": {"contact_id": "c-99", "amount": 50000}}',
            tools,
            refs,
        )
    except ValueError as exc:
        print("correctly rejected unknown contact_id:", exc)

    guard = LoopGuard()
    repeated = ToolCall(name="contacts.search", arguments={"name": "An"})
    for step in range(4):
        # Pre-execution check first: the third identical call is blocked
        # before it can be executed, not after.
        if guard.repeat_count(repeated) >= guard.max_repeats:
            if guard._replanned:
                print(f"step {step + 1}: identical call blocked before execution; stopping")
                break
            guard.mark_replanned()
            print(f"step {step + 1}: identical call blocked before execution; replanning once")
            continue
        action = guard.record(repeated, state_progress=False)
        print(f"step {step + 1}: executed, guard -> {action}")
        if action == "replan_once":
            guard.mark_replanned()
        if action == "stop":
            print("loop stopped; trace is returned as-is, nothing appended")
            break

    print("ask_missing_info legitimate (no writes, ungroundable):",
          request_missing_info(writes_executed=0, slot_groundable_by_any_read=False))
    print("ask_missing_info legitimate (writes already executed):",
          request_missing_info(writes_executed=1, slot_groundable_by_any_read=False))
    print("empty [] legitimate (no app can handle):",
          empty_if_no_app(request_handled_by_any_installed_app=False))

    if os.environ.get("LIFEMATE_RUN_VLLM") == "1":
        engine = build_engine()
        agent = ToolAgent(engine=engine, tools=tools, execute=lambda c: (True, True))
        print("vLLM engine built (GPU path only, set LIFEMATE_RUN_VLLM=1).")
        _ = agent  # generation needs a real prompt + zaic_tools; see report §3.


if __name__ == "__main__":
    demo()
