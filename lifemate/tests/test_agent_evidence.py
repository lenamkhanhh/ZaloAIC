"""Behavioral regressions from the smoke failure classes; no probe answers."""
import json
import unittest

from lifemate.agent import AgentLoop, render_observation_prompt
from lifemate.config import PipelineConfig
from lifemate.grounding import ground_arguments
from lifemate.loader import Sample, Turn
from lifemate.llm import parse_model_output


def spec(name, kind, properties=None):
    return {"name": name, "kind": kind, "parameters": {
        "type": "object", "properties": properties or {}, "required": []}}


TOOLS = {
    "contacts.search": spec("contacts.search", "read"),
    "phone.call": spec("phone.call", "write", {
        "contact_id": {"type": "string", "x-ref": "contacts.contacts"}}),
    "wallet.topup": spec("wallet.topup", "write", {"phone": {"type": "string"}}),
    "tasks.create": spec("tasks.create", "write"),
    "tasks.complete": spec("tasks.complete", "write", {
        "task_id": {"type": "string", "x-ref": "tasks.tasks"}}),
    "music.list": spec("music.list", "read"),
    "music.play": spec("music.play", "write", {
        "track_id": {"type": "string", "x-ref": "music.tracks"},
        "playlist_id": {"type": "string", "x-ref": "music.playlists"}}),
    "sys.ask_missing_info": spec("sys.ask_missing_info", "meta"),
}


class Env:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or {}

    def validate(self, name, arguments):
        return {"ok": name in TOOLS}

    def call(self, name, arguments):
        self.calls.append({"name": name, "arguments": arguments})
        return self.results.get(name, {"ok": True})

    def submission_line(self):
        return {"tool_calls": self.calls}


class EvidenceRegressions(unittest.TestCase):
    def setUp(self):
        self.sample = Sample("synthetic", "train", "x.wav", {"installed_apps": {}}, [])

    def test_full_observation_is_compact_json_and_keeps_all_fields(self):
        result = {"ok": True, "items": [{"id": f"opaque_{i}", "name": "x" * 80,
                   "phone": str(70000000 + i), "amount": i, "relation": "colleague"} for i in range(30)]}
        prompt = render_observation_prompt("base", [{"name": "directory.list", "arguments": {}}], [result])
        payload = prompt.split("output=", 1)[1]
        self.assertEqual(json.loads(payload), result)
        self.assertNotIn(': ', payload)

    def test_unseen_reference_never_reaches_env_call(self):
        env = Env()
        def bad(prompt, tools):
            return {"name": "phone.call", "arguments": {"contact_id": "invented"}}
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Call my colleague", env, bad)
        self.assertEqual(env.calls, [])

    def test_rejected_id_can_be_resolved_by_read_then_used(self):
        env = Env({"contacts.search": {"ok": True, "contacts": [{"id": "person_z", "name": "Zed"}]}})
        def generator(prompt, tools):
            if not env.calls and "NOT executed" not in prompt:
                return {"name": "phone.call", "arguments": {"contact_id": "guessed"}}
            if not env.calls:
                self.assertIn("contacts.search", prompt)
                return {"name": "contacts.search", "arguments": {}}
            if len(env.calls) == 1:
                self.assertIn("person_z", prompt)
                return {"name": "phone.call", "arguments": {"contact_id": "person_z"}}
            return None
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Call Zed", env, generator)
        self.assertEqual([c["name"] for c in env.calls], ["contacts.search", "phone.call"])

    def test_history_repr_results_supply_reference_evidence(self):
        self.sample.history = [Turn("assistant", tool_calls=[{"name": "contacts.search", "arguments": {}}],
                                    tool_results="[{'ok': True, 'contacts': [{'id': 'past_id', 'name': 'Jo'}]}]")]
        env = Env()
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Call Jo", env,
            lambda p, t: None if env.calls else {"name": "phone.call", "arguments": {"contact_id": "past_id"}})
        self.assertEqual(len(env.calls), 1)

    def test_reference_is_scoped_to_collection_not_just_app(self):
        call = {"name": "music.play", "arguments": {"track_id": "only_playlist"}}
        _, errors = ground_arguments(call, TOOLS,
            [{"name": "music.list", "arguments": {}}],
            [{"ok": True, "tracks": [], "playlists": [{"id": "only_playlist", "name": "Mix"}]}])
        self.assertTrue(errors)

    def test_named_observed_entity_can_be_repaired_without_changing_id(self):
        call, errors = ground_arguments({"name": "phone.call", "arguments": {"contact_id": "Jo"}}, TOOLS,
            [{"name": "contacts.search", "arguments": {}}],
            [{"ok": True, "contacts": [{"id": "ID:Case-Kept", "name": "Jo"}]}])
        self.assertFalse(errors)
        self.assertEqual(call["arguments"]["contact_id"], "ID:Case-Kept")

    def test_successful_create_supplies_new_id_without_a_read(self):
        call, errors = ground_arguments({"name": "tasks.complete", "arguments": {"task_id": "made"}}, TOOLS,
            [{"name": "tasks.create", "arguments": {}}],
            [{"ok": True, "id": "made", "item": {"id": "made", "title": "Work"}}])
        self.assertFalse(errors)

    def test_failed_call_does_not_establish_reference(self):
        _, errors = ground_arguments({"name": "tasks.complete", "arguments": {"task_id": "bad"}}, TOOLS,
            [{"name": "tasks.create", "arguments": {}}],
            [{"ok": True, "done": False, "item": {"id": "bad", "title": "not created"}}])
        self.assertTrue(errors)

    def test_observed_unnamed_id_still_valid(self):
        _, errors = ground_arguments({"name": "tasks.complete", "arguments": {"task_id": "unnamed"}}, TOOLS,
            [{"name": "tasks.create", "arguments": {}}], [{"ok": True, "id": "unnamed"}])
        self.assertFalse(errors)

    def test_unknown_phone_is_not_executed(self):
        env = Env()
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Top up for my colleague", env,
            lambda p, t: {"name": "wallet.topup", "arguments": {"phone": "0712345678"}})
        self.assertEqual(env.calls, [])

    def test_spoken_phone_and_user_supplied_id_are_supported(self):
        env = Env()
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Top up không bảy một hai ba bốn năm sáu bảy tám", env,
            lambda p, t: None if env.calls else {"name": "wallet.topup", "arguments": {"phone": "0712345678"}})
        self.assertEqual(len(env.calls), 1)

    def test_grouped_spoken_digits_and_phone_in_read_message(self):
        for text in ("Call không bảy một hai, ba bốn năm, sáu bảy tám",):
            env = Env()
            AgentLoop(PipelineConfig(), TOOLS).run(self.sample, text, env,
                lambda p, t: None if env.calls else {"name": "wallet.topup", "arguments": {"phone": "0712345678"}})
            self.assertEqual(len(env.calls), 1)
        self.sample.history = [Turn("assistant", tool_calls=[{"name": "chat.read", "arguments": {}}],
            tool_results=[{"ok": True, "messages": [{"content": "New number: 0712345678. Please call."}]}])]
        env = Env()
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Call that number", env,
            lambda p, t: None if env.calls else {"name": "wallet.topup", "arguments": {"phone": "0712345678"}})
        self.assertEqual(len(env.calls), 1)

    def test_person_name_in_user_text_does_not_become_an_id(self):
        env = Env()
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Call Jo", env,
            lambda p, t: {"name": "phone.call", "arguments": {"contact_id": "Jo"}})
        self.assertEqual(env.calls, [])

    def test_plain_explicit_id_with_parameter_label_is_supported(self):
        env = Env()
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Call contact_id=opaque", env,
            lambda p, t: None if env.calls else {"name": "phone.call", "arguments": {"contact_id": "opaque"}})
        self.assertEqual(len(env.calls), 1)
        env = Env()
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Call contact explicit_7", env,
            lambda p, t: None if env.calls else {"name": "phone.call", "arguments": {"contact_id": "explicit_7"}})
        self.assertEqual(len(env.calls), 1)

    def test_ask_ends_turn_without_extra_write(self):
        env = Env()
        def generator(prompt, tools):
            if not env.calls:
                return {"name": "sys.ask_missing_info", "arguments": {"tool_name": "tasks.create", "params": ["time"]}}
            return {"name": "tasks.create", "arguments": {}}
        AgentLoop(PipelineConfig(max_steps=2), TOOLS).run(self.sample, "Remind me", env, generator)
        self.assertEqual([c["name"] for c in env.calls], ["sys.ask_missing_info"])

    def test_format_retry_keeps_prior_observations(self):
        env = Env({"contacts.search": {"ok": True, "contacts": [{"id": "retain_me", "name": "Jo"}]}})
        count = 0
        def generator(prompt, tools):
            nonlocal count
            count += 1
            if count == 1:
                return {"name": "contacts.search", "arguments": {}}
            if count == 2:
                return ["bad format"]
            self.assertIn("retain_me", prompt)
            return None
        AgentLoop(PipelineConfig(), TOOLS).run(self.sample, "Call Jo", env, generator)

    def test_stop_as_tool_is_a_stop_signal_not_an_execution(self):
        self.assertIsNone(parse_model_output('{"name":"stop","reason":"done"}'))


if __name__ == "__main__":
    unittest.main()
