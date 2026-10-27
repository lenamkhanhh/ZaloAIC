import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import nullcontext
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("smoke_runner", ROOT / "smoke_runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SmokePreflight(unittest.TestCase):
    def test_attention_override_restores_helper_even_on_failure(self):
        original = lambda mask, key: True
        helper = SimpleNamespace(use_gqa_in_sdpa=original)
        modules = {
            "transformers": SimpleNamespace(__version__="4.57.6"),
            "transformers.integrations": SimpleNamespace(sdpa_attention=helper),
            "torch.nn.attention": SimpleNamespace(
                SDPBackend=SimpleNamespace(EFFICIENT_ATTENTION="efficient"),
                sdpa_kernel=lambda backend: nullcontext()),
        }
        with patch.dict("sys.modules", modules):
            with runner.t4_efficient_attention():
                self.assertFalse(helper.use_gqa_in_sdpa(None, None))
            self.assertIs(helper.use_gqa_in_sdpa, original)
            with self.assertRaisesRegex(RuntimeError, "generation failed"):
                with runner.t4_efficient_attention():
                    raise RuntimeError("generation failed")
            self.assertIs(helper.use_gqa_in_sdpa, original)
            modules["transformers"].__version__ = "5.0.0"
            with self.assertRaisesRegex(RuntimeError, "requires transformers"):
                with runner.t4_efficient_attention():
                    self.fail("unsupported version must not execute")
            self.assertIs(helper.use_gqa_in_sdpa, original)

    def test_five_ids_are_unique_and_dev(self):
        assignment = json.loads((ROOT.parents[1] / "lifemate/splits/train_dev_heldout.json").read_text())
        ids = [item["id"] for item in runner.SAMPLE_PLAN]
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)
        self.assertTrue(all(assignment[item] == "dev" for item in ids))

    def test_notebook_is_self_contained_and_compiles(self):
        notebook = json.loads((ROOT / "lifemate_smoke.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(notebook["nbformat"], 4)
        self.assertIn(runner.REPO_COMMIT, "".join(notebook["cells"][1]["source"]))
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), f"cell-{index}", "exec")
        self.assertEqual("".join(notebook["cells"][-1]["source"]).strip(), "main()")

    def test_kernel_is_private(self):
        metadata = json.loads((ROOT / "kernel-metadata.json").read_text())
        self.assertIs(metadata["is_private"], True)
        self.assertEqual(metadata["machine_shape"], "NvidiaTeslaT4")

    def test_archive_rejects_traversal(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "bad.zip"
            with zipfile.ZipFile(path, "w") as zipped:
                zipped.writestr("../escape.txt", "bad")
            with self.assertRaises(ValueError):
                runner.safe_extract(path, Path(temp) / "extract")
            self.assertFalse((Path(temp) / "escape.txt").exists())

    def test_bundle_excludes_itself(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            runner.write_json(Path(temp) / "summary.json", {"status": "test"})
            bundle = runner.make_bundle(Path(temp))
            runner.make_bundle(Path(temp))
            with zipfile.ZipFile(bundle) as zipped:
                self.assertEqual(zipped.namelist(), ["summary.json"])


if __name__ == "__main__":
    unittest.main()
