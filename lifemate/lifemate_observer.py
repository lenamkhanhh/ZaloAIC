"""Shadow-only G&G observer for the LifeMate agent loop (R5, worker C).

The observer computes the coordinator-owned adapter decision
(``lifemate_gates_adapter.decide``) for proposals that reach the
agent loop, and LOGS it. It NEVER changes agent behaviour:

- Flag OFF (default): the loop checks ``observer.enabled`` first and
  skips every observer call, so no observer code runs at all.
- Flag ON: the observer records one JSON-serialisable record per
  observed generation. It never mutates the proposal, the grounded
  call, validation, submitted calls, state, retry count, termination,
  or prompt ordering. It never inserts an ask, never rewrites
  arguments, never calls extra tools.
- The observer NEVER raises: every public method catches all
  exceptions internally and records them in the record's ``error``
  field (or drops the record only if even recording fails, which
  cannot happen for a plain list append). An observer exception must
  never become an agent error.

Allowed inputs ONLY: the current transcript, permitted context
(the loop's tools/kind map), history, and prior observations
(executed calls + their results). FORBIDDEN: gold labels, future
results, environment internals/state. The observer never calls
``env`` methods; it rebuilds its prefix from what the loop already
observed (history + executed/results), mirroring the paired audit's
prefix construction (see ``build_prefix``). Roster evidence is built
from observed contacts.search results in that same prefix, NOT from
the loop's grounding roster, so the observer is independent of the
grounding flag.

Record schema (exactly these keys, all JSON-serialisable):

- ``proposal_raw``: the generator's proposal before grounding
  (or the raw generator output for invalid generations).
- ``proposal_grounded``: the call that went to validation (after
  grounding / ask conversion), or None when there is none.
- ``validation_outcome``: "ok" | "failed" | "invalid".
  "failed" means validation rejected the call: it was NOT executed
  and NOT submitted. "invalid" means the generator output was not a
  usable tool call (non-dict or missing "name").
- ``baseline_decision``: {"fired", "applicable", "reason"} from the
  adapter's baseline gate, or None when no decision was computed
  (ask proposals, validation failures, invalid generations, or an
  observer error).
- ``candidate_decision``: {"fired", "applicable"} from the adapter,
  or None as above.
- ``adjustments``: the adapter's adjustment trail (list of dicts),
  or [] when no decision was computed.
- ``eligibility``: the adapter's R5 object-state eligibility report
  ({consumer, entity_id, status, reason}) when a decision was
  computed with eligibility enabled, else None. Report-only: it
  never changes fired/applicable. Unknown means unsupported
  consumer, missing entity, or missing context — never a guess.
- ``error``: None on success, else ``repr`` of the exception that
  prevented a decision (import failure, unparseable history, adapter
  exception, ...). An error record still proves the agent ran
  unchanged: the proposal flowed through the baseline path.
- ``position``: the evidence position of the proposal
  (``proposal_position`` passed to the adapter: max prefix position
  + 1). This is NOT a unique sequence number: two failed attempts at
  the same evidence position share it, because neither entered the
  prefix. Record order (list order) is the observation order.

Import safety: this module imports ONLY the standard library at
module level. The coordinator-owned adapter is imported LAZILY
inside ``_get_decide`` and only when flag ON and a decision is
actually needed. The adapter and its dependencies use
intra-package relative imports, and every outside consumer
(scripts, tests, entrypoints) imports them as ``lifemate.*``
with the repo root on ``sys.path`` -- the same contract as the
real entrypoint (``lifemate/run.py``). Adding lifemate/ itself
to ``sys.path`` is NOT required and must not be relied on: a
record with an import error in a clean process means the
contract is broken, not that the observer is "working". If the
import fails, the record carries the error and the agent keeps
its baseline behaviour.
"""
from __future__ import annotations

import json

ASK_TOOL = "sys.ask_missing_info"

_decide_cache = {"fn": None}


def _get_decide():
    """Return the coordinator-owned adapter decide(), importing it
    lazily and caching success. Raises on import failure; the caller
    (observe_proposal) converts that into an error record."""
    fn = _decide_cache.get("fn")
    if fn is not None:
        return fn
    from .lifemate_gates_adapter import decide

    _decide_cache["fn"] = decide
    return decide


def _safe(value):
    """Deep-copy via a JSON round-trip so records never alias live
    objects and are always JSON-serialisable. Falls back to a repr
    wrapper for values that cannot round-trip."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"__unserializable__": repr(value)}


def _outcome_of(result):
    """Outcome vocabulary, mirroring the paired audit's outcome_of:
    ok True + done not False -> "succeeded"; ok False ->
    "schema_rejected"; ok True + done False -> "noop"; anything else
    (including non-dict results) -> "unknown"."""
    if not isinstance(result, dict):
        return "unknown"
    if result.get("ok") is True and result.get("done") is not False:
        return "succeeded"
    if result.get("ok") is False:
        return "schema_rejected"
    return "noop"


def _collect_rosters(value, out):
    """Recursively collect {id, name, phone} roster entries from a
    result value, mirroring the paired audit's collect_rosters:
    any "contacts" list with id-bearing entries counts; recursion
    does not descend into "phone" values."""
    if isinstance(value, dict):
        contacts = value.get("contacts")
        if isinstance(contacts, list):
            for entry in contacts:
                if isinstance(entry, dict) and entry.get("id"):
                    out.append({"id": entry["id"],
                                "name": entry.get("name", ""),
                                "phone": entry.get("phone", "")})
        for key, item in value.items():
            if key != "phone":
                _collect_rosters(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_rosters(item, out)


def collect_rosters_from_prefix(prefix):
    """Roster evidence from observed contacts.search results in the
    prefix (history + session), in prefix order, deduped by id.
    History results that are not search results contribute nothing
    unless they carry a "contacts" list (same rule as the audit)."""
    out = []
    seen = set()
    for entry in prefix or []:
        if not isinstance(entry, dict):
            continue
        found = []
        _collect_rosters(entry.get("result"), found)
        for contact in found:
            if contact["id"] not in seen:
                seen.add(contact["id"])
                out.append(contact)
    return out


def build_prefix(history, executed, results):
    """Build the adapter prefix from history + session observations,
    mirroring the paired audit exactly:

    - History turns in order: a user turn becomes
      {"kind": "user_turn", "text": <audio_text or "">, "position": p};
      an assistant turn contributes one event per tool call, zipped
      with tool_results by index (missing result -> None):
      {"tool", "args", "result", "outcome", "position": p,
      "origin": "history"}.
    - Session events (executed/results zipped) continue positions
      after history with origin "session".
    - Positions are one contiguous counter; the next proposal's
      proposal_position is len(prefix).

    Returns (prefix, error): on success error is None. On unparseable
    history (tool_results present but not a list), returns
    (None, message): the caller must NOT compute a decision on a
    partial prefix; it records the error instead. A None tool_results
    is a no-call assistant turn and contributes no events (same as
    the audit's ``or []``).
    """
    prefix = []
    pos = 0
    for turn in history or []:
        role = getattr(turn, "role", None)
        if role == "user":
            text = getattr(turn, "audio_text", None)
            prefix.append({"kind": "user_turn",
                           "text": text if text is not None else "",
                           "position": pos})
            pos += 1
        elif role == "assistant":
            calls = getattr(turn, "tool_calls", None) or []
            res = getattr(turn, "tool_results", None)
            if res is None:
                continue
            if not isinstance(res, list):
                return None, ("history tool_results not a list "
                              "(unparseable); prefix withheld")
            for idx, call in enumerate(calls):
                if not isinstance(call, dict) or "name" not in call:
                    continue
                result = res[idx] if idx < len(res) else None
                prefix.append({"tool": call["name"],
                               "args": call.get("arguments") or {},
                               "result": result,
                               "outcome": _outcome_of(result),
                               "position": pos,
                               "origin": "history"})
                pos += 1
    for call, result in zip(executed or [], results or []):
        if not isinstance(call, dict) or "name" not in call:
            continue
        prefix.append({"tool": call["name"],
                       "args": call.get("arguments") or {},
                       "result": result,
                       "outcome": _outcome_of(result),
                       "position": pos,
                       "origin": "session"})
        pos += 1
    return prefix, None


class ShadowObserver:
    """Per-run shadow log. One instance lives on the AgentLoop; the
    loop calls reset() at the start of every run() so no state leaks
    across samples. Every method below never raises."""

    def __init__(self, enabled=False):
        self.enabled = bool(enabled)
        self.records = []

    def reset(self):
        try:
            self.records = []
        except Exception:
            pass

    def _append(self, record):
        try:
            self.records.append(record)
        except Exception:
            pass

    def observe_invalid(self, raw, history=None, executed=None,
                        results=None):
        """Record a generator output that was not a usable tool call
        (non-dict or missing "name"). No decision is computed."""
        try:
            prefix, _err = build_prefix(history, executed, results)
            position = len(prefix) if prefix is not None else 0
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": None,
                "validation_outcome": "invalid",
                "baseline_decision": None,
                "candidate_decision": None,
                "adjustments": [],
                "eligibility": None,
                "error": None,
                "position": position,
            })
        except Exception as exc:  # never leak into the agent
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": None,
                "validation_outcome": "invalid",
                "baseline_decision": None,
                "candidate_decision": None,
                "adjustments": [],
                "eligibility": None,
                "error": repr(exc),
                "position": 0,
            })

    def observe_validation_failure(self, raw, grounded, error,
                                   history=None, executed=None,
                                   results=None):
        """Record a proposal rejected by validation: NOT executed,
        NOT submitted, no decision computed."""
        try:
            prefix, _err = build_prefix(history, executed, results)
            position = len(prefix) if prefix is not None else 0
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": _safe(grounded),
                "validation_outcome": "failed",
                "baseline_decision": None,
                "candidate_decision": None,
                "adjustments": [],
                "eligibility": None,
                "error": None,
                "position": position,
            })
        except Exception as exc:  # never leak into the agent
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": _safe(grounded),
                "validation_outcome": "failed",
                "baseline_decision": None,
                "candidate_decision": None,
                "adjustments": [],
                "eligibility": None,
                "error": repr(exc),
                "position": 0,
            })

    def observe_proposal(self, raw, grounded, history=None,
                         executed=None, results=None, current_text="",
                         kinds=None):
        """Record a validated proposal with its adapter decision.
        Ask proposals are recorded with no decision: the gate scope
        excludes sys.ask_missing_info (same as the paired audit).
        Any failure (prefix build, adapter import, adapter exception)
        becomes an error record; the agent flow is untouched."""
        try:
            prefix, prefix_error = build_prefix(history, executed,
                                                results)
            if prefix is None:
                self._append({
                    "proposal_raw": _safe(raw),
                    "proposal_grounded": _safe(grounded),
                    "validation_outcome": "ok",
                    "baseline_decision": None,
                    "candidate_decision": None,
                    "adjustments": [],
                    "eligibility": None,
                    "error": prefix_error,
                    "position": 0,
                })
                return
            position = len(prefix)
            grounded_name = grounded.get("name") if isinstance(
                grounded, dict) else None
            if grounded_name == ASK_TOOL:
                self._append({
                    "proposal_raw": _safe(raw),
                    "proposal_grounded": _safe(grounded),
                    "validation_outcome": "ok",
                    "baseline_decision": None,
                    "candidate_decision": None,
                    "adjustments": [],
                    "eligibility": None,
                    "error": None,
                    "position": position,
                })
                return
            roster = collect_rosters_from_prefix(prefix)
            try:
                decision = _get_decide()(
                    grounded, prefix, roster, current_text, kinds,
                    proposal_position=position, eligibility=True)
            except Exception as exc:
                self._append({
                    "proposal_raw": _safe(raw),
                    "proposal_grounded": _safe(grounded),
                    "validation_outcome": "ok",
                    "baseline_decision": None,
                    "candidate_decision": None,
                    "adjustments": [],
                    "eligibility": None,
                    "error": repr(exc),
                    "position": position,
                })
                return
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": _safe(grounded),
                "validation_outcome": "ok",
                "baseline_decision": {
                    "fired": decision.baseline_fired,
                    "applicable": decision.applicable,
                    "reason": decision.baseline_reason,
                },
                "candidate_decision": {
                    "fired": decision.fired,
                    "applicable": decision.applicable,
                },
                "adjustments": _safe(decision.adjustments),
                "eligibility": _safe(
                    (decision.notes or {}).get("eligibility")),
                "error": None,
                "position": position,
            })
        except Exception as exc:  # last-resort guard: never raise
            try:
                self._append({
                    "proposal_raw": _safe(raw),
                    "proposal_grounded": _safe(grounded),
                    "validation_outcome": "ok",
                    "baseline_decision": None,
                    "candidate_decision": None,
                    "adjustments": [],
                    "eligibility": None,
                    "error": repr(exc),
                    "position": 0,
                })
            except Exception:
                pass

    def to_json(self):
        """Serialise the log (for artifacts/debugging). Never raises."""
        try:
            return json.dumps(self.records, ensure_ascii=False)
        except Exception:
            return "[]"
