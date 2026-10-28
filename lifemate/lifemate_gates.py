"""Deterministic gates for LifeMate (Round 10).

Standalone module: standard library only, no model, no simulator access.
Each gate is a pure CPU predicate over evidence the agent already observed.
A gate never invents data: it either passes, fires (veto -> ASK), or
reports itself not-applicable for the call at hand. Precision is audited
per gate on gold trajectories plus synthetic counterfactuals (see the
Round 10 measurement report); a gate below 95% precision is dropped.

Gates (see module docstrings for exact scope; scope is part of the gate):
- Gate 1, contact_ambiguity: a write that picks one contact out of >= 2
  same-normalized-name roster entries is vetoed; the agent must ASK.
- Gate 2, read_before_write: a write that references an existing entity
  (contact, *_id, or an update/delete/cancel verb) must have prior
  evidence the entity exists: a roster entry, or a string in a
  SUCCEEDED result that is not an echo of that call's own arguments.
  Prior-call ARGUMENTS never count (fix round: a proposal, failed or
  not, is not evidence -- and sms/phone never validate contacts, so
  even a successful sms.send echoes an unvalidated id). ALL references
  of a call are checked, not just the first.
- Gate 3, confirmation: a transfer needs an explicit user confirmation
  marker in the transcript. TWO variants are implemented and audited
  separately, because the literal form contradicts gold behaviour on
  single-turn transfers (the request itself IS the authorization):
  gate_confirmation (literal) and gate_confirmation_scoped (only when a
  prior ASK exists or the transfer details are not in the current
  request). The audit decides which, if either, ships.
- AskBudget: at most max_asks ASKs per session (default 2); the same slot
  may not be asked twice (loop guard). When the budget is exhausted,
  ASK (including ASK-other) is removed and the policy is DO_NOTHING --
  never execute an unproven write as a substitute for asking.

Name comparison is NFC + lowercase exact equality (never tone folding:
tone folding is LOSSY and would merge distinct people).
"""

import re
import unicodedata
from dataclasses import dataclass, field

__all__ = [
    "GateResult",
    "PriorCall",
    "gate_contact_ambiguity",
    "gate_read_before_write",
    "gate_confirmation",
    "gate_confirmation_scoped",
    "AskBudget",
    "CONFIRMATION_MARKERS",
    "TRANSFER_TOOLS",
    "READ_VERBS",
]

TRANSFER_TOOLS = {"banking.transfer", "ewallet.transfer"}
READ_VERBS = ("search", "list", "get", "status", "forecast", "balance",
              "history", "detail")
_MUTATE_VERBS = ("update", "delete", "cancel", "modify", "reschedule",
                 "remove")
CONFIRMATION_MARKERS = [
    "đồng ý", "xác nhận", "đúng rồi", "oke", "ok", "ừ", "ừm", "chốt",
    "gửi đi", "chuyển đi", "đồng ý chuyển", "xác nhận chuyển",
]


def nfc_lower(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


@dataclass
class GateResult:
    fired: bool
    applicable: bool
    reason: str


def _tool_verb(name):
    return (name or "").split(".", 1)[1] if "." in (name or "") else ""


def _is_read_tool(name):
    verb = _tool_verb(name)
    return any(verb == v or verb.startswith(v + "_") for v in READ_VERBS)


def _contact_reference(call):
    """Return (kind, value) for a call's contact reference, or None.

    kind 'id' for contact_id / 'to'-as-id, kind 'name' for contact_name /
    'to'-as-name. A 'to' holding an email address is not a contact
    reference for these gates.
    """
    args = call.get("arguments") or {}
    if args.get("contact_id"):
        return "id", args["contact_id"]
    if args.get("contact_name"):
        return "name", args["contact_name"]
    to = args.get("to")
    if isinstance(to, str) and to and "@" not in to:
        if to.startswith("c_"):
            return "id", to
        return "name", to
    return None


def _duplicate_name_groups(roster):
    """Map normalized name -> distinct ids, for names with >= 2 ids."""
    by_name = {}
    for entry in roster or []:
        if not isinstance(entry, dict):
            continue
        name = nfc_lower(entry.get("name"))
        cid = entry.get("id")
        if name and cid:
            by_name.setdefault(name, set()).add(cid)
    return {n: ids for n, ids in by_name.items() if len(ids) >= 2}


def gate_contact_ambiguity(call, roster):
    """Gate 1: veto a write that picks one of >= 2 same-name contacts.

    call: a proposed/gold tool call. roster: [{id, name}] observed via
    search BEFORE the write (same-sample replay + history results).
    Fires iff the write's contact is a member of a duplicate-name group.
    Not applicable when the call has no contact reference, or when no
    roster was observed (that case belongs to Gate 2, not Gate 1).
    """
    if _is_read_tool(call.get("name", "")) \
            or call.get("name") == "sys.ask_missing_info":
        return GateResult(False, False, "read/ask: gate does not apply")
    ref = _contact_reference(call)
    if ref is None:
        return GateResult(False, False, "no contact reference")
    if not roster:
        return GateResult(False, False, "no roster observed")
    dups = _duplicate_name_groups(roster)
    if not dups:
        return GateResult(False, True, "roster has no duplicate names")
    kind, value = ref
    if kind == "id":
        for name, ids in dups.items():
            if value in ids:
                return GateResult(
                    True, True,
                    "contact_id %s is one of %d contacts named %r"
                    % (value, len(ids), name))
        return GateResult(False, True, "contact_id not in a duplicate group")
    name = nfc_lower(value)
    if name in dups:
        return GateResult(
            True, True,
            "name %r matches %d contacts; must ASK" % (value, len(dups[name])))
    return GateResult(False, True, "name is unique in roster")


def _entity_ids(call):
    """Entity ids a call references: *_id args (except contact_id)."""
    args = call.get("arguments") or {}
    ids = set()
    for key, value in args.items():
        if key.endswith("_id") and key != "contact_id" \
                and isinstance(value, str) and value:
            ids.add(value)
    return ids


@dataclass
class PriorCall:
    """One earlier call in the session, with its recorded outcome.

    tool: tool name. args: the call's arguments. result_scalars:
    flattened scalar values from the call's RESULT (phones dropped).
    succeeded: True only when the result indicates execution
    (ok True and done not False). A schema-rejected call (ok False)
    and an app no-op (ok True, done False -- unknown id, insufficient
    balance, empty search) both count as NOT succeeded.
    A proposal is not evidence: only succeeded results establish
    anything, and a result scalar equal to the same call's own argument
    is an echo of the proposal, not state-derived evidence, and is
    excluded (a successful sms.send echoes its own contact_id; the
    simulator never validates contacts for sms/phone, so the echo
    proves nothing).
    Legacy (tool, args) tuples are accepted and treated as
    succeeded=False with no results: they establish nothing. Callers
    must pass PriorCall objects where they know outcomes (the audit
    does).
    """
    tool: str
    args: dict = field(default_factory=dict)
    result_scalars: list = field(default_factory=list)
    succeeded: bool = False


def _as_prior_call(entry):
    if isinstance(entry, PriorCall):
        return entry
    if isinstance(entry, (tuple, list)) and len(entry) >= 2:
        return PriorCall(tool=entry[0], args=entry[1] or {},
                         result_scalars=[], succeeded=False)
    return PriorCall(tool="", args={}, result_scalars=[], succeeded=False)


def _call_string_values(args):
    """String values in a call's arguments (for echo exclusion)."""
    out = set()
    if isinstance(args, dict):
        for value in args.values():
            if isinstance(value, str):
                out.add(nfc_lower(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        out.add(nfc_lower(item))
    return out


def gate_read_before_write(call, prior_calls, rosters):
    """Gate 2: a write referencing an existing entity needs prior
    evidence that the entity exists in this session.

    prior_calls: [PriorCall] of earlier calls in this session
        (same-sample calls before the write + history calls).
    rosters: [{id, name}] observed via successful search before the
        write.
    Applicable iff the write references an entity: a contact reference,
    any *_id argument, or an update/delete/cancel/modify/reschedule verb.
    A write fully specified by the request (e.g. reminders.create with
    all slots) is NOT applicable -- there is no entity to have read.
    Evidence that establishes an entity (ALL of it must come from
    succeeded calls or rosters; prior-call ARGUMENTS never count):
      - roster ids/names (successful contacts.search results);
      - string scalars in SUCCEEDED results, excluding echoes of the
        same call's own arguments (a proposal restated by its own
        result is not state-derived evidence).
    ALL references are checked: a contact reference AND every *_id
    argument. The old code returned after the contact check alone, so
    an established contact masked an unestablished entity id (a code
    flaw; no tool in the real 147-tool catalog combines a contact
    reference with another *_id, so the fix is defence in depth, not
    a real-schema behaviour change -- see the fix report).
    Fires iff any referenced entity is unestablished; the reason lists
    every missing reference.
    """
    name = call.get("name", "")
    if _is_read_tool(name) or name == "sys.ask_missing_info":
        return GateResult(False, False, "read/ask: gate does not apply")
    ref = _contact_reference(call)
    ids = _entity_ids(call)
    verb = _tool_verb(name)
    is_mutate_verb = verb in _MUTATE_VERBS or any(
        verb.startswith(v + "_") for v in _MUTATE_VERBS)
    if ref is None and not ids and not is_mutate_verb:
        return GateResult(False, False,
                          "write references no existing entity")
    priors = [_as_prior_call(e) for e in (prior_calls or [])]
    roster_ids = {e.get("id") for e in (rosters or [])
                  if isinstance(e, dict) and e.get("id")}
    roster_names = {nfc_lower(e.get("name")) for e in (rosters or [])
                    if isinstance(e, dict) and e.get("name")}
    # State-derived strings: scalars from SUCCEEDED results, minus
    # each call's own argument echoes. Compared NFC-lowercase (ids in
    # this data are lowercase alphanumerics + underscore).
    result_strings = set()
    for pc in priors:
        if not pc.succeeded:
            continue
        echoes = _call_string_values(pc.args)
        for scalar in pc.result_scalars or []:
            if isinstance(scalar, str) \
                    and nfc_lower(scalar) not in echoes:
                result_strings.add(nfc_lower(scalar))
    established_ids = {nfc_lower(i) for i in roster_ids} | result_strings
    missing = []
    # Contact reference.
    if ref is not None:
        kind, value = ref
        if kind == "id":
            if nfc_lower(value) not in established_ids:
                missing.append("contact_id %s" % value)
        else:
            if nfc_lower(value) not in roster_names \
                    and nfc_lower(value) not in result_strings:
                missing.append("contact name %r" % value)
    # Every *_id reference (no early return after the contact).
    for eid in sorted(ids):
        if nfc_lower(eid) not in established_ids:
            missing.append("entity id %s" % eid)
    if missing:
        return GateResult(True, True,
                          "unestablished reference(s): %s"
                          % "; ".join(missing))
    if ref is not None or ids:
        return GateResult(False, True, "references established")
    # Bare mutate verb with no id argument: needs a prior SUCCEEDED
    # read of the same app family in this session.
    app = name.split(".", 1)[0] if "." in name else ""
    for pc in priors:
        if pc.succeeded and _is_read_tool(pc.tool) \
                and pc.tool.split(".", 1)[0] == app:
            return GateResult(False, True, "prior read of app family")
    return GateResult(True, True,
                      "mutate verb with no prior successful read of its "
                      "app family")


def _has_confirmation_marker(texts):
    for text in texts or []:
        hay = nfc_lower(text)
        for marker in CONFIRMATION_MARKERS:
            # Word-boundary match so "ok" does not match inside a word.
            if re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", hay):
                return True
    return False


def gate_confirmation(call, transcript_texts):
    """Gate 3 (literal): a transfer needs an explicit confirmation marker.

    transcript_texts: user turns of the session (current + history).
    Applicable only to transfer tools. Fires iff no marker is present.
    NOTE: on single-turn transfers the request itself is the
    authorization, so this literal form fires on gold-correct transfers
    and is expected to fail the 95% precision rule -- see
    gate_confirmation_scoped for the deployable form.
    """
    name = call.get("name", "")
    if name not in TRANSFER_TOOLS:
        return GateResult(False, False, "not a transfer")
    if _has_confirmation_marker(transcript_texts):
        return GateResult(False, True, "confirmation marker present")
    return GateResult(True, True, "no explicit confirmation marker")


def gate_confirmation_scoped(call, post_ask_texts, had_prior_ask,
                             instructed_in_current):
    """Gate 3 (scoped, deployable form).

    Applicable only when confirmation is actually owed: a prior ASK about
    this transfer exists in the session, or the transfer details were not
    instructed in the current request (they come from history). When the
    current request itself instructs the transfer in full, the request IS
    the authorization and no extra confirmation is required.
    post_ask_texts: user turns AFTER the ask (empty when no prior ask).
    Fires iff applicable and no confirmation marker follows the ask.
    """
    name = call.get("name", "")
    if name not in TRANSFER_TOOLS:
        return GateResult(False, False, "not a transfer")
    if not had_prior_ask and instructed_in_current:
        return GateResult(False, False,
                          "fully instructed in current request")
    if _has_confirmation_marker(post_ask_texts):
        return GateResult(False, True, "confirmation after ask present")
    return GateResult(True, True,
                      "confirmation owed (prior ask / history-sourced) "
                      "but no marker after the ask")


@dataclass
class AskBudget:
    """Per-session ASK cap + loop guard (Round 10, task 3).

    max_asks: maximum ASK turns per session (default 2, per the brief's
    "1-2 lần"). The same slot may not be asked twice: a repeated ask for
    the same missing slot is a loop, not progress.
    When the budget is exhausted, allow_ask returns False for every slot
    INCLUDING "other": ASK-other is removed as a safe harbour. The
    caller policy for a blocked ask is DO_NOTHING -- never execute an
    unproven write as a substitute for asking.
    """
    max_asks: int = 2
    asks: list = field(default_factory=list)

    def allow_ask(self, slot):
        if len(self.asks) >= self.max_asks:
            return False
        if slot in self.asks:
            return False
        return True

    def record_ask(self, slot):
        if not self.allow_ask(slot):
            return False
        self.asks.append(slot)
        return True

    @property
    def remaining(self):
        return max(0, self.max_asks - len(self.asks))

    def reset(self):
        self.asks = []
