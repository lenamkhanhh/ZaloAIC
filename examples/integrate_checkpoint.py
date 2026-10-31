"""Bring your own ASR/LLM. No model downloads or GPU dependencies here.

Run `python examples/integrate_checkpoint.py --self-check` after installation.
The self-check uses the real AgentLoop with synthetic tools/model/environment.
It proves the callback/observation path, not checkpoint quality.
"""
from copy import deepcopy
import hashlib
import json

from lifemate.agent import AgentLoop
from lifemate.config import PipelineConfig
from lifemate.loader import Sample


def run_sample(*, sample, transcript, tools, env, generate, config):
    """One fresh loop per sample; caller owns checkpoint and official env.

    generate(prompt: str, tools: dict) -> one {name, arguments} dict or None.
    The callback only proposes; AgentLoop alone validates/executes tools.
    config.grounding can modify proposals; config.shadow_observer only logs.
    """
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("A non-empty transcript from your ASR is required")
    if not callable(generate):
        raise TypeError("generate must be callable")
    config.check_budget()  # Counts are caller-supplied metadata, not measured here.
    loop = AgentLoop(deepcopy(config), tools)
    submission = loop.run(sample, transcript, env, generate)
    # Copy immediately: these diagnostics are never submission fields.
    diagnostics = {
        "observer_enabled": config.shadow_observer,
        "observer_records": deepcopy(loop.observer.records),
        "grounding_log": deepcopy(loop.grounding_log),
    }
    return submission, diagnostics


def self_check():
    """Synthetic read -> observation -> write -> stop, observer OFF and ON."""
    contact = {"id": "synthetic_contact", "name": "Lan", "phone": "0901234567"}
    tools = {
        "contacts.search": {"name": "contacts.search", "kind": "read",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                           "required": ["query"]}},
        "phone.call": {"name": "phone.call", "kind": "write",
            "parameters": {"type": "object", "properties": {"phone_number": {"type": "string"}},
                           "required": ["phone_number"]}},
    }
    sample = Sample(id="synthetic-self-check", split="synthetic", audio="unused.wav",
        context={"current_time": "2026-10-31T09:00:00+07:00", "timezone": "Asia/Ho_Chi_Minh",
                 "user_profile": {}, "installed_apps": {}}, history=[])

    class FakeEnv:
        def __init__(self):
            self.calls, self.dialed = [], []
        def validate(self, name, arguments):
            spec = tools.get(name)
            if not spec or any(k not in arguments for k in spec["parameters"]["required"]):
                return {"ok": False, "error": "synthetic schema failure"}
            return {"ok": True}
        def call(self, name, arguments):
            self.calls.append({"name": name, "arguments": deepcopy(arguments)})
            if name == "contacts.search":
                return {"ok": True, "done": True, "contacts": [deepcopy(contact)]}
            self.dialed.append(arguments["phone_number"])
            return {"ok": True, "done": True}
        def submission_line(self):
            return {"id": sample.id, "tool_calls": deepcopy(self.calls),
                    "state_hash": hashlib.sha256(json.dumps(self.dialed).encode()).hexdigest()}

    outputs = []
    for observer in (False, True):
        env = FakeEnv()
        calls = iter([{"name": "contacts.search", "arguments": {"query": "Lan"}},
                      {"name": "phone.call", "arguments": {"phone_number": contact["phone"]}}, None])
        prompts = []
        def generate(prompt, available_tools):
            prompts.append(prompt)
            proposal = next(calls)
            if proposal and proposal["name"] == "phone.call" and contact["phone"] not in prompt:
                raise RuntimeError("read observation did not reach generator")
            return proposal
        line, diagnostics = run_sample(sample=sample, transcript="Gọi cho Lan.", tools=tools,
            env=env, generate=generate, config=PipelineConfig(shadow_observer=observer))
        if len(line["tool_calls"]) != 2 or env.dialed != [contact["phone"]]:
            raise RuntimeError("synthetic read/write trace mismatch")
        records = diagnostics["observer_records"]
        if observer and (not records or any(r.get("error") for r in records)):
            raise RuntimeError("observer did not compute error-free records")
        if not observer and records:
            raise RuntimeError("observer OFF unexpectedly recorded data")
        outputs.append((line, prompts))
    if outputs[0] != outputs[1]:
        raise RuntimeError("observer changed submission or prompts")
    return {"status": "PASS", "scope": "synthetic CPU callback/observation and observer parity",
            "model_inference": "NOT_RUN", "official_simulator": "NOT_RUN"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", required=True, action="store_true")
    parser.parse_args()
    print(json.dumps(self_check()))
