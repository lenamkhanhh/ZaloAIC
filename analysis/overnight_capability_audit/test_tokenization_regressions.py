"""Regression tests for the tokenization fix (Thread A, 2026-10-29).

Bug fixed: the old builder encoded the RAW prompt with
tok.encode(text, add_special_tokens=False), while runtime a2e832b
applies the chat template first (llm._render: one user message,
add_generation_prompt=True). Builder and validator shared the old
helper, so they agreed with each other while both disagreeing with
runtime. These tests pin the fix:

  * raw encode MUST differ from runtime ids (missing role markers
    and the assistant generation prefix);
  * rendered prompt ids MUST equal runtime ids computed through TWO
    independent paths (worktree llm._render, and apply_chat_template
    called directly in this test, never through the builder helper);
  * a verification function independent of the builder MUST reject
    tampered role markers / generation prefixes, missing or extra
    EOS, and a mask shifted by one token;
  * budget MUST be computed on rendered prompt + 512 reserved output,
    so a case that fits on raw length but not on rendered length fails.

Tokenizer tests run only under a python with transformers (the venv
python); under system python they SKIP with a reason and are never
reported as passes. Pure-logic tests (verification function, fake-id
budget/error paths) run on both backends.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WORKTREE = "/home/hatch/workspace/zaic-branch-a2e832b/lifemate"
VENV_PYTHON = "/home/hatch/workspace/zaic-test-venv/bin/python"
MODEL = "Qwen/Qwen3-4B-Instruct-2507"
REVISION = "cdbee75"
EOS = 151645

SYN_PROMPT = ("You are a Vietnamese voice assistant. Output exactly one JSON "
              "object per turn.")
SYN_TARGET = '{"name":"contacts.search","arguments":{"query":"Mai"}}'
SYN_STOP = '{"stop":true}'


def load_tokenizer():
    """Return (tok, transformers_version) or raise (caller skips)."""
    import subprocess
    code = (
        "import json, transformers\n"
        "from transformers import AutoTokenizer\n"
        f"tok = AutoTokenizer.from_pretrained({MODEL!r}, revision={REVISION!r}, local_files_only=True)\n"
        "print(json.dumps({'version': transformers.__version__, 'eos': tok.eos_token_id}))\n"
    )
    proc = subprocess.run([VENV_PYTHON, "-c", code], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-500:])
    # The tokenizer object itself is only usable in-process under the
    # venv python; this test file is EXPECTED to run under venv python
    # for tokenizer tests (see TestCase setUpClass).
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, local_files_only=True)
    import transformers
    return tok, transformers.__version__


def verify_step(step):
    """Independent verification of one builder step (does NOT use the
    builder's attach logic). Returns a list of failure reasons; empty
    means the step is well-formed. Checks: input_ids construction,
    labels mask (prompt fully masked, target fully trained, exactly
    one EOS at the end), eos not inside target, sequence length, and
    prompt_token_ids meaning rendered ids."""
    reasons = []
    r = step.get("rendered_prompt_token_ids")
    t = step.get("target_token_ids")
    inp = step.get("input_ids")
    lab = step.get("labels")
    if r is None or t is None or inp is None or lab is None:
        return ["missing token fields"]
    if step.get("prompt_token_ids") != r:
        reasons.append("prompt_token_ids != rendered_prompt_token_ids")
    # Pinned Qwen template structure (constants of the template, not
    # sample data): rendered prompt must start with <|im_start|> user
    # \n and end with the assistant generation prefix <|im_end|> \n
    # <|im_start|> assistant \n. This is what catches a dropped or
    # altered role marker / generation prefix even when the tampered
    # step is internally consistent.
    if r[:3] != [151644, 872, 198]:
        reasons.append("missing/altered user role marker prefix")
    if r[-5:] != [151645, 198, 151644, 77091, 198]:
        reasons.append("missing/altered assistant generation prefix")
    if inp != r + t + [EOS]:
        reasons.append("input_ids != rendered + target + [EOS]")
    if lab != [-100] * len(r) + t + [EOS]:
        reasons.append("labels != [-100]*len(rendered) + target + [EOS]")
    if any(x != -100 for x in lab[:len(r)]):
        reasons.append("prompt token trained (mask leak)")
    if lab[len(r):-1] != t:
        reasons.append("target token masked")
    if not lab or lab[-1] != EOS or not inp or inp[-1] != EOS:
        reasons.append("missing final EOS")
    if EOS in t:
        reasons.append("EOS inside target (would duplicate EOS)")
    if step.get("sequence_tokens") != len(inp):
        reasons.append("sequence_tokens != len(input_ids)")
    if step.get("eos_token_id") != EOS:
        reasons.append("eos_token_id != 151645")
    return reasons


class TokenizerCase(unittest.TestCase):
    """Base for tests needing the real tokenizer: only meaningful
    under the venv python. Under any other interpreter, skip."""

    @classmethod
    def setUpClass(cls):
        if sys.executable != VENV_PYTHON and not os.path.exists(VENV_PYTHON):
            raise unittest.SkipTest(f"venv python missing: {VENV_PYTHON}")
        try:
            from transformers import AutoTokenizer  # noqa: F401
        except Exception as exc:
            raise unittest.SkipTest(f"transformers unavailable: {exc}")
        try:
            cls.tok, cls.version = load_tokenizer()
        except Exception as exc:
            raise unittest.SkipTest(f"tokenizer unavailable: {exc}")


class TestRawVsRuntime(TokenizerCase):
    def test_raw_encode_differs_from_runtime(self):
        """(a) Raw encode must be caught deviating from runtime."""
        tok = self.tok
        raw = tok.encode(SYN_PROMPT, add_special_tokens=False)
        rendered = tok.apply_chat_template(
            [{"role": "user", "content": SYN_PROMPT}], tokenize=False,
            add_generation_prompt=True)
        out = tok.apply_chat_template(
            [{"role": "user", "content": SYN_PROMPT}], tokenize=True,
            add_generation_prompt=True)
        rendered_ids = out["input_ids"] if hasattr(out, "keys") else out
        self.assertNotEqual(raw, rendered_ids)
        # Exactly the template wrapper: 3 head + 5 tail tokens.
        self.assertEqual(len(rendered_ids) - len(raw), 8)
        self.assertEqual(rendered_ids[:3], [151644, 872, 198])  # <|im_start|> user \n
        self.assertEqual(rendered_ids[-5:], [151645, 198, 151644, 77091, 198])
        self.assertEqual([tok.decode([i]) for i in rendered_ids[:3]],
                         ["<|im_start|>", "user", "\n"])
        self.assertEqual([tok.decode([i]) for i in rendered_ids[-5:]],
                         ["<|im_end|>", "\n", "<|im_start|>", "assistant", "\n"])

    def test_builder_ids_equal_runtime_two_independent_paths(self):
        """(e) Builder ids must equal runtime ids computed WITHOUT the
        builder helper, through two independent paths."""
        from sft_prototype_builder import batch_tokenize
        data = batch_tokenize(VENV_PYTHON, MODEL, REVISION, [(SYN_PROMPT, SYN_TARGET)])
        item = data["results"][0]
        builder_ids = item["rendered_prompt_token_ids"]
        # Path 1: import the worktree runtime module and call _render.
        sys.path.insert(0, WORKTREE)
        import llm as runtime_llm
        rendered_text = runtime_llm._render(self.tok, SYN_PROMPT, 16384, 512)
        path1_ids = self.tok.encode(rendered_text, add_special_tokens=False)
        # Path 2: apply_chat_template called directly in this test.
        out = self.tok.apply_chat_template(
            [{"role": "user", "content": SYN_PROMPT}], tokenize=True,
            add_generation_prompt=True)
        path2_ids = out["input_ids"] if hasattr(out, "keys") else out
        self.assertEqual(builder_ids, path1_ids)
        self.assertEqual(builder_ids, path2_ids)
        self.assertEqual(item["rendered_prompt"], rendered_text)
        self.assertEqual(item["runtime_input_ids"], path1_ids)
        self.assertEqual(data["eos_token_id"], EOS)

    def test_concat_is_correct_construction_not_full_text(self):
        """Concat (rendered + target + [EOS]) is the teacher-forcing
        construction; full-conversation tokenize adds a trailing
        newline token after EOS that generation never produces."""
        from sft_prototype_builder import batch_tokenize
        data = batch_tokenize(VENV_PYTHON, MODEL, REVISION, [(SYN_PROMPT, SYN_STOP)])
        item = data["results"][0]
        concat = (item["rendered_prompt_token_ids"] + item["target_token_ids"] + [EOS])
        full = item["full_conversation_token_ids"]
        self.assertEqual(full[:len(concat)], concat)
        self.assertEqual(full[len(concat):], [198])  # trailing "\n" after EOS only
        self.assertNotIn(EOS, item["target_token_ids"])


class TestVerificationRejects(unittest.TestCase):
    def _good_step(self):
        r = [151644, 872, 198, 100, 200, 151645, 198, 151644, 77091, 198]
        t = [300, 301, 302]
        return {"rendered_prompt_token_ids": r, "prompt_token_ids": list(r),
                "target_token_ids": t, "input_ids": r + t + [EOS],
                "labels": [-100] * len(r) + t + [EOS],
                "sequence_tokens": len(r) + len(t) + 1, "eos_token_id": EOS}

    def test_good_step_passes(self):
        self.assertEqual(verify_step(self._good_step()), [])

    def test_role_marker_removed_fails(self):
        """(b) Dropping the <|im_start|>user prefix must fail, even
        though the tampered step is internally consistent (input_ids
        and labels rebuilt to match the tampered ids). Only the
        template-marker check catches it."""
        st = self._good_step()
        r = st["rendered_prompt_token_ids"][3:]
        t = st["target_token_ids"]
        st["rendered_prompt_token_ids"] = r
        st["prompt_token_ids"] = list(r)
        st["input_ids"] = r + t + [EOS]
        st["labels"] = [-100] * len(r) + t + [EOS]
        st["sequence_tokens"] = len(st["input_ids"])
        self.assertIn("missing/altered user role marker prefix", verify_step(st))

    def test_generation_prefix_changed_fails(self):
        """(b) Changing the assistant generation prefix must fail."""
        st = self._good_step()
        r = st["rendered_prompt_token_ids"][:-1] + [999]
        t = st["target_token_ids"]
        st["rendered_prompt_token_ids"] = r
        st["prompt_token_ids"] = list(r)
        st["input_ids"] = r + t + [EOS]
        st["labels"] = [-100] * len(r) + t + [EOS]
        st["sequence_tokens"] = len(st["input_ids"])
        self.assertIn("missing/altered assistant generation prefix", verify_step(st))

    def test_eos_missing_and_extra_fail(self):
        """(c) Missing or extra EOS must fail."""
        st = self._good_step()
        st["labels"] = st["labels"][:-1]
        self.assertNotEqual(verify_step(st), [])
        st = self._good_step()
        st["labels"] = st["labels"] + [EOS]
        self.assertNotEqual(verify_step(st), [])
        st = self._good_step()
        st["input_ids"] = st["input_ids"][:-1]
        self.assertNotEqual(verify_step(st), [])

    def test_mask_shifted_by_one_fails(self):
        """(c) A mask off by one token must fail, both directions."""
        st = self._good_step()
        r, t = st["rendered_prompt_token_ids"], st["target_token_ids"]
        st["labels"] = [-100] * (len(r) - 1) + t + [EOS]  # last prompt token trained
        self.assertIn("prompt token trained (mask leak)", verify_step(st))
        st = self._good_step()
        st["labels"] = [-100] * (len(r) + 1) + t[1:] + [EOS]  # first target masked
        self.assertIn("target token masked", verify_step(st))

    def test_eos_inside_target_rejected_by_attach(self):
        """EOS inside target ids must surface as a token error."""
        from sft_prototype_builder import attach_token_data
        example = {"sample_id": "synthetic-eos", "steps": [
            {"step": 0, "prompt": SYN_PROMPT, "target": SYN_STOP}]}
        token_data = {"eos_token_id": EOS, "results": [{
            "rendered_prompt": "<|im_start|>user\nX<|im_end|>\n<|im_start|>assistant\n",
            "rendered_prompt_token_ids": [151644, 872, 198, 100, 151645, 198, 151644, 77091, 198],
            "runtime_input_ids": [151644, 872, 198, 100, 151645, 198, 151644, 77091, 198],
            "target_token_ids": [300, EOS],
            "full_conversation_token_ids": [151644, 872, 198, 100, 151645, 198, 151644, 77091, 198, 300, EOS],
        }]}
        index = {("p", "synthetic-eos", 0): 0, ("t", "synthetic-eos", 0): 0}
        attach_token_data(example, token_data, index, max_context_tokens=16384)
        self.assertTrue(any(e["reason"] == "eos_in_target"
                            for e in example["token_errors"]))


class TestBudgetBoundary(TokenizerCase):
    def test_raw_fits_but_rendered_plus_reserve_fails(self):
        """(d) Budget uses rendered length + 512, not raw length."""
        from sft_prototype_builder import attach_token_data, batch_tokenize
        tok = self.tok
        raw_len = len(tok.encode(SYN_PROMPT, add_special_tokens=False))
        data = batch_tokenize(VENV_PYTHON, MODEL, REVISION, [(SYN_PROMPT, SYN_TARGET)])
        item = data["results"][0]
        rendered_len = len(item["rendered_prompt_token_ids"])
        self.assertEqual(rendered_len, raw_len + 8)
        example = {"sample_id": "synthetic-budget", "steps": [
            {"step": 0, "prompt": SYN_PROMPT, "target": SYN_TARGET}]}
        index = {("p", "synthetic-budget", 0): 0, ("t", "synthetic-budget", 0): 0}
        # At max_context = raw_len + 512 the RAW prompt would pass, but
        # the rendered prompt + 512 exceeds it: must be over_budget.
        attach_token_data(example, data, index, max_context_tokens=raw_len + 512)
        self.assertEqual(example["budget_status"], "over_budget")
        self.assertTrue(example["token_budget_over_steps"])
        # Exactly at the boundary it passes.
        attach_token_data(example, data, index, max_context_tokens=rendered_len + 512)
        self.assertEqual(example["budget_status"], "ok")
        self.assertFalse(example["token_budget_over_steps"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
