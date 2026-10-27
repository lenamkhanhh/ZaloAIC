"""Loader for the real LifeMate package (v3.2.0, built 2026-10-24).

Verified against the extracted zip (URL + SHA256 in RUN_LIFEMATE.md):

- ``train/``: 1545 samples, keys exactly
  ``audio, audio_text, context, history, id, label``; label keys
  ``final_state, tool_calls, tool_results``; ``final_state`` holds only
  apps changed by the label calls.
- ``public_test/``: 634 samples, keys exactly
  ``audio, context, history, id`` — NO label, NO audio_text anywhere
  (neither on the final request nor on history user turns).
- Catalogs: train 46 apps / 147 tools, public_test 36 apps / 122 tools
  (schema_version 2.7.0 both). The app sets DIFFER: public_test has
  apps train lacks (stocks, translator, grocery, recipes,
  public_transit, parking, train_bus_tickets, ecommerce,
  event_tickets, habit_tracker, pantry) and vice versa — a model that
  memorises train apps will face unseen apps on public/private.
- Audio: WAV 16 kHz mono 16-bit (checked on 4 files with stdlib wave).
- History: even turn counts (user/assistant pairs); user turns have
  ``audio`` (+ ``audio_text`` on train only); assistant turns have
  ``text`` + ``tool_calls`` (+ ``tool_results``, which in history is
  sometimes a Python-repr STRING, not parsed JSON — callers must not
  json-parse history tool_results blindly).
- ``sample_submission.jsonl``: 3 example lines (execute / ask /
  empty), format ``{id, tool_calls, state_hash}``.

This module NEVER opens anything under ``<split>_environment/``. The
only code allowed to touch state files is zaic_tools itself, via
``adapter.py``. Loader functions that take a ``root`` expect the
extracted ``train+public_test/`` directory (the one containing
``train/`` and ``public_test/``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    audio: str | None = None  # path relative to the split dir
    audio_text: str | None = None  # train only; None on public_test
    text: str | None = None  # assistant text
    tool_calls: list = field(default_factory=list)
    tool_results: object = None  # list OR repr-string in history; do not assume


@dataclass
class Sample:
    id: str
    split: str
    audio: str  # path relative to the split dir
    context: dict
    history: list[Turn]
    audio_text: str | None = None  # train only
    label: dict | None = None  # train only

    @property
    def installed_tools(self) -> list[str]:
        """Tool names the sample may call, from context.installed_apps
        plus sys.ask_missing_info (always allowed by zaic_tools)."""
        tools = []
        for app in self.context["installed_apps"].values():
            tools.extend(app.get("tools", []))
        if "sys.ask_missing_info" not in tools:
            tools.append("sys.ask_missing_info")
        return tools

    def label_class(self) -> str:
        """Stratification class for splits: empty / ask_only /
        ask_after (ask present but not alone) / normal."""
        if self.label is None:
            return "unlabelled"
        calls = self.label["tool_calls"]
        if not calls:
            return "empty"
        names = [c["name"] for c in calls]
        if names == ["sys.ask_missing_info"]:
            return "ask_only"
        if "sys.ask_missing_info" in names:
            return "ask_after"
        return "normal"


def load_catalog(root: str | Path, split: str) -> dict:
    root = Path(root)
    with open(root / split / f"{split}_tools_catalog.json", encoding="utf-8") as f:
        return json.load(f)


def catalog_tools_for_sample(catalog: dict, sample: Sample) -> dict:
    """Tool specs for this sample only: its installed_apps tools plus
    sys.ask_missing_info. Never put the full split catalog in a prompt
    (context budget + noise; see plans/lifemate.md)."""
    wanted = set(sample.installed_tools)
    out = {}
    for app in catalog["apps"]:
        for tool in app["tools"]:
            if tool["name"] in wanted:
                out[tool["name"]] = tool
    return out


def fuzzy_params(catalog: dict) -> dict[str, set[str]]:
    """tool name -> param names with x-match: fuzzy (scoring input)."""
    out: dict[str, set[str]] = {}
    for app in catalog["apps"]:
        for tool in app["tools"]:
            fuzzy = {
                name
                for name, spec in tool["parameters"].get("properties", {}).items()
                if spec.get("x-match") == "fuzzy"
            }
            if fuzzy:
                out[tool["name"]] = fuzzy
    return out


def _load_turn(raw: dict) -> Turn:
    return Turn(
        role=raw["role"],
        audio=raw.get("audio"),
        audio_text=raw.get("audio_text"),
        text=raw.get("text"),
        tool_calls=raw.get("tool_calls", []),
        tool_results=raw.get("tool_results"),
    )


def load_split(root: str | Path, split: str) -> list[Sample]:
    root = Path(root)
    samples = []
    with open(root / split / f"{split}.jsonl", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            raw = json.loads(line)
            samples.append(
                Sample(
                    id=raw["id"],
                    split=split,
                    audio=raw["audio"],
                    context=raw["context"],
                    history=[_load_turn(t) for t in raw.get("history", [])],
                    audio_text=raw.get("audio_text"),
                    label=raw.get("label"),
                )
            )
    return samples
