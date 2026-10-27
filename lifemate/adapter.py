"""Adapter over the official zaic_tools — the ONLY bridge to app state.

Verified against the shipped package (train + public_test, stdlib
only) by reading its code, not by guessing:

- ``ToolEnv(split, id, root=...)`` loads ``<split>_environment/<id>/
  state.json`` + the split catalog and returns one Session. One env
  per sample, created once, in the submission path: every call made on
  it (including schema-rejected ones) lands in ``get_tool_calls()``
  and therefore in the submission line.
- ``validate(name, arguments)`` is schema-check ONLY: it does NOT log
  and does NOT change state. Pre-call validation is therefore safe
  and invisible to scoring — this is the sanctioned way to avoid
  polluting a trace with calls that could never run.
- A call is REJECTED (``{"ok": false, "error": ...}``, state unchanged,
  but still logged) ONLY on a schema error: unknown/not-installed
  tool, missing required param, wrong type/enum/range/format, or no
  x-one-of group. An unknown ID, insufficient balance, or an empty
  search is NOT an error: it returns ``{"ok": true, "done": false,
  "message": ...}`` and changes nothing. Code must distinguish these
  two cases instead of calling both "failed".
- ``sys.ask_missing_info`` is recorded in the call list only and
  touches no state (``{"ok": true, "waiting_for_user": true}``).
- ``get_state_hash()`` = sha256 of the canonicalised FULL current
  state (all apps), not just changed apps. The submission hash must
  come from here, never from a hand-rolled hash.
- ``get_state()`` exists in the library but the agent path NEVER calls
  it: it would expose full app data outside tool calls. It is used
  only in diagnostics that are explicitly labelled as such (gold
  replay in ``run.py`` compares changed apps against label.final_state
  — a train-label check, not agent input).

This module never opens a ``*_environment`` path itself and never
imports anything that does, except through ``ToolEnv``. If you catch
pipeline code reading state.json directly, that is a bug — report it,
do not work around it.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any


class ZaicEnv:
    """One zaic_tools session for one sample."""

    def __init__(self, data_root: str | Path, split: str, sample_id: str):
        data_root = Path(data_root)
        split_dir = data_root / split
        pkg_dir = split_dir / "zaic_tools"
        if not pkg_dir.is_dir():
            raise FileNotFoundError(f"zaic_tools not found under {split_dir}")
        if str(split_dir) not in sys.path:
            sys.path.insert(0, str(split_dir))
        zaic = importlib.import_module("zaic_tools")
        importlib.reload(zaic)  # train/public_test packages differ; reload per split
        self._env = zaic.ToolEnv(split, sample_id, root=str(data_root))
        self.sample_id = sample_id
        self.split = split

    def validate(self, name: str, arguments: dict) -> dict:
        """Schema check only; not logged, no state change."""
        return self._env.validate(name, arguments)

    def call(self, name: str, arguments: dict) -> dict:
        """Execute through zaic_tools; result always a dict, never raises
        for a bad call (schema rejection -> ok:false, logged)."""
        return self._env.call(name, arguments)

    def tool_calls(self) -> list[dict]:
        """Every call made, in order, rejected included — submission material."""
        return self._env.get_tool_calls()

    def state_hash(self) -> str:
        return self._env.get_state_hash()

    def submission_line(self) -> dict:
        return {
            "id": self.sample_id,
            "tool_calls": self.tool_calls(),
            "state_hash": self.state_hash(),
        }
