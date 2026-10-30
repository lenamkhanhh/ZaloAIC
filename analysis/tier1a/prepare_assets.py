"""Prepare Linux/Python 3.13 wheels and pinned HF snapshots on a CPU host.

Use in a CPU Kaggle session; publish the resulting directory as a PRIVATE
input only after it contains READY.json. No model is loaded here.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

PACKAGES = ["vllm==0.10.2", "torch==2.8.0", "torchaudio==2.8.0",
            "torchvision==0.23.0", "transformers==4.56.2", "accelerate==1.10.1",
            "faster-whisper==1.2.1", "numpy<2.3"]
MODELS = [("asr", "vinai/PhoWhisper-small", "a86b604"),
          ("llm", "Qwen/Qwen3-4B-Instruct-2507", "cdbee75")]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--plan", action="store_true")
    args = p.parse_args()
    root = Path(args.out)
    if args.plan:
        print(json.dumps({"packages": PACKAGES, "models": MODELS,
                          "requires": "Linux x86_64 Python 3.13 CPU host",
                          "output": str(root)}, indent=2))
        return
    if platform.system() != "Linux" or sys.version_info[:2] != (3, 13):
        raise SystemExit("Prepare on Linux Python 3.13 to match the measured Kaggle image.")
    root.mkdir(parents=True, exist_ok=True)
    ready = root / "READY.json"
    ready.unlink(missing_ok=True)
    wheels = root / "wheels"
    wheels.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:",
                    "--dest", str(wheels), *PACKAGES], check=True)
    from huggingface_hub import HfApi, snapshot_download
    revisions = {}
    for name, model, revision in MODELS:
        full_revision = HfApi().model_info(model, revision=revision).sha
        revisions[name] = {"model": model, "revision": full_revision}
        snapshot_download(model, revision=full_revision, local_dir=root / name,
                          allow_patterns=["*.json", "*.jinja", "*.safetensors",
                                          "*.bin", "*.txt", "*.model"])
    inventory = []
    for file in sorted(root.rglob("*")):
        if not file.is_file() or ".cache" in file.parts:
            continue
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        inventory.append({"path": file.relative_to(root).as_posix(),
                          "bytes": file.stat().st_size, "sha256": digest.hexdigest()})
    ready.write_text(json.dumps({"status": "ASSETS_DOWNLOADED_NOT_GPU_VALIDATED",
                                "python": platform.python_version(),
                                "models": revisions, "packages": PACKAGES,
                                "files": inventory}, indent=2), encoding="utf-8")
    print(ready, flush=True)


if __name__ == "__main__":
    main()
