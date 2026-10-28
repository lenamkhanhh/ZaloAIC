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
- Gate 2, read_before_write (fix round 2: STRUCTURED evidence;
  THREAD 1 round: REGISTRY-TYPED evidence): a write referencing an
  existing entity must have prior evidence the entity exists: a
  roster entry, or a structured result entry (field, value[, path])
  from a SUCCEEDED prior call whose REGISTRY matches the registry
  the consumer slot needs (PRODUCER_REGISTRY vs CONSUMER_REGISTRY
  below, both grounded in the tool catalog's x-ref fields and the
  zaic_tools implementations, never in id-string prefixes or gold
  pass rates). A flat global string set is NOT evidence; a
  free-text scalar that merely equals an id proves nothing; a
  foreign-key field inside a returned record proves nothing about
  the referenced registry (only the record's own primary id proves
  its own registry, plus the two documented field-scoped exceptions:
  food_delivery.merchants via merchant_id, package_tracking
  shipments via id OR tracking_id); and a write that only echoes
  its own argument proves nothing. Rules: contacts come only from
  rosters or contacts-app results (id/contact_id fields, registry
  contacts.contacts); other *_ids come from id-typed fields whose
  producer registry EQUALS the consumer slot's registry; READS
  verify by lookup (a succeeded read's id-field establishes even
  when it equals the read's input -- get_ride finds or noops);
  WRITEs establish only non-echo ids (a create's new id counts; an
  sms/phone echo does not). Failed, empty and noop reads establish
  nothing. ALL references of a call are checked, not just the first.
  INTERFACE CHANGE (flagged, see PriorCall): result entries may
  now carry a third element, the dotted key path from the result
  root to the enclosing record (e.g. "devices", "programs.rewards");
  a legacy 2-tuple is resolved only when its (tool, field) maps to
  exactly ONE registry -- an ambiguous legacy entry (smart_home.
  get_status "id" = devices OR scenes; music.list_tracks "id" =
  tracks OR playlists; podcast_radio.search "id" = shows OR
  episodes OR stations; loyalty.get_points "id" = programs OR
  nested rewards) establishes NOTHING. Known conservative residual:
  a patch-verified write (cancel/update returning the full record
  of an id it looked up) is still treated as echo when the id
  equals its argument -- see the gate docstring.
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
    "PRODUCER_REGISTRY",
    "CONSUMER_REGISTRY",
    "PATCH_VERIFIED",
    "flatten_result_entries",
    "registry_for_entry",
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


def _is_read_tool(name, kind_by_tool=None):
    """Read classification: catalog kind wins when a kind map is
    supplied (a verb-name list misclassifies 14 catalog reads, e.g.
    email.read, sms.read_recent, chat_ott.read_chat -- reviewer
    finding 8-V); otherwise the verb list is the fallback so the
    module stays standalone."""
    if kind_by_tool is not None and name in kind_by_tool:
        return kind_by_tool[name] == "read"
    verb = _tool_verb(name)
    return any(verb == v or verb.startswith(v + "_") for v in READ_VERBS)


def _norm_phone(value):
    """Digits-only phone, with +84/84 country prefix folded to 0
    (same rule as zaic_tools base.contact_ref)."""
    d = "".join(ch for ch in str(value or "") if ch.isdigit())
    if d.startswith("84") and len(d) == 11:
        return "0" + d[2:]
    return d


def _contact_reference(call):
    """Return (kind, value) for a call's contact reference, or None.

    kind 'id' for contact_id / 'to'-as-id, kind 'name' for contact_name /
    'to'-as-name. A 'to' holding an email address is not a contact
    reference for these gates. phone_number is handled separately by
    _contact_references (Gate 2 only): Gate 1 is name/id based.
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


def _contact_references(call):
    """ALL contact references of a call for Gate 2: the id/name/to
    reference (if any) plus a phone_number reference (if any).
    A phone-only call (phone.call/sms.send with only phone_number)
    previously bypassed Gate 2 entirely (reviewer finding 3-PH):
    it has no *_id arg and call/send is not a mutate verb, so the
    gate returned not-applicable even for a hallucinated number.
    """
    refs = []
    ref = _contact_reference(call)
    if ref is not None:
        refs.append(ref)
    phone = (call.get("arguments") or {}).get("phone_number")
    if isinstance(phone, str) and phone:
        refs.append(("phone", phone))
    return refs


def _call_reference_values(args):
    """String values of a call's REFERENCE arguments only (for echo
    exclusion): *_id args, contact_name, and to. Free-text args
    (title, content, note, ...) are NOT references: a write whose
    note happens to contain an id string must not suppress that id
    as evidence from its own result (reviewer finding 4-EO).
    """
    out = set()
    if isinstance(args, dict):
        for key, value in args.items():
            if not (key.endswith("_id") or key in ("contact_name", "to")):
                continue
            if isinstance(value, str):
                out.add(nfc_lower(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        out.add(nfc_lower(item))
    return out


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

    tool: tool name. args: the call's arguments. result_entries:
    (field, value) pairs -- or (field, value, path) triples -- for
    scalar leaves of the call's RESULT (phones dropped; field is
    None for a bare scalar result). PATH (THREAD 1 round, optional
    third element): the dotted key path from the result root to
    the dict directly containing the leaf, list indices skipped,
    "" for a top-level scalar. Examples: smart_home.get_status
    {"devices": [{id}]} -> ("id", v, "devices"); the same tool
    unfiltered also returns {"scenes": [{id}]} -> ("id", v,
    "scenes"); loyalty.get_points programs with nested rewards ->
    program ids ("id", v, "programs"), reward ids ("id", v,
    "programs.rewards"); a create returning {"ok", "id", "item"}
    -> ("id", v, "") and ("id", v, "item"). See
    flatten_result_entries for the reference flattener.
    A legacy 2-tuple (no path) is resolved only when its
    (tool, field) maps to exactly one registry in
    PRODUCER_REGISTRY; an ambiguous legacy entry establishes
    nothing. This is an INTERFACE EXTENSION, not a break: old
    2-tuple callers keep working for single-registry tools, and
    callers that can carry paths should (the gates audit and the
    trace shadow must, for the four ambiguous tools above).
    succeeded: True only when the result indicates execution
    (ok True and done not False). A schema-rejected call (ok False)
    and an app no-op (ok True, done False -- unknown id, insufficient
    balance, empty search) both count as NOT succeeded.
    A proposal is not evidence: only succeeded results establish
    anything. REGISTRY-TYPED evidence (THREAD 1 round): a bare
    string is never evidence, and neither is an id-typed field
    from the WRONG registry -- the producer entry's registry (via
    registry_for_entry) must EQUAL the consumer slot's registry
    (CONSUMER_REGISTRY). A free-text scalar that merely equals an
    id proves nothing; a foreign-key field inside a returned
    record (e.g. a booking's flight_id, a message's contact_id, a
    transaction's account_id) proves nothing about the referenced
    registry; and for writes only non-echo values count (a
    successful sms.send returns a message record carrying its own
    contact_id -- that echo proves the contact exists no more than
    the proposal did, because sms/phone never validate contacts).
    Legacy (tool, args) tuples are accepted and treated as
    succeeded=False with no results: they establish nothing. Callers
    must pass PriorCall objects where they know outcomes (the audit
    does).
    """
    tool: str
    args: dict = field(default_factory=dict)
    result_entries: list = field(default_factory=list)
    succeeded: bool = False


def _as_prior_call(entry):
    if isinstance(entry, PriorCall):
        return entry
    if isinstance(entry, (tuple, list)) and len(entry) >= 2:
        return PriorCall(tool=entry[0], args=entry[1] or {},
                         result_entries=[], succeeded=False)
    return PriorCall(tool="", args={}, result_entries=[], succeeded=False)


# ------------------------------------------------------------------
# Registry mapping (THREAD 1 round). Grounds, in order of authority:
# (1) the tool catalog's x-ref field for the consumer slot
#     (train_tools_catalog.json, e.g. home_automation.create_rule
#     device_id -> "smart_home.devices"); (2) the zaic_tools
#     implementation the consumer validates against -- the
#     collection passed to find/patch/delete/create, or an explicit
#     cross-app state check (home_automation.create_rule reads
#     session.states["smart_home"]["devices"]); (3) the producer
#     implementation -- the collection passed to read(), the record
#     returned by find(), or the collection passed to create().
# Deliberately NOT grounds: id-string prefixes, gold pass rates,
# "no collision seen yet". A registry key is "app.collection".
# Two field-scoped exceptions, each grounded in code, not in a
# collection id: food_delivery.merchants (merchant_id is a FIELD of
# restaurant records -- catalog text for ewallet.pay_qr says
# explicitly "không phải id quán"; the producer is
# food_delivery.list_restaurants) and package_tracking.shipments
# dual-key (package_tracking._shipment matches a shipment by its
# state "id" OR its "tracking_id" field, so both producer fields
# establish the same registry).
#
# PRODUCER_REGISTRY: (producer tool, path, field) -> registry.
# path is the dotted key path to the enclosing record ("" at the
# result root); see PriorCall and flatten_result_entries. Only
# primary-id fields are listed, plus the two exceptions above.
# Foreign-key fields inside a returned record are DELIBERATELY
# ABSENT: a booking's flight_id, a message's contact_id, a
# transaction's account_id/beneficiary_id, a reservation's
# book_id, a recording's program_id, an order's restaurant_id,
# a lesson's course_id, a call's chat_id, a rule's device_id,
# a voucher's reward_id/program_id, a saved place's place_id,
# a guest code's lock_id, a playlist record's track ids, a
# meeting's attendees -- none of these establish the referenced
# registry, because the producing tool performed no lookup on
# that registry (it merely returned a record that references it).
# Patch/delete returns are likewise absent for their own id: a
# patch record's id always equals the call's own id argument, so
# the write echo rule excludes it anyway (outcome-equivalent);
# the three patch-validated returns verified by hand
# (bill_payment.pay -> "bill", contacts.update -> "item",
# learning.enroll -> "item") ARE listed for completeness and are
# still echo-excluded for their own id.
# Tools with no id registry (weather, exchange_rate, fuel_price,
# gold_price, lottery, calculator, ewallet.get_balance scalar,
# home_energy usage, robot_vacuum rooms-as-names, chat messages
# which carry no id) have no entries: their results establish
# nothing, explicitly, rather than by accident.
PRODUCER_REGISTRY = {
    # -- reads: list/search/get returning state records ----------
    ("alarm.list", "alarms", "id"): "alarm.alarms",
    ("appliances.list", "appliances", "id"): "appliances.appliances",
    ("banking.get_balance", "accounts", "id"): "banking.accounts",
    ("banking.list_beneficiaries", "beneficiaries", "id"):
        "banking.beneficiaries",
    ("banking.list_transactions", "transactions", "id"):
        "banking.transactions",
    ("bike_rental.find_bikes", "bikes", "id"): "bike_rental.bikes",
    ("bill_payment.list_bills", "bills", "id"): "bill_payment.bills",
    ("calendar.list_events", "events", "id"): "calendar.events",
    ("chat_ott.list_chats", "chats", "id"): "chat_ott.chats",
    ("contacts.search", "contacts", "id"): "contacts.contacts",
    ("contacts.search", "contacts", "name"): "contacts.contacts",
    ("contacts.get", "contacts", "id"): "contacts.contacts",
    ("contacts.get", "contacts", "name"): "contacts.contacts",
    ("door_lock.list_locks", "locks", "id"): "door_lock.locks",
    ("email.list", "emails", "id"): "email.emails",
    ("email.read", "email", "id"): "email.emails",
    ("fitness.get_activity", "activity.workouts", "id"):
        "fitness.workouts",
    ("flights.search", "flights", "id"): "flights.flights",
    ("flights.my_bookings", "bookings", "id"): "flights.bookings",
    ("food_delivery.list_restaurants", "restaurants", "id"):
        "food_delivery.restaurants",
    ("food_delivery.list_restaurants", "restaurants", "merchant_id"):
        "food_delivery.merchants",
    # Merchant_id also rides on place / course / program records
    # (verified in gold history results); registry_for_entry
    # additionally resolves ANY merchant_id field to this registry
    # (field-scoped -- see its docstring), so these entries are
    # documentation as much as lookup.
    ("maps.search_place", "places", "merchant_id"):
        "food_delivery.merchants",
    ("learning.list_courses", "courses", "merchant_id"):
        "food_delivery.merchants",
    ("loyalty.get_points", "programs", "merchant_id"):
        "food_delivery.merchants",
    ("food_delivery.get_menu", "menu", "id"):
        "food_delivery.menu_items",
    ("food_delivery.order_history", "orders", "id"):
        "food_delivery.orders",
    ("home_automation.list_rules", "rules", "id"):
        "home_automation.rules",
    ("home_security.list_alerts", "alerts", "id"):
        "home_security.alerts",
    ("home_security.get_camera", "cameras", "id"):
        "home_security.cameras",
    ("household_chores.list_chores", "chores", "id"):
        "household_chores.chores",
    ("learning.list_courses", "courses", "id"): "learning.courses",
    ("library.search", "books", "id"): "library.books",
    ("loyalty.list_vouchers", "vouchers", "id"): "loyalty.vouchers",
    ("loyalty.get_points", "programs", "id"): "loyalty.programs",
    ("loyalty.get_points", "programs.rewards", "id"):
        "loyalty.rewards",
    ("maps.search_place", "places", "id"): "maps.places",
    ("medication.list", "schedules", "id"): "medication.schedules",
    ("music.list_tracks", "tracks", "id"): "music.tracks",
    ("music.list_tracks", "playlists", "id"): "music.playlists",
    ("news.headlines", "articles", "id"): "news.articles",
    ("news.search", "articles", "id"): "news.articles",
    ("notes.list", "notes", "id"): "notes.notes",
    ("package_tracking.track", "shipments", "id"):
        "package_tracking.shipments",
    ("package_tracking.track", "shipments", "tracking_id"):
        "package_tracking.shipments",
    ("phone.recent_calls", "calls", "id"): "phone.calls",
    ("podcast_radio.search", "shows", "id"): "podcast_radio.shows",
    ("podcast_radio.search", "episodes", "id"):
        "podcast_radio.episodes",
    ("podcast_radio.search", "stations", "id"):
        "podcast_radio.stations",
    ("reminders.list", "reminders", "id"): "reminders.reminders",
    ("ride_hailing.get_quotes", "quotes", "id"):
        "ride_hailing.quotes",
    ("ride_hailing.get_ride", "ride", "id"): "ride_hailing.rides",
    ("shopping_list.get", "items", "id"): "shopping_list.items",
    ("smart_home.get_status", "devices", "id"): "smart_home.devices",
    ("smart_home.get_status", "scenes", "id"): "smart_home.scenes",
    ("sms.read_recent", "messages", "id"): "sms.messages",
    ("subscriptions.list", "subscriptions", "id"):
        "subscriptions.subscriptions",
    ("tasks.list", "tasks", "id"): "tasks.tasks",
    ("tv.guide", "programs", "id"): "tv.programs",
    ("video_meeting.list_meetings", "meetings", "id"):
        "video_meeting.meetings",
    # -- writes: creates returning a NEW id (non-echo only) ------
    # App.create returns {"ok", "id", "item"}; tools returning it
    # directly therefore have paths "" and "item".
    ("alarm.create", "", "id"): "alarm.alarms",
    ("alarm.create", "item", "id"): "alarm.alarms",
    ("banking.open_savings", "savings", "id"): "banking.savings",
    ("banking.transfer", "transaction", "id"):
        "banking.transactions",
    ("bike_rental.reserve", "reservation", "id"):
        "bike_rental.reservations",
    ("bill_payment.pay", "bill", "id"): "bill_payment.bills",
    ("bill_payment.schedule_autopay", "autopay", "id"):
        "bill_payment.autopays",
    ("calendar.create_event", "", "id"): "calendar.events",
    ("calendar.create_event", "item", "id"): "calendar.events",
    ("chat_ott.call", "call", "id"): "chat_ott.calls",
    ("contacts.update", "item", "id"): "contacts.contacts",
    ("door_lock.grant_guest_code", "guest_code", "id"):
        "door_lock.guest_codes",
    ("email.send", "", "id"): "email.sent",
    ("email.send", "email", "id"): "email.sent",
    ("email.create_draft", "", "id"): "email.drafts",
    ("email.create_draft", "draft", "id"): "email.drafts",
    ("email.reply", "", "id"): "email.sent",
    ("email.reply", "email", "id"): "email.sent",
    ("ewallet.transfer", "transaction", "id"):
        "ewallet.transactions",
    ("ewallet.topup_mobile", "transaction", "id"):
        "ewallet.transactions",
    ("ewallet.pay_qr", "transaction", "id"):
        "ewallet.transactions",
    ("fitness.log_workout", "workout", "id"): "fitness.workouts",
    ("flights.book", "booking", "id"): "flights.bookings",
    ("food_delivery.place_order", "order", "id"):
        "food_delivery.orders",
    ("home_automation.create_rule", "rule", "id"):
        "home_automation.rules",
    ("learning.enroll", "item", "id"): "learning.courses",
    ("learning.schedule_lesson", "lesson", "id"):
        "learning.lessons",
    ("learning.log_progress", "progress", "id"):
        "learning.progress",
    ("library.reserve", "reservation", "id"):
        "library.reservations",
    ("loyalty.redeem", "voucher", "id"): "loyalty.vouchers",
    ("maps.save_place", "", "id"): "maps.saved_places",
    ("maps.save_place", "item", "id"): "maps.saved_places",
    ("medication.add", "", "id"): "medication.schedules",
    ("medication.add", "item", "id"): "medication.schedules",
    ("music.add_to_playlist", "playlist", "id"): "music.playlists",
    ("news.save", "", "id"): "news.saved",
    ("news.save", "item", "id"): "news.saved",
    ("notes.create", "", "id"): "notes.notes",
    ("notes.create", "item", "id"): "notes.notes",
    ("package_tracking.schedule_pickup", "pickup", "id"):
        "package_tracking.pickups",
    ("phone.call", "call", "id"): "phone.calls",
    ("reminders.create", "", "id"): "reminders.reminders",
    ("reminders.create", "item", "id"): "reminders.reminders",
    ("ride_hailing.book", "", "id"): "ride_hailing.rides",
    ("ride_hailing.book", "item", "id"): "ride_hailing.rides",
    ("shopping_list.add", "", "id"): "shopping_list.items",
    ("shopping_list.add", "item", "id"): "shopping_list.items",
    ("smart_home.scene_run", "", "scene_id"): "smart_home.scenes",
    ("smart_home.scene_run", "devices", "id"): "smart_home.devices",
    ("sms.send", "message", "id"): "sms.messages",
    ("tasks.add", "", "id"): "tasks.tasks",
    ("tasks.add", "item", "id"): "tasks.tasks",
    ("tv.record", "recording", "id"): "tv.recordings",
    ("video_meeting.create", "", "id"): "video_meeting.meetings",
    ("video_meeting.create", "item", "id"): "video_meeting.meetings",
}

# CONSUMER_REGISTRY: consumer slot -> registry it needs. Every
# *_id slot in the 147-tool catalog is covered: slots with a
# catalog x-ref take that registry (verified against the
# implementation's find/patch collection in every case); the
# three slots without an x-ref are grounded separately --
# merchant_id: catalog text for ewallet.pay_qr (merchant_id field
# of food_delivery.list_restaurants results); reward_id:
# loyalty.py module docstring + redeem() lookup inside one
# program's rewards list (program-membership itself is NOT
# checked by Gate 2 -- residual, see the report); tracking_id:
# package_tracking._shipment dual-key lookup. Slots that are
# NOT ids (email "to" address lists, video_meeting attendees
# lists, loyalty "program" name-or-id, podcast "station"
# name/frequency, tv "channel" name, robot_vacuum rooms) are
# deliberately absent: Gate 2's _entity_ids only collects *_id
# string args, and list/name args are not registry ids.
CONSUMER_REGISTRY = {
    "account_id": "banking.accounts",
    "alarm_id": "alarm.alarms",
    "alert_id": "home_security.alerts",
    "appliance_id": "appliances.appliances",
    "article_id": "news.articles",
    "beneficiary_id": "banking.beneficiaries",
    "bike_id": "bike_rental.bikes",
    "bill_id": "bill_payment.bills",
    "book_id": "library.books",
    "booking_id": "flights.bookings",
    "chat_id": "chat_ott.chats",
    "chore_id": "household_chores.chores",
    "contact_id": "contacts.contacts",
    "course_id": "learning.courses",
    "device_id": "smart_home.devices",
    "email_id": "email.emails",
    "episode_id": "podcast_radio.episodes",
    "event_id": "calendar.events",
    "flight_id": "flights.flights",
    "from_account_id": "banking.accounts",
    "item_id": "shopping_list.items",
    "lock_id": "door_lock.locks",
    "meeting_id": "video_meeting.meetings",
    "merchant_id": "food_delivery.merchants",
    "note_id": "notes.notes",
    "order_id": "food_delivery.orders",
    "place_id": "maps.places",
    "playlist_id": "music.playlists",
    # NB: program_id is tv.record's slot (catalog x-ref tv.programs).
    # Loyalty's redeem takes "program" (name-or-id, not a *_id slot),
    # so no *_id consumer needs loyalty.programs.
    "program_id": "tv.programs",
    "reminder_id": "reminders.reminders",
    "restaurant_id": "food_delivery.restaurants",
    "reward_id": "loyalty.rewards",
    "ride_id": "ride_hailing.rides",
    "rule_id": "home_automation.rules",
    "scene_id": "smart_home.scenes",
    "schedule_id": "medication.schedules",
    "show_id": "podcast_radio.shows",
    "subscription_id": "subscriptions.subscriptions",
    "task_id": "tasks.tasks",
    "track_id": "music.tracks",
    "tracking_id": "package_tracking.shipments",
}

# (tool, field) -> set of registries, for legacy 2-tuple fallback.
_FIELD_REGISTRIES = {}
for (_t, _p, _f), _r in PRODUCER_REGISTRY.items():
    _FIELD_REGISTRIES.setdefault((_t, _f), set()).add(_r)


def _normalize_entry(entry):
    """(field, value, path|None) for a 2- or 3-tuple entry."""
    if isinstance(entry, (tuple, list)):
        if len(entry) >= 3:
            return entry[0], entry[1], entry[2]
        if len(entry) == 2:
            return entry[0], entry[1], None
    return None, None, None


def registry_for_entry(tool, field, path=None):
    """Registry a producer entry establishes, or None.

    With a path, the lookup is exact: (tool, path, field). Without
    a path (legacy 2-tuple), it resolves only when (tool, field)
    maps to exactly one registry; an ambiguous legacy entry
    (e.g. smart_home.get_status "id" -> devices or scenes)
    returns None -- it establishes nothing. A field absent from
    the table (free text, foreign keys, unknown tools) returns
    None: unknown is never silently treated as same-registry.
    One field-level exception: "merchant_id" establishes
    food_delivery.merchants from ANY producer, because merchants
    have no collection and no validating lookup anywhere --
    merchant identity IS the merchant_id field value, and that
    field appears on restaurant, place, course and program
    records alike (verified in gold history results, not just
    the catalog). A plain "id" from those same records still
    does NOT establish a merchant; only merchant_id fields do.
    """
    if not isinstance(field, str):
        return None
    if field == "merchant_id":
        return "food_delivery.merchants"
    if path is not None:
        return PRODUCER_REGISTRY.get((tool, path, field))
    regs = _FIELD_REGISTRIES.get((tool, field), set())
    if len(regs) == 1:
        return next(iter(regs))
    return None


def flatten_result_entries(obj, _path=""):
    """Reference flattener: (field, value, path) triples for
    scalar leaves of a tool RESULT, phones dropped, bools dropped.

    path is the dotted key path from the result root to the dict
    directly containing the leaf (list indices skipped, "" at
    the root). Callers producing PriorCall entries (the gates
    audit, the trace shadow) should use exactly this shape so
    multi-registry results keep their registry: e.g.
    smart_home.get_status -> ("id", v, "devices") vs
    ("id", v, "scenes"); loyalty.get_points ->
    ("id", v, "programs") vs ("id", v, "programs.rewards").
    """
    out = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "phone":
                continue
            if isinstance(value, (dict, list)):
                out.extend(flatten_result_entries(
                    value, key if not _path else _path + "." + key))
            elif isinstance(value, (str, int, float)) \
                    and not isinstance(value, bool):
                out.append((key, value, _path))
    elif isinstance(obj, list):
        for value in obj:
            out.extend(flatten_result_entries(value, _path))
    elif isinstance(obj, (str, int, float)) \
            and not isinstance(obj, bool):
        out.append((None, obj, _path))
    return out


def _establishes_contact_id(priors, roster_ids, value, kind_by_tool=None):
    """Contact existence: roster, or a contacts-app result whose
    registry is contacts.contacts (id/contact_id field).

    Contacts-app READS verify by lookup (search/get return state
    records), so any such entry in a succeeded contacts read
    establishes. Contacts-app WRITEs establish only non-echo ids
    (an update echo does not) -- EXCEPT a succeeded contacts.update
    patch: App.patch finds-or-noops, so a succeeded update whose
    returned record id equals its contact_id argument provably
    looked that contact up (patch-verified, see PATCH_VERIFIED).
    Results from other apps never establish contacts -- a message's
    contact_id is a foreign key in sms.messages, not a contacts
    record, and sms/phone never validate contacts (base.py
    contact_ref returns an unknown contact_id unchanged).
    """
    v = nfc_lower(value)
    if v in roster_ids:
        return True
    for pc in priors:
        if not pc.succeeded or not pc.tool.startswith("contacts."):
            continue
        for entry in pc.result_entries or []:
            f, val, path = _normalize_entry(entry)
            if f in ("id", "contact_id") and isinstance(val, str) \
                    and nfc_lower(val) == v \
                    and registry_for_entry(pc.tool, f, path) \
                    == "contacts.contacts":
                if _is_read_tool(pc.tool, kind_by_tool):
                    return True
                if pc.tool == "contacts.update" \
                        and pc.args.get("contact_id") == value \
                        and f == "id" and path == "item":
                    return True
                if v not in _call_reference_values(pc.args):
                    return True
    return False


def _establishes_contact_name(priors, roster_names, value,
                              kind_by_tool=None):
    """Contact-name existence: roster, or a contacts-app READ
    name field (registry contacts.contacts). No other app's
    result establishes a name, and writes never do (a message's
    content naming someone is not a contact record)."""
    v = nfc_lower(value)
    if v in roster_names:
        return True
    for pc in priors:
        if not pc.succeeded or not _is_read_tool(pc.tool, kind_by_tool) \
                or not pc.tool.startswith("contacts."):
            continue
        for entry in pc.result_entries or []:
            f, val, path = _normalize_entry(entry)
            if f == "name" and isinstance(val, str) \
                    and nfc_lower(val) == v \
                    and registry_for_entry(pc.tool, f, path) \
                    == "contacts.contacts":
                return True
    return False


def _establishes_contact_phone(priors, roster_phones, value):
    """Phone-number reference existence: the number is established
    iff EITHER (a) it matches exactly one roster contact's phone
    (digits-normalized, +84 folded to 0 -- the same rule as
    base.contact_ref, which completes a phone to a contact only on
    a unique match), OR (b) it appears as a phone_number field in a
    SUCCEEDED prior READ of the interaction log (phone.recent_calls
    or sms.read_recent): the callback pattern -- gold routinely
    dials or texts a number from a missed call or a message thread,
    including numbers with no address-book entry at all (empty
    books, hotlines, supplier numbers), so the call log is
    legitimate grounding for the number itself. Deliberately
    EXCLUDED: phone.call / sms.send result phone_numbers -- those
    are echoes of the call's own argument (the write never
    validates), so counting them would launder a hallucinated
    number through its own first use. Zero roster/log matches:
    unknown number, fires. Two or more roster matches: ambiguous,
    fires (log matches need no uniqueness: the number itself is
    the value, no contact completion is involved).
    """
    v = _norm_phone(value)
    if not v:
        return False
    matches = [cid for cid, phone in (roster_phones or {}).items()
               if _norm_phone(phone) == v]
    if len(matches) == 1:
        return True
    if len(matches) > 1:
        return False
    for pc in priors or []:
        if not pc.succeeded:
            continue
        if pc.tool not in ("phone.recent_calls", "sms.read_recent"):
            continue
        for entry in pc.result_entries:
            field, val = entry[0], entry[1]
            if field == "phone_number" and _norm_phone(val) == v:
                return True
    return False


# PATCH_VERIFIED: write tools whose implementation provably looks
# the id up before writing (zaic_tools base.App.patch: find the
# item or return noop, so a SUCCEEDED patch returned the record it
# found; patch returns {"ok": True, "item": record}, so the record
# id flattens to ("id", value, "item")). Map: tool -> (registry,
# patch id-arg). A succeeded patch entry with field "id", path
# "item" and value equal to the patch id-arg therefore ESTABLISHES
# that id even though it echoes the argument -- the echo rule's
# blind-echo concern does not apply to a find-or-noop lookup
# (reviewer finding 4-PV; the round-2 conservative residual is
# thus lifted ONLY for these verified tools). Deliberately
# EXCLUDED: all deletes (App.delete removes the item, so a
# deleted id must not establish a later reference) and any tool
# whose write path is a blind create/echo (sms.send, phone.call,
# email.send, ...). Note email.archive has a delete branch, but
# that branch returns {"ok": True} with NO item, so no ("id", ...)
# entry exists to (mis)use -- the path=="item" requirement makes
# the branch distinction automatic.
PATCH_VERIFIED = {
    "alarm.update": ("alarm.alarms", "alarm_id"),
    "calendar.update_event": ("calendar.events", "event_id"),
    "calendar.cancel_event": ("calendar.events", "event_id"),
    "contacts.update": ("contacts.contacts", "contact_id"),
    "door_lock.set_lock": ("door_lock.locks", "lock_id"),
    "email.archive": ("email.emails", "email_id"),
    "flights.cancel": ("flights.bookings", "booking_id"),
    "food_delivery.cancel_order": ("food_delivery.orders", "order_id"),
    "home_security.acknowledge_alert": ("home_security.alerts",
                                        "alert_id"),
    "household_chores.assign": ("household_chores.chores", "chore_id"),
    "reminders.complete": ("reminders.reminders", "reminder_id"),
    "ride_hailing.cancel": ("ride_hailing.rides", "ride_id"),
    "shopping_list.check": ("shopping_list.items", "item_id"),
    "smart_home.light_set": ("smart_home.devices", "device_id"),
    "smart_home.fan_set": ("smart_home.devices", "device_id"),
    "smart_home.climate_set": ("smart_home.devices", "device_id"),
    "smart_home.switch_set": ("smart_home.devices", "device_id"),
    "tasks.complete": ("tasks.tasks", "task_id"),
}


def _establishes_entity_id(priors, slot, value, kind_by_tool=None):
    """A non-contact *_id is established iff a SUCCEEDED prior
    call has an entry whose registry EQUALS the registry the
    consumer slot needs (CONSUMER_REGISTRY). The old rule
    ("id" of any app, or the slot's own field name) is GONE:
    a calendar event id does not establish a ride_id even when
    the strings are identical, a scene id does not establish a
    device_id, a track id does not establish a playlist_id, and
    a foreign-key field (booking flight_id, message contact_id)
    establishes nothing. READS verify by lookup: a succeeded
    read's registry-matching id-field establishes even when it
    equals the read's input argument (ride_hailing.get_ride
    finds the ride or returns noop, which is not succeeded).
    WRITEs establish only non-echo ids: a create's new id
    counts; a write restating its own argument does not --
    EXCEPT patch-verified writes (PATCH_VERIFIED above): a
    succeeded patch whose returned record id equals its patch
    id-arg provably looked the entity up. A slot with no
    registry in CONSUMER_REGISTRY is UNKNOWN and never
    established (never silently same-registry).
    """
    need = CONSUMER_REGISTRY.get(slot)
    if need is None:
        return False
    v = nfc_lower(value)
    for pc in priors:
        if not pc.succeeded:
            continue
        for entry in pc.result_entries or []:
            f, val, path = _normalize_entry(entry)
            if not isinstance(val, str) or nfc_lower(val) != v:
                continue
            # Patch-verified FIRST: patch tools are deliberately
            # absent from PRODUCER_REGISTRY for their own id (their
            # record id always equals the patch argument), so the
            # registry check below would skip them before the
            # patch branch could run. A succeeded patch whose
            # returned record ("item") id equals its patch id-arg
            # provably looked the entity up.
            patch = PATCH_VERIFIED.get(pc.tool)
            if patch is not None and patch[0] == need \
                    and f == "id" and path == "item" \
                    and pc.args.get(patch[1]) == value:
                return True
            if registry_for_entry(pc.tool, f, path) != need:
                continue
            if _is_read_tool(pc.tool, kind_by_tool):
                return True
            if v not in _call_reference_values(pc.args):
                return True
    return False


def gate_read_before_write(call, prior_calls, rosters, kind_by_tool=None):
    """Gate 2: a write referencing an existing entity needs prior
    evidence that the entity exists in this session.

    prior_calls: [PriorCall] of earlier calls in this session
        (same-sample calls before the write + history calls).
    rosters: [{id, name, phone?}] observed via successful search
        before the write (phone is needed for phone_number
        references; entries without a phone simply do not match
        any phone reference).
    kind_by_tool: optional {tool: "read"/"write"/"meta"} catalog
        kind map; when supplied it overrides the verb-name list
        for read/write classification (see _is_read_tool).
    Applicable iff the write references an entity: a contact reference
    (id, name, or phone_number), any *_id argument, or an
    update/delete/cancel/modify/reschedule verb.
    A write fully specified by the request (e.g. reminders.create with
    all slots) is NOT applicable -- there is no entity to have read.
    Evidence (ALL registry-typed; prior-call ARGUMENTS never count,
    a bare string never counts, and a field from the wrong
    registry never counts -- see PRODUCER_REGISTRY /
    CONSUMER_REGISTRY):
      - contact_id: roster id, or a contacts-app result id/contact_id
        field with registry contacts.contacts (reads verify by
        lookup; writes need non-echo, except patch-verified
        contacts.update);
      - contact name: roster name, or a contacts-app READ name field
        with registry contacts.contacts;
      - phone_number: exactly one roster contact with that phone
        (digits-normalized); zero or multiple matches fire;
      - other *_id: a succeeded result entry whose registry EQUALS
        the slot's registry in CONSUMER_REGISTRY (reads verify by
        lookup; writes need non-echo, except patch-verified
        writes). A legacy 2-tuple entry resolves only when its
        (tool, field) maps to exactly one registry; ambiguous
        legacy entries establish nothing.
    ALL references are checked: every contact reference AND every
    *_id argument, and an id value carried under several arg names
    is checked against EVERY one of its slots (reviewer finding
    3-SL: first-slot-only let an established slot mask an
    unestablished one sharing the value). The old code returned
    after the contact check alone, so an established contact masked
    an unestablished entity id (a code flaw; no tool in the real
    147-tool catalog combines a contact reference with another
    *_id, so the fix is defence in depth, not a real-schema
    behaviour change -- see the fix report).
    Fires iff any referenced entity is unestablished; the reason lists
    every missing reference.
    """
    name = call.get("name", "")
    if _is_read_tool(name, kind_by_tool) or name == "sys.ask_missing_info":
        return GateResult(False, False, "read/ask: gate does not apply")
    refs = _contact_references(call)
    ids = _entity_ids(call)
    verb = _tool_verb(name)
    is_mutate_verb = verb in _MUTATE_VERBS or any(
        verb.startswith(v + "_") for v in _MUTATE_VERBS)
    if not refs and not ids and not is_mutate_verb:
        return GateResult(False, False,
                          "write references no existing entity")
    priors = [_as_prior_call(e) for e in (prior_calls or [])]
    roster_ids = {nfc_lower(e.get("id")) for e in (rosters or [])
                  if isinstance(e, dict) and e.get("id")}
    roster_names = {nfc_lower(e.get("name")) for e in (rosters or [])
                    if isinstance(e, dict) and e.get("name")}
    roster_phones = {e.get("id"): e.get("phone") for e in (rosters or [])
                     if isinstance(e, dict) and e.get("id")
                     and e.get("phone")}
    missing = []
    # Every contact reference (id, name, phone).
    for kind, value in refs:
        if kind == "id":
            if not _establishes_contact_id(priors, roster_ids, value,
                                           kind_by_tool):
                missing.append("contact_id %s" % value)
        elif kind == "name":
            if not _establishes_contact_name(priors, roster_names, value,
                                             kind_by_tool):
                missing.append("contact name %r" % value)
        elif kind == "phone":
            if not _establishes_contact_phone(priors, roster_phones,
                                              value):
                missing.append("phone_number %s" % value)
    # Every *_id reference, checked against EVERY slot carrying it
    # (no early return after the contact, no first-slot-only).
    # Semantics (reviewer finding 3-SL, refined): a value carried
    # under two slots is TWO references -- one per slot -- so it
    # is established only when EVERY slot's registry is
    # established. Checking "any slot" would let an established
    # slot mask an unestablished one sharing the value (the same
    # masking flaw class round 1 fixed for contacts); firing when
    # one slot's registry is unestablished is the conservative-
    # correct outcome, not a false block.
    for eid in sorted(ids):
        slots = [key for key, val in (call.get("arguments") or {}).items()
                 if val == eid and key.endswith("_id")]
        if not all(_establishes_entity_id(priors, slot, eid, kind_by_tool)
                   for slot in slots):
            missing.append("entity id %s" % eid)
    if missing:
        return GateResult(True, True,
                          "unestablished reference(s): %s"
                          % "; ".join(missing))
    if refs or ids:
        return GateResult(False, True, "references established")
    # Bare mutate verb with no id argument: needs a prior SUCCEEDED
    # read of the same app family in this session.
    app = name.split(".", 1)[0] if "." in name else ""
    for pc in priors:
        if pc.succeeded and _is_read_tool(pc.tool, kind_by_tool) \
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
