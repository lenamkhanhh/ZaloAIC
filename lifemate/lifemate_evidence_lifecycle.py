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
