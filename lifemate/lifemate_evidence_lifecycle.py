"""Evidence lifecycle ledger (rule engine, NOT a DAG) for LifeMate G&G.

Problem it solves (Round 10 follow-up): the gates' read-before-write
check treats a once-established id as established forever. In the
simulator, state moves: an id read successfully can later be
deleted, a booking can be cancelled, a contact phone can be
patched, and a value copied from one record into another goes
stale when its source changes. This module tracks those
transitions, in prefix order, from implementation-verified rules.

What it is: a chronological ledger (journal) + a rule engine that
replays the journal. It is deliberately NOT called a DAG: there is
no graph construction, no topological ordering, no proof search.
Derived claims are resolved by following declared ``derived_from``
links recursively (with a cycle guard); that is link-following,
not DAG proving. See ``research/lifemate/gg_lifecycle_notes.md``
for the implementation-verified mutation table this ledger is
built on.

Core semantics (all verified against zaic_tools implementation):

* Outcome rule (executor.py + base.App): only a call returning
  ``ok is True`` with ``done`` not ``False`` counts as succeeded.
  Schema rejection (``ok`` False) and app no-ops (``ok`` True,
  ``done`` False -- unknown id, insufficient balance, already
  cancelled, empty search) change nothing and therefore invalidate
  nothing. A result of ``{"ok": True}`` with NO ``done`` key (e.g.
  App.delete, email.archive's delete branch) IS succeeded.
* Three independent claims per entity: ``existence`` (the entity
  is present), ``field_value`` (a specific field currently holds a
  specific value), ``eligibility`` (the entity is live/open enough
  for a follow-up action). One mutation kills only the claims it
  touches: update phone kills the old phone field_value, not
  existence; a status-only cancel kills eligibility (and the
  ``status`` field_value), not existence; a delete kills all
  three for that entity.
* Evidence records are independent: a mutation kills only the
  records it is linked to (same registry + same entity, see
  ``_record_linked``). A key is ``active`` if ANY surviving record
  supports it, ``invalidated`` if records existed but all were
  killed, ``unknown`` otherwise (no record, ambiguous record, or a
  dead derived source).
* Prefix order is journal order. ``apply_prefix`` sorts by
  position; a mutation never affects records later in the journal
  (future calls/results are invisible to earlier queries), and
  ``query(..., position=P)`` considers only journal entries at or
  before P. A later succeeded re-read re-establishes a killed
  claim with fresh evidence (newer position wins for that record
  set, but never revives a killed record -- it adds a new one).
* Registry isolation: keys are (registry, value, claim[, field]).
  The same id string in two registries never interacts.

Schemas (the coordinator's integration contract; JSON-able dicts):

Evidence record::

    {"kind": "phone"|"contact"|"entity", "value": <normalized>,
     "source": "roster"|"call_log"|"message_log"|"user_text"
               |"history_text"|"read_result"|"write_result",
     "producer": <tool name or "user">, "field": <field/path>,
     "outcome": "succeeded"|"failed"|"schema_rejected"|"noop",
     "counterpart": <record identity dict or None>,
     "position": <int>, "claim": "existence"|"field_value"
               |"eligibility",
     "status": "active"|"invalidated"|"ambiguous"|"unknown",
     "reason": <short str>}

Mutation event::

    {"tool": str, "args": dict, "result": dict, "position": int,
     "registry": str, "entity_value": str,
     "mutation_kind": "delete"|"cancel"|"update"|"create"|"none",
     "effective": bool}

Registry resolution for an evidence record, in order: an explicit
``registry`` key on the record; ``counterpart["registry"]``; the
producer tool's registry in MUTATION_TABLE; else ``"unknown"``
(only queryable as ``"unknown"`` -- the adapter should always
supply a registry; an unresolvable record never silently matches
a real registry).

Field-value records are entity-scoped: the ledger keys them by
(counterpart["id"] if present else value, field). A field_value
query is therefore an entity + field query: pass the entity id as
``value`` and the field path as ``field``. Querying a field_value
without ``field`` returns the unique field's status if exactly one
field is recorded for that entity, else ``"unknown"`` with reason
``field_value_query_requires_field`` (fail-closed, never a guess).

Derived claims: an evidence record may carry an OPTIONAL extra
key ``derived_from`` -- a list of {"registry", "value", "claim"}
(+ optional "field") source keys -- or equivalently
``counterpart == {"derived_from": [...]}``. When the record itself
is alive, each source is resolved at the same position; any
invalidated source makes the derived claim ``"unknown"`` with
reason ``derived_source_invalidated``; any unknown source makes it
``"unknown"`` with reason ``derived_source_unknown``. Derived
resolution is recursive with a cycle guard (cycle -> ``unknown``,
``derived_cycle``).

What this module does NOT do (explicit non-goals):

* It does not classify tool calls into mutation events -- the
  adapter does that from MUTATION_TABLE (tool names alone are
  insufficient: email.archive is delete iff action == "delete",
  else a folder update; bill_payment.pay with source == "ewallet"
  additionally debits the wallet). Multi-effect tools need one
  event per affected (registry, entity) pair.
* It does not model action-specific guards (flights.check_in
  refuses a cancelled or already-checked-in booking; video_meeting
  .join refuses a cancelled meeting; library.reserve refuses an
  already-reserved book). Generic ``eligibility`` is killed only
  by delete, status-only cancel, and updates setting status to
  "cancelled" or enabled to False. Action-specific preconditions
  must be checked by the adapter from field_value claims (e.g.
  checked_in == True) or a fresh read -- the ledger gives it the
  field evidence to do so, it does not pretend generic
  eligibility covers every guard.
* It does not validate values, normalize phones, or parse text.
  Values are compared exactly as given; normalization is the
  adapter's job (Thread A owns phone normalization).
* It never invents evidence: mutation events create no evidence.
  A create only becomes evidence when the adapter records its
  result as an evidence record. (Edge: App.new_id can REUSE an id
  after a delete shrinks the collection; position order + a fresh
  create-result record handle that -- the killed record stays
  killed, the new record is new evidence.)

Pure Python, stdlib only. No imports from lifemate_gates or
lifemate_provenance (the coordinator owns integration).

R5 (worker B) additions, appended at the end of this module:

* ``field_value_record`` -- the canonical record shape for entity
  field evidence: counterpart {"id": entity}, value = observed
  field value, field = field path. The adapter's current
  build_ledger records flattened result values as ``existence``
  records (value = observed value, field = leaf name, counterpart
  None) -- those carry NO entity link and therefore can NEVER
  satisfy an entity field check or expire by entity mutation.
  Field checks (eligibility + prover validity) require the
  counterpart convention; the coordinator must extend build_ledger
  to emit field_value records, or pass snapshots. Until then,
  field checks correctly return unknown, never a guessed value.
* ``EvidenceLedger.query_field_value`` -- (status, observed,
  reason) for one entity field, fail-closed on non-linked records.
* ``EvidenceLedger.field_invalidated_since`` -- snapshot staleness
  probe: did any succeeded mutation touch this entity field after
  the snapshot's position?
* ``check_eligibility`` -- (status, reason) with status in
  {"eligible", "ineligible", "unknown"} for supported consumers
  only (see CONSUMER_CONTRACTS / UNSUPPORTED_CONSUMERS).
* ``make_prover_validity`` -- adapts a ledger + proposal position
  into the callable the prover's ``validity`` parameter expects.
"""

from __future__ import annotations

CLAIMS = ("existence", "field_value", "eligibility")
OUTCOMES = ("succeeded", "failed", "schema_rejected", "noop")
STATUSES = ("active", "invalidated", "ambiguous", "unknown")
MUTATION_KINDS = ("delete", "cancel", "update", "create", "none")

# Status-like fields: a status-only cancel kills the field_value
# claim for these fields (the old status value no longer holds).
STATUS_FIELDS = ("status",)
# Terminal transitions on update that also kill generic eligibility
# (entity stops being live/open): status -> cancelled, enabled -> False.
TERMINAL_STATUS_VALUES = ("cancelled",)


# ---------------------------------------------------------------------------
# Outcome classification (executor.py semantics)
# ---------------------------------------------------------------------------

def result_succeeded(result) -> bool:
    """True iff the call executed: ok is True and done is not False.

    ``{"ok": True}`` (no ``done`` key -- App.delete, App.create,
    most patches) counts as succeeded; ``{"ok": True, "done":
    False}`` (app noop) and ``{"ok": False}`` (schema rejection)
    do not. Non-dict results are never succeeded.
    """
    if not isinstance(result, dict):
        return False
    return result.get("ok") is True and result.get("done") is not False


def classify_outcome(result) -> str:
    """Map a raw tool result to the ledger's outcome vocabulary."""
    if not isinstance(result, dict):
        return "failed"
    if result.get("ok") is False:
        return "schema_rejected"
    if result.get("ok") is True and result.get("done") is False:
        return "noop"
    if result_succeeded(result):
        return "succeeded"
    return "failed"


# ---------------------------------------------------------------------------
# Mutation table (implementation-verified; see gg_lifecycle_notes.md)
#
# tool -> {"registry", "id_arg", "mutation_kind", ...}. This table
# classifies the PRIMARY effect. Tools with side effects list them
# under "side_effects" (one entry per extra affected entity -- the
# adapter must emit one mutation event per entry). Tools whose
# kind depends on arguments say so in "notes" and carry
# "kind_arg" where applicable.
# ---------------------------------------------------------------------------

def _e(registry, id_arg, kind, **kw):
    d = {"registry": registry, "id_arg": id_arg, "mutation_kind": kind}
    d.update(kw)
    return d


MUTATION_TABLE = {
    # -- generic App.create / App.patch / App.delete forms --------
    "calendar.create_event": _e("calendar.events", None, "create"),
    "calendar.update_event": _e("calendar.events", "event_id", "update"),
    "calendar.cancel_event": _e("calendar.events", "event_id", "cancel",
                                notes="patch status=cancelled; entity remains"),
    "flights.book": _e("flights.bookings", None, "create",
                       notes="new booking, status confirmed; flight record untouched (FK only)"),
    "flights.cancel": _e("flights.bookings", "booking_id", "cancel",
                         notes="patch status=cancelled; entity remains"),
    "flights.check_in": _e("flights.bookings", "booking_id", "update",
                           fields=["checked_in"],
                           notes="guarded: noop if cancelled or already checked in; sets checked_in=True"),
    "food_delivery.place_order": _e("food_delivery.orders", None, "create",
                                    notes="new order, status placed; restaurant/menu untouched"),
    "food_delivery.cancel_order": _e("food_delivery.orders", "order_id", "cancel",
                                     notes="patch status=cancelled; entity remains"),
    "ride_hailing.book": _e("ride_hailing.rides", None, "create",
                            notes="new ride, status booked"),
    "ride_hailing.cancel": _e("ride_hailing.rides", "ride_id", "cancel",
                              notes="patch status=cancelled; entity remains"),
    "contacts.update": _e("contacts.contacts", "contact_id", "update",
                          notes="patch phone/email, only non-None args applied"),
    "email.send": _e("email.sent", None, "create"),
    "email.create_draft": _e("email.drafts", None, "create"),
    "email.reply": _e("email.sent", None, "create",
                     side_effects=[{"registry": "email.emails",
                                    "mutation_kind": "update",
                                    "fields": ["unread", "replied"],
                                    "notes": "original email: unread=False, replied=True"}]),
    "email.archive": _e("email.emails", "email_id", "update",
                        kind_arg="action",
                        fields=["folder"],
                        notes="action=='delete' -> DELETE (App.delete, returns {ok: True} with NO item); "
                              "otherwise patch folder=archive, entity remains. "
                              "fields applies ONLY to the update branch; the adapter MUST reclassify "
                              "by action arg first (reviewer fix R2-B2)."),
    "tasks.add": _e("tasks.tasks", None, "create",
                    notes="new task, done=False"),
    "tasks.complete": _e("tasks.tasks", "task_id", "update",
                         fields=["done"],
                         notes="patch done=True; idempotent, no guard"),
    "reminders.create": _e("reminders.reminders", None, "create"),
    "reminders.complete": _e("reminders.reminders", "reminder_id", "update",
                             fields=["done"],
                             notes="patch done=True"),
    "reminders.delete": _e("reminders.reminders", "reminder_id", "delete"),
    "alarm.create": _e("alarm.alarms", None, "create",
                       notes="new alarm, enabled=True"),
    "alarm.update": _e("alarm.alarms", "alarm_id", "update",
                       notes="patch time/label/enabled; enabled=False disables (terminal for eligibility)"),
    "alarm.delete": _e("alarm.alarms", "alarm_id", "delete"),
    "smart_home.light_set": _e("smart_home.devices", "device_id", "update",
                               notes="patch nested state.*; require type=light, else noop"),
    "smart_home.fan_set": _e("smart_home.devices", "device_id", "update",
                             notes="patch nested state.*; require type=fan, else noop"),
    "smart_home.climate_set": _e("smart_home.devices", "device_id", "update",
                                 notes="patch nested state.*; require type=climate, else noop"),
    "smart_home.switch_set": _e("smart_home.devices", "device_id", "update",
                                notes="patch nested state.*; no type require"),
    "smart_home.scene_run": _e("smart_home.devices", None, "update",
                               notes="MULTI-ENTITY: updates state.* of every action device + sets active_scene; "
                                     "guarded: noop (atomic, nothing applied) if scene missing or any action device missing. "
                                     "Adapter must emit one event per affected device."),
    "household_chores.assign": _e("household_chores.chores", "chore_id", "update",
                                  notes="patch assignee; guarded: chore must exist and assignee must be a member"),
    "shopping_list.add": _e("shopping_list.items", None, "create",
                            notes="new item, checked=False"),
    "shopping_list.remove": _e("shopping_list.items", "item_id", "delete"),
    "shopping_list.check": _e("shopping_list.items", "item_id", "update",
                              fields=["checked"],
                              notes="patch checked=True"),
    "home_security.arm": _e("home_security.global", None, "update",
                            notes="global mode field, not an entity; entity_value='mode'"),
    "home_security.acknowledge_alert": _e("home_security.alerts", "alert_id", "update",
                                          notes="patch acknowledged=True"),
    "door_lock.set_lock": _e("door_lock.locks", "lock_id", "update",
                             notes="patch locked"),
    "door_lock.grant_guest_code": _e("door_lock.guest_codes", None, "create",
                                     notes="code is a pure function of (lock_id, valid_until); guarded: lock must exist, "
                                           "valid_until must be tz-aware ISO. Derived claim: code depends on lock existence + valid_until."),
    "chat_ott.send_message": _e("chat_ott.chats", "chat_id", "update",
                                notes="appends a message to chat.messages; chat existence unchanged, messages field changes"),
    "chat_ott.send_location": _e("chat_ott.chats", "chat_id", "update",
                                 notes="appends a location message; same as send_message"),
    "chat_ott.call": _e("chat_ott.calls", None, "create",
                        notes="new OTT call record, status dialing; chat untouched"),
    "sms.send": _e("sms.messages", None, "create",
                   notes="never validates contacts (contact_ref completion only); result contact_id is an echo, not evidence"),
    "phone.call": _e("phone.calls", None, "create",
                     notes="never validates contacts (contact_ref completion only); result contact_id is an echo, not evidence"),
    "home_automation.create_rule": _e("home_automation.rules", None, "create",
                                      notes="guarded: device must exist in smart_home.devices when installed; "
                                            "device_id is a cross-app FK, not a mutation of smart_home"),
    "home_automation.delete_rule": _e("home_automation.rules", "rule_id", "delete"),
    "notes.create": _e("notes.notes", None, "create"),
    "notes.append": _e("notes.notes", "note_id", "update",
                       notes="content APPENDS (old + newline + new); an equality claim 'content == old' dies"),
    "library.reserve": _e("library.reservations", None, "create",
                          side_effects=[{"registry": "library.books",
                                         "mutation_kind": "update",
                                         "fields": ["available"],
                                         "notes": "book available=False; guarded: book exists, no ready/waiting reservation"}]),
    "subscriptions.cancel": _e("subscriptions.subscriptions", "subscription_id", "cancel",
                               notes="patch status=cancelled; guarded: already-cancelled -> noop. Entity remains."),
    "banking.transfer": _e("banking.transactions", None, "create",
                           side_effects=[{"registry": "banking.accounts",
                                          "mutation_kind": "update",
                                          "fields": ["balance"],
                                          "notes": "from-account balance decreases; guarded: accounts/beneficiary exist, balance sufficient"}]),
    "banking.open_savings": _e("banking.savings", None, "create",
                               side_effects=[{"registry": "banking.accounts",
                                              "mutation_kind": "update",
                                              "fields": ["balance"],
                                              "notes": "from-account balance decreases; guarded: account exists, balance sufficient"}]),
    "bill_payment.pay": _e("bill_payment.bills", "bill_id", "update",
                           fields=["paid", "paid_with"],
                           notes="patch paid=True, paid_with=source; guarded: bill exists, not already paid. "
                                 "source=='ewallet' additionally debits ewallet balance + creates an ewallet transaction (separate event)."),
    "bill_payment.schedule_autopay": _e("bill_payment.autopays", None, "update",
                                        notes="UPSERT by type: updates the existing entry for the type, else creates one"),
    "bike_rental.reserve": _e("bike_rental.reservations", None, "create",
                              side_effects=[{"registry": "bike_rental.bikes",
                                             "mutation_kind": "update",
                                             "fields": ["available"],
                                             "notes": "bike available=False; guarded: bike exists and is available"}]),
    "video_meeting.create": _e("video_meeting.meetings", None, "create",
                               notes="new meeting, status scheduled, link derived from (new id, start); "
                                     "guarded: attendees must be in contacts.contacts when installed"),
    "video_meeting.join": _e("video_meeting.meetings", "meeting_id", "update",
                             fields=["status"],
                             notes="patch status=joined; guarded: noop if missing or cancelled"),
    "music.play": _e("music.global", None, "update",
                     notes="global now_playing; guarded: track/playlist must exist"),
    "music.control": _e("music.global", None, "update",
                        notes="global now_playing status / volume; noop if nothing playing (except volume)"),
    "music.add_to_playlist": _e("music.playlists", "playlist_id", "update",
                                fields=["track_ids"],
                                notes="appends track_id to track_ids; guarded: track+playlist exist, not already present"),
    "tv.tune": _e("tv.global", None, "update",
                   notes="global power/channel; guarded: channel must be in channels list"),
    "tv.control": _e("tv.global", None, "update",
                     notes="global power/volume/muted"),
    "tv.record": _e("tv.recordings", None, "create",
                    notes="guarded: program exists, not already scheduled"),
    "medication.add": _e("medication.schedules", None, "create"),
    "medication.log_taken": _e("medication.logs", None, "create",
                               notes="guarded: schedule must exist"),
    "medication.remove": _e("medication.schedules", "schedule_id", "delete"),
    "robot_vacuum.start": _e("robot_vacuum.global", None, "update",
                             notes="global status/current_job; guarded: rooms valid, battery >= 15%"),
    "robot_vacuum.stop": _e("robot_vacuum.global", None, "update",
                            notes="global status=docked, current_job=None"),
    "appliances.start_cycle": _e("appliances.appliances", "appliance_id", "update",
                                 notes="patch nested state.*; guarded: cycle valid, not running/scheduled"),
    "appliances.stop": _e("appliances.appliances", "appliance_id", "update",
                          notes="patch nested state to idle"),
    "home_energy.set_alert": _e("home_energy.global", None, "update",
                                notes="global alert_threshold_kwh"),
    "loyalty.redeem": _e("loyalty.vouchers", None, "create",
                         side_effects=[{"registry": "loyalty.programs",
                                        "mutation_kind": "update",
                                        "fields": ["points"],
                                        "notes": "program points decrease; guarded: program+reward exist, points sufficient"}]),
    "ewallet.transfer": _e("ewallet.transactions", None, "create",
                           side_effects=[{"registry": "ewallet.global",
                                          "mutation_kind": "update",
                                          "fields": ["balance"],
                                          "notes": "wallet balance decreases; guarded: balance sufficient; phone->contact completion only"}]),
    "ewallet.topup_mobile": _e("ewallet.transactions", None, "create",
                               side_effects=[{"registry": "ewallet.global",
                                              "mutation_kind": "update",
                                              "fields": ["balance"],
                                              "notes": "wallet balance decreases; guarded: balance sufficient"}]),
    "ewallet.pay_qr": _e("ewallet.transactions", None, "create",
                         side_effects=[{"registry": "ewallet.global",
                                        "mutation_kind": "update",
                                        "fields": ["balance"],
                                        "notes": "wallet balance decreases; guarded: balance sufficient"}]),
    "fitness.log_workout": _e("fitness.workouts", None, "create",
                              notes="new workout; time defaults to session now when omitted"),
    "fitness.set_goal": _e("fitness.global", None, "update",
                           notes="global goal_steps"),
    "learning.enroll": _e("learning.courses", "course_id", "update",
                          notes="patch enrolled=True; guarded: course exists, not already enrolled"),
    "learning.schedule_lesson": _e("learning.lessons", None, "create",
                                   notes="guarded: course must exist"),
    "learning.log_progress": _e("learning.progress", None, "create",
                                side_effects=[{"registry": "learning.courses",
                                               "mutation_kind": "update",
                                               "fields": ["progress_minutes"],
                                               "notes": "course progress_minutes increases; guarded: course exists"}]),
    "maps.save_place": _e("maps.saved_places", None, "update",
                          notes="UPSERT by place_id: re-saving only relabels the existing entry, else creates one"),
    "package_tracking.reschedule_delivery": _e("package_tracking.shipments", "tracking_id", "update",
                                               notes="patch scheduled_time; guarded: shipment exists, not delivered. "
                                                     "Registry key is the shipment's tracking_id."),
    "package_tracking.schedule_pickup": _e("package_tracking.pickups", None, "create",
                                           notes="new pickup, status scheduled"),
    "news.save": _e("news.saved", None, "update",
                    notes="UPSERT by article_id: saving twice keeps a single entry"),
    "podcast_radio.play": _e("podcast_radio.global", None, "update",
                             notes="global now_playing (+ removes a played episode from queue); guarded: episode/station exists"),
    "podcast_radio.subscribe": _e("podcast_radio.global", None, "update",
                                  fields=["subscriptions"],
                                  notes="appends show_id to subscriptions; noop if already subscribed"),
    "podcast_radio.queue": _e("podcast_radio.global", None, "update",
                              notes="appends episode_id to queue; noop if already queued"),
    "sys.ask_missing_info": _e("sys.meta", None, "none",
                               notes="meta tool: recorded in the call list only, touches no state"),
}


def classify_tool(tool: str):
    """MUTATION_TABLE entry for a tool name, or None for read-only /
    unknown tools. Reads are not in the table (they mutate nothing).
    """
    return MUTATION_TABLE.get(tool)


def cancel_tools_are_status_only() -> bool:
    """Verified property of the implementation: every tool whose
    primary kind is 'cancel' patches status=cancelled and removes
    nothing. There is NO cancel tool that truly deletes an entity
    (checked 2026-10-29 across all apps; see notes). A cancel that
    deletes would have to be invented -- the table refuses to."""
    return all(e["mutation_kind"] != "cancel" or "status=cancelled" in e.get("notes", "")
               for e in MUTATION_TABLE.values())


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def _record_registry(record: dict) -> str:
    if record.get("registry"):
        return str(record["registry"])
    cp = record.get("counterpart")
    if isinstance(cp, dict) and cp.get("registry"):
        return str(cp["registry"])
    entry = MUTATION_TABLE.get(record.get("producer") or "")
    if entry is not None:
        return entry["registry"]
    return "unknown"


def _record_entity(record: dict):
    """Entity id a record belongs to: counterpart id if present,
    else the record's value (for existence/eligibility records the
    value IS the entity id)."""
    cp = record.get("counterpart")
    if isinstance(cp, dict) and cp.get("id") is not None:
        return str(cp["id"])
    return None if record.get("value") is None else str(record["value"])


def _derived_sources(record: dict):
    """Declared source keys for a derived claim, or None."""
    if isinstance(record.get("derived_from"), list):
        return record["derived_from"]
    cp = record.get("counterpart")
    if isinstance(cp, dict) and isinstance(cp.get("derived_from"), list):
        return cp["derived_from"]
    return None


def _is_status_field(field) -> bool:
    if not isinstance(field, str):
        return False
    return field == "status" or field.endswith(".status")


def _touched_fields(mutation: dict):
    """Field paths an update touches. Explicit 'fields' wins; else
    derived from args (non-id args with non-None values -- exactly
    what App.patch applies). Returns None when the touched set is
    unknown (update with no args/fields info): the caller cannot
    prove which fields survived, so the ledger kills ALL field
    claims for that entity (conservative, documented)."""
    if isinstance(mutation.get("fields"), list):
        return list(mutation["fields"])
    args = mutation.get("args")
    if not isinstance(args, dict):
        return None
    touched = [k for k, v in args.items()
               if v is not None and not str(k).endswith("_id")
               and k not in ("action",)]
    return touched


def _field_matches(record_field, touched: list) -> bool:
    """A record field is touched if it equals a touched path, or
    equals 'state.' + a touched path (smart_home/appliances nested
    state patches), or its state.-stripped form is touched."""
    if record_field is None:
        return False
    rf = str(record_field)
    for t in touched:
        t = str(t)
        if rf == t or rf == "state." + t:
            return True
        if rf.startswith("state.") and rf[6:] == t:
            return True
    return False


def _terminal_update(mutation: dict) -> bool:
    """An update that makes the entity non-live: status -> a
    terminal value, or enabled -> False. (done=True is NOT
    terminal here: completion is idempotent in the implementation
    -- a done task can be patched again -- so it kills only the
    done field_value, not generic eligibility. Action-specific
    guards are the adapter's job; see module docstring.)"""
    args = mutation.get("args")
    if not isinstance(args, dict):
        return False
    if args.get("status") in TERMINAL_STATUS_VALUES:
        return True
    if args.get("enabled") is False:
        return True
    return False


class EvidenceLedger:
    """Chronological evidence ledger with implementation-rule
    invalidation. Journal order == prefix order; positions are
    audit labels, journal order is authoritative."""

    def __init__(self):
        self._journal = []  # entries in journal order
        self._seq = 0

    # -- ingestion ------------------------------------------------------
    def add_evidence(self, record: dict) -> dict:
        rec = dict(record)
        if rec.get("claim") not in CLAIMS:
            raise ValueError("evidence claim must be one of %r" % (CLAIMS,))
        if rec.get("status") not in STATUSES:
            raise ValueError("evidence status must be one of %r" % (STATUSES,))
        if not isinstance(rec.get("position"), int):
            raise ValueError("evidence position must be an int")
        entry = {"_type": "evidence", "_seq": self._seq, **rec}
        self._seq += 1
        self._insert(entry)
        return dict(rec)

    def apply_mutation(self, event: dict) -> dict:
        ev = dict(event)
        if ev.get("mutation_kind") not in MUTATION_KINDS:
            raise ValueError("mutation_kind must be one of %r" % (MUTATION_KINDS,))
        if not isinstance(ev.get("position"), int):
            raise ValueError("mutation position must be an int")
        succeeded = bool(ev.get("effective", True)) and result_succeeded(ev.get("result"))
        entry = {"_type": "mutation", "_seq": self._seq,
                 "_succeeded": succeeded, **ev}
        if not succeeded:
            entry["_ignored_reason"] = (
                "ineffective_flag" if not ev.get("effective", True)
                else "outcome_not_succeeded:" + classify_outcome(ev.get("result")))
        self._seq += 1
        self._insert(entry)
        return dict(ev)

    def apply_prefix(self, events) -> None:
        """Apply a mixed list of evidence records and mutation
        events in position order (stable for equal positions).
        An event is a mutation iff it carries 'mutation_kind'."""
        ordered = sorted(events, key=lambda e: e.get("position", 0))
        for e in ordered:
            if "mutation_kind" in e:
                self.apply_mutation(e)
            else:
                self.add_evidence(e)

    def _insert(self, entry: dict) -> None:
        # Keep the journal sorted by position (stable by insertion
        # sequence). Callers normally feed increasing positions;
        # this keeps out-of-order ingestion prefix-correct too.
        pos = entry.get("position", 0)
        idx = len(self._journal)
        while idx > 0 and self._journal[idx - 1].get("position", 0) > pos:
            idx -= 1
        self._journal.insert(idx, entry)

    # -- core evaluation -------------------------------------------------
    def _record_killed_by(self, record: dict, mutation: dict):
        """Reason string if this (succeeded) mutation kills this
        record, else None. Only mutations EARLIER in journal order
        than the record are considered by the caller (replay)."""
        if mutation.get("registry") != _record_registry(record):
            return None
        entity = mutation.get("entity_value")
        if entity is None:
            return None
        linked = (_record_entity(record) == str(entity)
                  or (record.get("value") is not None
                      and str(record["value"]) == str(entity)))
        if not linked:
            return None
        kind = mutation.get("mutation_kind")
        claim = record.get("claim")
        if kind == "delete":
            return "deleted@pos%d" % mutation.get("position", 0)
        if kind == "cancel":
            if claim == "eligibility":
                return "cancelled@pos%d" % mutation.get("position", 0)
            if claim == "field_value" and _is_status_field(record.get("field")):
                return "status_cancelled@pos%d" % mutation.get("position", 0)
            return None
        if kind == "update":
            if claim == "eligibility" and _terminal_update(mutation):
                return "terminal_update@pos%d" % mutation.get("position", 0)
            if claim == "field_value":
                touched = _touched_fields(mutation)
                if touched is None:
                    return "update_unknown_fields@pos%d" % mutation.get("position", 0)
                if _field_matches(record.get("field"), touched):
                    return "field_updated@pos%d" % mutation.get("position", 0)
            if claim == "existence" and record.get("field") is not None:
                # An existence record grounded in a specific field
                # (e.g. a phone number grounded in a contact's
                # phone field) dies when that field changes. An
                # entity's own existence record (field None/"id")
                # never dies on update -- "id" is never a touched
                # field (id args are excluded from touched sets).
                touched = _touched_fields(mutation)
                if touched is not None and _field_matches(record.get("field"), touched):
                    return "grounding_field_updated@pos%d" % mutation.get("position", 0)
            return None
        return None  # create / none kill nothing

    def _record_state(self, record: dict, record_idx: int, upto_idx: int):
        """(status, reason) of one record after replaying journal
        entries after the record (record_idx < j < upto_idx): a
        mutation kills only records EARLIER than itself in journal
        order, and only within the query prefix (upto_idx)."""
        outcome = record.get("outcome")
        if outcome != "succeeded":
            if record.get("status") == "ambiguous":
                return "unknown", "ambiguous_evidence@pos%d" % record.get("position", 0)
            return "unknown", "outcome_%s@pos%d" % (outcome, record.get("position", 0))
        if record.get("status") == "invalidated":
            return "invalidated", "record_marked_invalidated@pos%d" % record.get("position", 0)
        if record.get("status") == "ambiguous":
            return "unknown", "ambiguous_evidence@pos%d" % record.get("position", 0)
        for j in range(record_idx + 1, upto_idx):
            other = self._journal[j]
            if other.get("_type") != "mutation" or not other.get("_succeeded"):
                continue
            reason = self._record_killed_by(record, other)
            if reason is not None:
                return "invalidated", reason
        return "active", "evidence@pos%d" % record.get("position", 0)

    def _resolve_key(self, registry, value, claim, field, upto_idx, visited):
        """Any-record semantics for one key: active if ANY matching
        record is active at upto_idx; else invalidated if any
        matching record was killed; else unknown. Returns
        (status, evidence_or_None, reason). Derived sources are
        resolved recursively (cycle-guarded) only for the
        latest active record."""
        key = (registry, str(value), claim, field)
        if key in visited:
            return "unknown", None, "derived_cycle"
        visited = visited | {key}
        matches = []  # (journal_idx, record)
        for idx, entry in enumerate(self._journal[:upto_idx]):
            if entry.get("_type") != "evidence":
                continue
            rec = entry
            if _record_registry(rec) != registry or rec.get("claim") != claim:
                continue
            if not (str(rec.get("value")) == str(value)
                    or _record_entity(rec) == str(value)):
                continue
            if claim == "field_value" and field is not None:
                if not (rec.get("field") == field
                        or _field_matches(rec.get("field"), [field])):
                    continue
            matches.append((idx, rec))
        if not matches:
            return "unknown", None, "no_evidence"
        # Latest active record (by journal order) wins for evidence
        # reporting; any active record makes the key active.
        active = []
        killed = []
        unknown_reasons = []
        for idx, rec in matches:
            st, reason = self._record_state(rec, idx, upto_idx)
            if st == "active":
                active.append((idx, rec, reason))
            elif st == "invalidated":
                killed.append((idx, rec, reason))
            else:
                unknown_reasons.append(reason)
        if active:
            idx, rec, reason = active[-1]
            sources = _derived_sources(rec)
            if sources:
                for src in sources:
                    s_st, _, s_reason = self._resolve_key(
                        src.get("registry"), src.get("value"),
                        src.get("claim"), src.get("field"),
                        upto_idx, visited)
                    if s_st == "invalidated":
                        return ("unknown", dict(rec),
                                "derived_source_invalidated(%s)" % s_reason)
                    if s_st != "active":
                        return ("unknown", dict(rec),
                                "derived_source_unknown(%s)" % s_reason)
            return "active", dict(rec), reason
        if killed:
            idx, rec, reason = killed[-1]
            return "invalidated", dict(rec), reason
        return "unknown", None, unknown_reasons[-1] if unknown_reasons else "no_evidence"

    # -- public query -----------------------------------------------------
    def query(self, registry, value, claim, position=None, field=None):
        """(status, latest_evidence_or_None, reason).

        status in ("active", "invalidated", "unknown"). position
        restricts the journal to entries at or before it (prefix
        query -- future entries are invisible). field is required
        to disambiguate field_value queries when more than one
        field is recorded for the entity (fail-closed otherwise).
        """
        if claim not in CLAIMS:
            raise ValueError("claim must be one of %r" % (CLAIMS,))
        upto = len(self._journal)
        if position is not None:
            upto = sum(1 for e in self._journal
                       if e.get("position", 0) <= position)
        if claim == "field_value" and field is None:
            fields = set()
            for entry in self._journal[:upto]:
                if entry.get("_type") != "evidence":
                    continue
                if (_record_registry(entry) == registry
                        and entry.get("claim") == "field_value"
                        and (str(entry.get("value")) == str(value)
                             or _record_entity(entry) == str(value))):
                    fields.add(entry.get("field"))
            if len(fields) != 1:
                return ("unknown", None,
                        "field_value_query_requires_field")
            field = next(iter(fields))
        return self._resolve_key(registry, value, claim, field, upto, frozenset())

    def explain(self, registry, value, claim, position=None, field=None) -> dict:
        status, evidence, reason = self.query(registry, value, claim,
                                               position=position, field=field)
        return {"status": status, "evidence": evidence, "reason": reason}

    # -- R5: field-value queries + snapshot staleness ------------------
    def query_field_value(self, registry, entity, field, position=None):
        """(status, observed_value_or_None, reason) for one entity field.

        Strict entity linkage: only a field_value record whose
        counterpart id equals the entity counts as field evidence.
        A record that merely matches by value (e.g. an adapter
        flattened existence record, or a mislabeled field_value
        record with no counterpart) is IGNORED -- it cannot prove
        what this entity's field holds -- so the result is
        "unknown" with reason "field_record_not_entity_linked"
        instead of a guessed value. Derived sources are resolved
        by the underlying query (a dead derived source yields
        "unknown" with a derived_source_* reason).
        """
        status, evidence, reason = self.query(
            registry, entity, "field_value", position=position, field=field)
        if status == "active":
            cp = evidence.get("counterpart") if isinstance(evidence, dict) else None
            if isinstance(cp, dict) and str(cp.get("id")) == str(entity):
                return ("active", evidence.get("value"), reason)
            return ("unknown", None, "field_record_not_entity_linked")
        if status == "invalidated":
            return ("invalidated", None, reason)
        return ("unknown", None, reason)

    def field_invalidated_since(self, registry, entity, field,
                                since_position, position=None):
        """(True, reason) if any succeeded mutation with
        since_position < pos <= position touches this entity field
        (same linkage as _record_killed_by for a field_value
        record: delete kills any field, cancel kills only status
        fields, update kills only touched fields or all fields when
        the touched set is unknown). Used to detect stale snapshots:
        a snapshot observed at since_position is unusable for this
        field when this returns True. Positions are per-call audit
        labels; a mutation at exactly since_position is treated as
        concurrent (not invalidating) -- callers pass the
        observation's own position.
        """
        upto = None if position is None else position
        probe = {"registry": registry, "value": str(entity),
                 "field": field, "claim": "field_value",
                 "counterpart": {"id": str(entity)}}
        for entry in self._journal:
            if entry.get("_type") != "mutation" or not entry.get("_succeeded"):
                continue
            pos = entry.get("position", 0)
            if pos <= since_position:
                continue
            if upto is not None and pos > upto:
                continue
            reason = self._record_killed_by(probe, entry)
            if reason is not None:
                return (True, reason)
        return (False, None)

    def history(self):
        """Journal copies for audit (evidence + mutations, in
        journal order). Internal keys are stripped except _type /
        _succeeded / _ignored_reason, which are audit metadata."""
        out = []
        for entry in self._journal:
            cp = {k: v for k, v in entry.items() if not k.startswith("_")
                  or k in ("_type", "_succeeded", "_ignored_reason")}
            out.append(cp)
        return out


# ---------------------------------------------------------------------------
# R5: producer -> claim -> mutation -> consumer table
#
# Read from the simulator implementation (zaic_tools/apps/*.py).
# "Producer" = the call whose result establishes the claim.
# "Killed by" = the mutation kinds that invalidate it (ledger
# semantics: delete kills all claims; status-only cancel kills
# eligibility + the status field_value only; update kills only
# touched fields). Failed / noop / schema-rejected mutations kill
# NOTHING (the ledger ignores them). "Consumer" = the tool whose
# eligibility check reads the claim (see CONSUMER_CONTRACTS).
# ---------------------------------------------------------------------------

PRODUCER_CLAIM_CONSUMER_TABLE = [
    # Existence: established by a create result (new id) or a read
    # result that lists the entity (item present). Killed ONLY by
    # delete. Every existence-gated consumer reads it.
    {"producer": "create-result (App.create / book / place_order / "
                 "reserve / schedule / enroll-adjacent creates)",
     "claim": "existence",
     "killed_by": "delete only",
     "consumers": "all existence-gated consumers (see CONSUMER_CONTRACTS)",
     "evidence": "base.py App.create / App.delete; every app's "
                 "find() -> None gives noop, never a phantom entity"},
    # Field values: established by a create/read/update result's
    # item fields, recorded as field_value records (counterpart
    # convention). Killed by an update touching the field, or by
    # delete (all fields). A status-only cancel kills ONLY the
    # status field_value, never other fields.
    {"producer": "read-result / create-result / patch-result item fields",
     "claim": "field_value",
     "killed_by": "update touching the field; delete (all fields); "
                  "cancel (status field only)",
     "consumers": "flights.check_in (checked_in), bill_payment.pay "
                  "(paid), learning.enroll (enrolled), bike_rental."
                  "reserve (available), package_tracking."
                  "reschedule_delivery (status), smart_home.*_set "
                  "(type), music.add_to_playlist (track_ids)",
     "evidence": "flights.py check_in; bill_payment.py pay; learning.py "
                 "enroll; bike_rental.py reserve; package_tracking.py "
                 "reschedule_delivery; smart_home.py light_set/fan_set/"
                 "climate_set (require=); music.py add_to_playlist"},
    # Eligibility (liveness): established by a create result (status
    # confirmed/booked/scheduled/placed, enabled True) or a read
    # result whose status is not cancelled. Killed by delete,
    # status-only cancel, or a terminal update (status -> cancelled,
    # enabled -> False). NOTE: cancel-type consumers do NOT require
    # liveness -- cancelling is the action that ENDS liveness, so
    # they require existence only (a patch-cancel even succeeds on
    # an already-cancelled entity: App.patch has no guard).
    {"producer": "create-result (live by construction) / read-result "
                 "(status != cancelled)",
     "claim": "eligibility",
     "killed_by": "delete; status-only cancel; terminal update "
                  "(status -> cancelled, enabled -> False)",
     "consumers": "video_meeting.join, subscriptions.cancel, "
                  "flights.check_in (via not_cancelled leg)",
     "evidence": "video_meeting.py join (noop if cancelled); "
                 "subscriptions.py cancel (noop if cancelled); "
                 "flights.py check_in (noop if cancelled); base.py "
                 "App.patch (no already-cancelled guard -- patch-"
                 "cancels succeed on cancelled entities)"},
    # Derived claims: established by copying a value out of a source
    # record (code from lock+valid_until, meeting link from id+start,
    # paid_with from source). Killed when ANY dependency source dies
    # at the proposal position (ledger walks derived_from).
    {"producer": "write-result copying source fields (door_lock code, "
                 "video_meeting link, bill paid_with)",
     "claim": "field_value (derived_from=[sources])",
     "killed_by": "death of any dependency source (delete / update "
                  "touching the source field / cancel of a status source)",
     "consumers": "prover expiry (validity gating); eligibility "
                  "field checks on derived values",
     "evidence": "door_lock.py grant_guest_code (code is a pure function "
                 "of lock_id+valid_until); video_meeting.py create "
                 "(link derived from id+start); ledger derived "
                 "resolution in _resolve_key"},
    # Foreign-key existence: established by an existence record in
    # the REFERENCED registry. Killed by delete of the referenced
    # entity. The referencing call never validates the FK itself --
    # the simulator noops on a missing FK.
    {"producer": "existence record in the referenced registry "
                 "(read/create result there)",
     "claim": "existence (foreign registry)",
     "killed_by": "delete of the referenced entity",
     "consumers": "flights.book (flights.flights), home_automation."
                  "create_rule (smart_home.devices), medication."
                  "log_taken (medication.schedules), learning."
                  "schedule_lesson / log_progress (learning.courses), "
                  "food_delivery.place_order (food_delivery.restaurants "
                  "+ menu items), music.add_to_playlist (music.tracks)",
     "evidence": "flights.py book (noop if flight missing); "
                 "home_automation.py create_rule (device must exist "
                 "when smart_home installed); medication.py log_taken; "
                 "learning.py schedule_lesson/log_progress; "
                 "food_delivery.py place_order (noop if restaurant or "
                 "menu item missing); music.py add_to_playlist"},
]


def field_value_record(registry, entity, field, observed, position,
                       producer, source="read_result", outcome="succeeded",
                       status="active", reason="field_observation"):
    """Build a canonical field_value record (the counterpart
    convention). value = the observed field value (NOT the entity
    id); counterpart.id = the entity. Records built any other way
    do not satisfy field checks (see query_field_value)."""
    return {"kind": "entity", "value": observed, "registry": registry,
            "claim": "field_value", "field": field,
            "outcome": outcome, "counterpart": {"id": str(entity)},
            "position": position, "producer": producer,
            "source": source, "status": status, "reason": reason}


# ---------------------------------------------------------------------------
# R5: eligibility API
#
# check_eligibility(ledger, consumer, entity_id, ...) -> (status,
# reason) with status in exactly {"eligible", "ineligible",
# "unknown"}. Unknown is never presented as eligible or ineligible:
# it always carries a reason naming what is missing. The function
# never raises for an unlisted consumer (returns unknown +
# "consumer_not_supported:<name>") and never invents a rule for an
# unclear semantic -- those consumers are listed in
# UNSUPPORTED_CONSUMERS with their boundary.
#
# Snapshot contract: snapshot is the entity's last observed full
# item dict (from a read/create result); snapshot_position is that
# observation's position. A fresh snapshot value beats an older
# ledger record; a live ledger record beats snapshot ABSENCE (the
# snapshot may be partial); a stale snapshot (a succeeded mutation
# touched the field after snapshot_position) falls through to the
# ledger, else unknown. A snapshot without a position is
# treated as observed at position -1 (any touching mutation in the
# prefix makes it unusable). Simulator defaults are mirrored
# exactly: .get(field) absent counts as falsy; .get("available",
# True) absent counts as True; require={type} fails on absent.
# ---------------------------------------------------------------------------

import unicodedata as _unicodedata


def _fold_text(s):
    """Lower + strip diacritics (mirrors zaic_tools.utils._fold for
    member-name comparison in household_chores.assign)."""
    if s is None:
        return ""
    nfkd = _unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not _unicodedata.combining(c)).lower()


def _ledger_existence(ledger, registry, entity, position):
    """(status, reason): ledger existence for one entity."""
    st, _, reason = ledger.query(registry, entity, "existence",
                                 position=position)
    if st == "active":
        return ("active", "entity_exists")
    if st == "invalidated":
        return ("invalidated", "entity_deleted:" + reason)
    return ("unknown", "no_existence_evidence")


def _resolve_field(ledger, registry, entity, field, position,
                   snapshot, snapshot_position):
    """("known", value, basis) | ("absent", None, basis) |
    ("unknown", None, reason) for one entity field.

    Precedence: a fresh snapshot value > a live ledger record >
    snapshot absence > unknown. A snapshot is fresh iff no
    succeeded mutation touched the field after snapshot_position.
    Snapshot absence is WEAK evidence (the snapshot may be
    partial), so a live ledger record beats it; but a fresh
    snapshot value beats an older ledger record (the caller
    observed it directly). A stale snapshot falls through to the
    ledger (a re-read after the mutation may have recorded the new
    value), and only if the ledger has nothing does the answer
    become unknown with the staleness named.
    """
    stale_reason = None
    if snapshot is not None:
        since = -1 if snapshot_position is None else snapshot_position
        stale, sreason = ledger.field_invalidated_since(
            registry, entity, field, since, position)
        if not stale:
            if field in snapshot:
                return ("known", snapshot[field], "snapshot")
            st, observed, reason = ledger.query_field_value(
                registry, entity, field, position)
            if st == "active":
                return ("known", observed, "ledger")
            return ("absent", None, "snapshot_absent")
        stale_reason = sreason
    st, observed, reason = ledger.query_field_value(
        registry, entity, field, position)
    if st == "active":
        return ("known", observed, "ledger")
    if st == "invalidated":
        return ("unknown", None, "field_invalidated:" + reason)
    if stale_reason is not None:
        return ("unknown", None,
                "snapshot_stale:" + stale_reason
                + "; no_current_field_evidence")
    return ("unknown", None, reason)


def _not_cancelled(ledger, registry, entity, position,
                   snapshot, snapshot_position):
    """(True, reason) not cancelled | (False, reason) cancelled |
    (None, reason) unknown. Generic eligibility is checked first
    (cancel kills it); the status field is the fallback. A status
    field killed by a cancel mutation is itself evidence of
    cancellation (kill reason "status_cancelled@posN").
    """
    st, _, reason = ledger.query(registry, entity, "eligibility",
                                 position=position)
    if st == "invalidated":
        return (False, "entity_cancelled_or_terminal:" + reason)
    if st == "active":
        return (True, "eligibility_active")
    fr = _resolve_field(ledger, registry, entity, "status", position,
                        snapshot, snapshot_position)
    if fr[0] == "known":
        if fr[1] == "cancelled":
            return (False, "status_cancelled")
        return (True, "status_not_cancelled")
    if fr[0] == "absent":
        return (True, "status_absent_not_cancelled")
    if fr[2] and "status_cancelled@" in fr[2]:
        return (False, "status_cancelled_via_field_invalidation")
    return (None, fr[2])


def _existence_gate(ledger, registry, entity, position):
    """(ok, status, reason) for the existence precondition shared by
    all handlers: ok=True -> proceed; ok=False -> ineligible;
    ok=None -> unknown."""
    st, reason = _ledger_existence(ledger, registry, entity, position)
    if st == "active":
        return (True, "eligible", "entity_exists")
    if st == "invalidated":
        return (False, "ineligible", "entity_deleted")
    return (None, "unknown", reason)


def _h_existence(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, status, reason = _existence_gate(ledger, c["registry"], entity,
                                         position)
    return (status, reason)


def _h_not_cancelled(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    nc, reason = _not_cancelled(ledger, c["registry"], entity, position,
                                snapshot, spos)
    if nc is True:
        return ("eligible", "entity_exists_not_cancelled")
    if nc is False:
        return ("ineligible", reason)
    return ("unknown", reason)


def _h_field_not_true(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    fr = _resolve_field(ledger, c["registry"], entity, c["field"],
                        position, snapshot, spos)
    if fr[0] == "known":
        if bool(fr[1]):
            return ("ineligible", "field_true:" + c["field"])
        return ("eligible", "field_not_true:" + c["field"])
    if fr[0] == "absent":
        return ("eligible", "field_absent_default_falsy:" + c["field"])
    return ("unknown", fr[2])


def _h_field_default_true(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    fr = _resolve_field(ledger, c["registry"], entity, c["field"],
                        position, snapshot, spos)
    if fr[0] == "known":
        if fr[1] is False:
            return ("ineligible", "field_false:" + c["field"])
        return ("eligible", "field_not_false:" + c["field"])
    if fr[0] == "absent":
        return ("eligible", "field_absent_default_true:" + c["field"])
    return ("unknown", fr[2])


def _h_field_not_value(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    fr = _resolve_field(ledger, c["registry"], entity, c["field"],
                        position, snapshot, spos)
    if fr[0] == "known":
        if fr[1] == c["value"]:
            return ("ineligible",
                    "field_equals:%s=%s" % (c["field"], c["value"]))
        return ("eligible", "field_not_value:%s" % c["field"])
    if fr[0] == "absent":
        return ("eligible", "field_absent_not_value:%s" % c["field"])
    return ("unknown", fr[2])


def _h_type_is(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    fr = _resolve_field(ledger, c["registry"], entity, "type",
                        position, snapshot, spos)
    if fr[0] == "known":
        if fr[1] == c["type"]:
            return ("eligible", "type_matches:" + c["type"])
        return ("ineligible", "type_mismatch:%s" % (fr[1],))
    if fr[0] == "absent":
        # Simulator require={type} fails on absent (None != type).
        return ("ineligible", "type_absent_not_" + c["type"])
    return ("unknown", fr[2])


def _h_fk(ledger, c, entity, position, snapshot, spos, args, ctx):
    st, reason = _ledger_existence(ledger, c["registry"], entity, position)
    if st == "active":
        return ("eligible", "fk_exists:" + c["registry"])
    if st == "invalidated":
        return ("ineligible", "fk_deleted:" + c["registry"])
    return ("unknown", "fk_existence_unknown:" + c["registry"])


def _h_bill_pay(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    fr = _resolve_field(ledger, c["registry"], entity, "paid",
                        position, snapshot, spos)
    if fr[0] == "known" and bool(fr[1]):
        return ("ineligible", "field_true:paid")
    if fr[0] == "unknown":
        return ("unknown", fr[2])
    # Bill leg passed (unpaid, or paid absent which .get() reads
    # falsy). The ewallet leg is a second entity + a numeric guard
    # and is NOT evaluated here: paying from the wallet needs the
    # wallet installed and balance >= amount (bill_payment.py pay).
    if (args or {}).get("source") == "ewallet":
        return ("unknown", "ewallet_balance_leg_unknown")
    return ("eligible", "bill_unpaid")


def _h_grant_guest_code(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    # State leg only. valid_until tz-aware ISO is ARGUMENT
    # validation (door_lock.py grant_guest_code), not state
    # eligibility: the reason always names the unchecked leg so an
    # "eligible" here is never misread as a full simulator pass.
    return ("eligible",
            "lock_exists; valid_until_not_checked(argument_validation)")


def _h_library_reserve(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    if not isinstance(ctx, dict) or "reservations" not in ctx:
        return ("unknown", "active_reservation_unknown")
    for r in ctx.get("reservations") or []:
        if isinstance(r, dict) and r.get("book_id") == entity \
                and r.get("status") in ("ready", "waiting"):
            return ("ineligible", "book_already_reserved")
    return ("eligible",
            "book_exists_no_active_reservation(context_basis)")


def _h_chores_assign(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    assignee = (args or {}).get("assignee")
    if assignee is None:
        return ("unknown", "assignee_missing")
    if not isinstance(ctx, dict) or "members" not in ctx:
        return ("unknown", "assignee_membership_unknown")
    want = _fold_text(assignee)
    for m in ctx.get("members") or []:
        if _fold_text(m) == want:
            return ("eligible",
                    "chore_exists_assignee_member(context_basis)")
    return ("ineligible", "assignee_not_member")


def _h_add_to_playlist(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    track_id = (args or {}).get("track_id")
    if track_id is None:
        return ("unknown", "track_id_missing")
    st, _ = _ledger_existence(ledger, "music.tracks", track_id, position)
    if st == "invalidated":
        return ("ineligible", "track_deleted")
    if st != "active":
        return ("unknown", "track_existence_unknown")
    fr = _resolve_field(ledger, c["registry"], entity, "track_ids",
                        position, snapshot, spos)
    if fr[0] == "known":
        ids = fr[1] if isinstance(fr[1], list) else []
        if track_id in ids:
            return ("ineligible", "track_already_in_playlist")
        return ("eligible", "track_not_in_playlist")
    if fr[0] == "absent":
        # Simulator setdefault("track_ids", []) reads absent as empty.
        return ("eligible", "track_ids_absent_empty")
    return ("unknown", fr[2])


def _h_place_order(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    items = (args or {}).get("items")
    if not items:
        return ("ineligible", "empty_order")
    if not isinstance(snapshot, dict) or "menu" not in snapshot:
        return ("unknown", "menu_unknown")
    menu = {m.get("id") for m in snapshot.get("menu") or []
            if isinstance(m, dict)}
    for it in items:
        iid = it.get("item_id") if isinstance(it, dict) else None
        if iid not in menu:
            return ("ineligible", "menu_item_missing:%s" % (iid,))
    return ("eligible",
            "restaurant_exists_all_items_in_menu(snapshot_basis)")


def _h_not_cancelled_checked_in(ledger, c, entity, position, snapshot, spos, args, ctx):
    ok, _, _ = _existence_gate(ledger, c["registry"], entity, position)
    if ok is not True:
        return ("ineligible", "entity_deleted") if ok is False \
            else ("unknown", "no_existence_evidence")
    nc, reason = _not_cancelled(ledger, c["registry"], entity, position,
                                snapshot, spos)
    if nc is False:
        return ("ineligible", reason)
    if nc is None:
        return ("unknown", reason)
    fr = _resolve_field(ledger, c["registry"], entity, "checked_in",
                        position, snapshot, spos)
    if fr[0] == "known" and bool(fr[1]):
        return ("ineligible", "field_true:checked_in")
    if fr[0] == "unknown":
        return ("unknown", fr[2])
    return ("eligible", "booking_live_not_checked_in")


_HANDLER_BY_NAME = {
    "existence": _h_existence,
    "not_cancelled": _h_not_cancelled,
    "field_not_true": _h_field_not_true,
    "field_default_true": _h_field_default_true,
    "field_not_value": _h_field_not_value,
    "type_is": _h_type_is,
    "fk": _h_fk,
    "bill_pay": _h_bill_pay,
    "grant_guest_code": _h_grant_guest_code,
    "library_reserve": _h_library_reserve,
    "chores_assign": _h_chores_assign,
    "add_to_playlist": _h_add_to_playlist,
    "place_order": _h_place_order,
    "not_cancelled_checked_in": _h_not_cancelled_checked_in,
}


def _C(registry, id_arg, handler, **kw):
    d = {"registry": registry, "id_arg": id_arg, "handler": handler}
    d.update(kw)
    return d


# Supported consumers: contract verified against the simulator
# implementation (file:line in the "evidence" column). "handler"
# selects the precondition evaluation; "id_arg" is the argument
# whose value is passed as entity_id.
CONSUMER_CONTRACTS = {
    # Existence-only: App.patch / App.delete with no guard beyond
    # the find() (missing -> noop). A patch-cancel even succeeds on
    # an already-cancelled entity (patch has no guard) -- so these
    # do NOT require liveness, only existence.
    "flights.cancel": _C("flights.bookings", "booking_id", "existence",
                         evidence="flights.py cancel: patch status=cancelled, no guard"),
    "ride_hailing.cancel": _C("ride_hailing.rides", "ride_id", "existence",
                              evidence="ride_hailing.py:41-42 patch, no guard"),
    "food_delivery.cancel_order": _C("food_delivery.orders", "order_id", "existence",
                                     evidence="food_delivery.py:46-47 patch, no guard"),
    "calendar.cancel_event": _C("calendar.events", "event_id", "existence",
                                evidence="calendar.py:30-31 patch, no guard"),
    "tasks.complete": _C("tasks.tasks", "task_id", "existence",
                         evidence="tasks.py:20-21 patch done=True, idempotent"),
    "reminders.complete": _C("reminders.reminders", "reminder_id", "existence",
                             evidence="reminders.py:19-20 patch done=True"),
    "reminders.delete": _C("reminders.reminders", "reminder_id", "existence",
                           evidence="reminders.py:23-24 App.delete"),
    "alarm.delete": _C("alarm.alarms", "alarm_id", "existence",
                       evidence="alarm.py:23-24 App.delete"),
    "alarm.update": _C("alarm.alarms", "alarm_id", "existence",
                       evidence="alarm.py:19-20 patch, no guard"),
    "shopping_list.remove": _C("shopping_list.items", "item_id", "existence",
                               evidence="shopping_list.py:24-25 App.delete"),
    "shopping_list.check": _C("shopping_list.items", "item_id", "existence",
                              evidence="shopping_list.py:28-29 patch checked=True"),
    "contacts.update": _C("contacts.contacts", "contact_id", "existence",
                          evidence="contacts.py:20-21 patch phone/email"),
    "calendar.update_event": _C("calendar.events", "event_id", "existence",
                                evidence="calendar.py:26-27 patch, no guard"),
    "email.archive": _C("email.emails", "email_id", "existence",
                        evidence="email.py:72-75 delete branch or patch folder, both existence-gated"),
    "notes.append": _C("notes.notes", "note_id", "existence",
                       evidence="notes.py:19-23 noop if note missing, else append"),
    "chat_ott.send_message": _C("chat_ott.chats", "chat_id", "existence",
                                evidence="chat_ott.py:22-28 noop if chat missing"),
    "chat_ott.send_location": _C("chat_ott.chats", "chat_id", "existence",
                                 evidence="chat_ott.py:31-37 noop if chat missing"),
    "home_security.acknowledge_alert": _C("home_security.alerts", "alert_id", "existence",
                                          evidence="home_security.py:41-42 patch acknowledged=True"),
    "door_lock.set_lock": _C("door_lock.locks", "lock_id", "existence",
                             evidence="door_lock.py:18-21 noop if lock missing, else patch"),
    "appliances.stop": _C("appliances.appliances", "appliance_id", "existence",
                          evidence="appliances.py:32-36 noop if missing, else patch to idle"),
    "medication.remove": _C("medication.schedules", "schedule_id", "existence",
                            evidence="medication.py:28-29 App.delete"),
    # Not-cancelled: explicit cancelled guard (join on joined
    # succeeds; cancel on cancelled noops only for subscriptions --
    # patch-cancels above have no such guard).
    "video_meeting.join": _C("video_meeting.meetings", "meeting_id", "not_cancelled",
                             evidence="video_meeting.py join: noop if missing/cancelled; joined->joined succeeds"),
    "subscriptions.cancel": _C("subscriptions.subscriptions", "subscription_id", "not_cancelled",
                               evidence="subscriptions.py:15-20 noop if missing/cancelled"),
    # Field-not-true: simulator .get(field) truthy -> noop; absent
    # counts as falsy.
    "flights.check_in": _C("flights.bookings", "booking_id", "not_cancelled_checked_in",
                           evidence="flights.py check_in: noop if missing/cancelled/checked_in; sets checked_in=True"),
    "bill_payment.pay": _C("bill_payment.bills", "bill_id", "bill_pay",
                           evidence="bill_payment.py:16-33 noop if missing/paid; ewallet leg separate"),
    "learning.enroll": _C("learning.courses", "course_id", "field_not_true",
                          field="enrolled",
                          evidence="learning.py:15-21 noop if missing/enrolled"),
    # Field-default-true: .get("available", True) -- absent counts
    # as available; only a known False blocks.
    "bike_rental.reserve": _C("bike_rental.bikes", "bike_id", "field_default_true",
                              field="available",
                              evidence="bike_rental.py:27-33 noop if missing/not available; sets available=False"),
    # Field-not-value: status == delivered blocks, anything else
    # (including absent) passes.
    "package_tracking.reschedule_delivery": _C("package_tracking.shipments", "tracking_id", "field_not_value",
                                               field="status", value="delivered",
                                               evidence="package_tracking.py:29-35 noop if missing/delivered"),
    # Type-gated patch (require=): absent type FAILS the require
    # (None != type), unlike the falsy-default guards above.
    "smart_home.light_set": _C("smart_home.devices", "device_id", "type_is",
                               type="light",
                               evidence="smart_home.py:18-19 patch require type=light"),
    "smart_home.fan_set": _C("smart_home.devices", "device_id", "type_is",
                             type="fan",
                             evidence="smart_home.py:22-23 patch require type=fan"),
    "smart_home.climate_set": _C("smart_home.devices", "device_id", "type_is",
                                 type="climate",
                                 evidence="smart_home.py:26-27 patch require type=climate"),
    "smart_home.switch_set": _C("smart_home.devices", "device_id", "existence",
                                evidence="smart_home.py:30-31 patch, no type require"),
    # Foreign-key existence: the call noops when the referenced
    # entity is missing.
    "flights.book": _C("flights.flights", "flight_id", "fk",
                       evidence="flights.py book: noop if flight missing"),
    "home_automation.create_rule": _C("smart_home.devices", "device_id", "fk",
                                      evidence="home_automation.py:15-20 device must exist when smart_home installed"),
    "medication.log_taken": _C("medication.schedules", "schedule_id", "fk",
                               evidence="medication.py:19-23 noop if schedule missing"),
    "learning.schedule_lesson": _C("learning.courses", "course_id", "fk",
                                   evidence="learning.py:25-28 noop if course missing"),
    "learning.log_progress": _C("learning.courses", "course_id", "fk",
                                evidence="learning.py:32-36 noop if course missing"),
    "door_lock.grant_guest_code": _C("door_lock.locks", "lock_id", "grant_guest_code",
                                     evidence="door_lock.py:24-34 noop if lock missing; valid_until is argument validation"),
    # Context-gated: a second evidence source the caller supplies
    # (reservations list, members list) because the guard reads
    # state beyond the entity itself.
    "library.reserve": _C("library.books", "book_id", "library_reserve",
                          evidence="library.py:15-26 noop if book missing or a ready/waiting reservation exists"),
    "household_chores.assign": _C("household_chores.chores", "chore_id", "chores_assign",
                                  evidence="household_chores.py:16-23 noop if chore missing or assignee not a member"),
    "music.add_to_playlist": _C("music.playlists", "playlist_id", "add_to_playlist",
                                evidence="music.py:46-54 noop if track/playlist missing or track already present"),
    "food_delivery.place_order": _C("food_delivery.restaurants", "restaurant_id", "place_order",
                                    evidence="food_delivery.py:26-42 noop if restaurant/menu item missing or no lines"),
}


# Explicitly unsupported consumers: the contract is NOT clear enough
# for a sound eligibility decision, or the guard needs machinery
# this round does not build (numeric comparison, multi-entity
# atomicity, global state). check_eligibility returns unknown for
# all of these (via the not-in-CONTRACTS path) -- never eligible,
# never ineligible, always with consumer_not_supported + the
# boundary below. This list is part of the coverage report.
UNSUPPORTED_CONSUMERS = {
    # Numeric balance guards + multi-entity: amount vs balance
    # comparison is arithmetic on ledger values, out of scope.
    "banking.transfer": "numeric guard (accounts exist + balance sufficient) + beneficiary leg; no arithmetic on ledger values this round",
    "ewallet.transfer": "numeric guard (balance sufficient); phone->contact completion is not validation",
    "ewallet.topup_mobile": "numeric guard (balance sufficient)",
    "ewallet.pay_qr": "numeric guard (balance sufficient)",
    "loyalty.redeem": "numeric guard (points sufficient) + program leg",
    "banking.open_savings": "numeric guard (account exists + balance sufficient)",
    # Multi-entity / roster guards.
    "video_meeting.create": "attendee roster guard (every attendee id in contacts, skipped when contacts not installed); multi-entity + installation-conditional",
    "smart_home.scene_run": "atomic multi-entity guard (scene exists + every action device exists); one bad device noops everything",
    "tv.record": "program FK + already-scheduled NEGATIVE over recordings registry; negative leg needs schedule evidence",
    "appliances.start_cycle": "cycle-membership + running/scheduled state-machine guard; needs full appliance snapshot evaluation",
    # Global state: no entity id to key the ledger on.
    "music.play": "global now_playing, no entity id",
    "music.control": "global now_playing/volume, no entity id",
    "tv.tune": "global power/channel, no entity id",
    "tv.control": "global power/volume/muted, no entity id",
    "robot_vacuum.start": "global status/current_job + battery guard, no entity id",
    "robot_vacuum.stop": "global status, no entity id",
    "home_energy.set_alert": "global alert_threshold_kwh, no entity id",
    "home_security.arm": "global mode field, no entity id",
    "fitness.set_goal": "global goal_steps, no entity id",
    "podcast_radio.play": "global now_playing + queue mutation, no entity id",
    "podcast_radio.queue": "global queue membership, no entity id",
    "podcast_radio.subscribe": "global subscriptions membership, no entity id",
    # Creates / reads / meta with no entity precondition: not
    # applicable to an entity eligibility API (nothing to check).
    "ride_hailing.book": "no entity guard (creates a ride unconditionally)",
    "calendar.create_event": "no entity guard (creates an event)",
    "tasks.add": "no entity guard (creates a task)",
    "reminders.create": "no entity guard (creates a reminder)",
    "alarm.create": "no entity guard (creates an alarm)",
    "notes.create": "no entity guard (creates a note)",
    "shopping_list.add": "no entity guard (creates an item)",
    "email.send": "no entity guard (creates a sent mail)",
    "email.create_draft": "no entity guard (creates a draft)",
    "email.reply": "no entity guard (creates a sent mail + marks original)",
    "sms.send": "no entity guard (never validates contacts; contact_ref completion only)",
    "phone.call": "no entity guard (never validates contacts; contact_ref completion only)",
    "chat_ott.call": "no entity guard (creates a call record)",
    "fitness.log_workout": "no entity guard (creates a workout)",
    "bill_payment.schedule_autopay": "no entity guard (upsert by type)",
    "maps.save_place": "no entity guard (upsert by place_id)",
    "news.save": "no entity guard (upsert by article_id)",
    "package_tracking.schedule_pickup": "no entity guard (creates a pickup)",
    "medication.add": "no entity guard (creates a schedule)",
    "sys.ask_missing_info": "meta tool, touches no state",
}


def check_eligibility(ledger, consumer, entity_id, position=None,
                      snapshot=None, snapshot_position=None,
                      args=None, context=None):
    """(status, reason) for one consumer call's entity precondition.

    status in {"eligible", "ineligible", "unknown"} -- exactly.
    "unknown" always carries a reason naming what is missing and is
    never to be read as eligible or ineligible. Unlisted consumers
    return ("unknown", "consumer_not_supported:<name>"); a missing
    entity_id returns ("unknown", "entity_id_missing"). Failed /
    noop / schema-rejected mutations never revoke evidence (the
    ledger ignores them), so eligibility computed from the ledger
    is unaffected by them. A future mutation (position > query
    position) never affects the prefix before it (the ledger's
    position-bounded queries). A re-read appends NEW evidence; it
    never rewrites history (killed records stay killed; a fresh
    record for the same key makes the key active again).
    """
    contract = CONSUMER_CONTRACTS.get(consumer)
    if contract is None:
        return ("unknown", "consumer_not_supported:" + str(consumer))
    if entity_id is None or (isinstance(entity_id, str)
                             and not entity_id):
        return ("unknown", "entity_id_missing")
    handler = _HANDLER_BY_NAME[contract["handler"]]
    return handler(ledger, contract, str(entity_id), position,
                   snapshot, snapshot_position, args, context)


# ---------------------------------------------------------------------------
# R5: prover validity adapter
# ---------------------------------------------------------------------------

def _values_equal(a, b):
    """Observed-value equality for validity checks: exact equality,
    numeric equality (bools excluded -- True != 1 here), or ISO
    datetime equality (same instant, format-insensitive). Anything
    else is unequal (a changed value is stale, not unknown).
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    if isinstance(a, str) and isinstance(b, str):
        try:
            from datetime import datetime as _dt
            da = _dt.fromisoformat(a.replace("Z", "+00:00"))
            db = _dt.fromisoformat(b.replace("Z", "+00:00"))
            return da == db
        except ValueError:
            return False
    return False


def make_prover_validity(ledger, position, registry_for_tool=None):
    """Adapt a ledger + proposal position into the prover's
    ``validity`` callable: check(obs_tool, field, value, entity) ->
    (status, reason) with status in {"active", "invalidated",
    "unknown"}.

    Semantics: an observation proves only if an entity-linked
    field_value record (counterpart convention) for (registry,
    entity, field) is alive at the proposal position AND its
    observed value equals the observation's value. A live record
    with a DIFFERENT value means the field changed and was
    re-observed -> "invalidated" (stale, not unknown). No record
    -> "unknown" (the adapter never recorded this observation as
    entity-linked field evidence). An entity-less observation can
    never be linked -> "unknown" (it never proves under gating;
    the adapter must attach entity ids where possible). A tool
    with no registry mapping -> "unknown" (registry_for_tool
    covers read tools; MUTATION_TABLE covers write tools).
    """
    def check(obs_tool, field, value, entity):
        if field is None:
            return ("unknown", "field_unknown")
        registry = None
        if registry_for_tool is not None:
            registry = registry_for_tool(obs_tool)
        if registry is None:
            entry = MUTATION_TABLE.get(obs_tool or "")
            registry = entry["registry"] if entry else None
        if registry is None:
            return ("unknown", "registry_unknown_for_tool:%s" % (obs_tool,))
        if entity is None:
            return ("unknown", "entity_unknown_for_observation")
        st, observed, reason = ledger.query_field_value(
            registry, entity, field, position)
        if st == "active":
            if _values_equal(observed, value):
                return ("active", reason)
            return ("invalidated", "field_value_changed")
        if st == "invalidated":
            return ("invalidated", reason)
        return ("unknown", reason)

    return check
