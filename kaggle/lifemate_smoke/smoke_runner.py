"""Private, bounded GPU smoke. Standard-library imports until setup finishes.

The notebook embeds this file verbatim. No training or competition submission.
"""
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
import zipfile

REPO_COMMIT = "a9d48d24021cb91efef7d50cbc3d18ad98ed5b89"
DATA_URL = "https://dl-challenge.zalo.ai/2026/lifemate_argfzdgert/train+public_test.zip"
DATA_BYTES = 876430231
DATA_SHA256 = "57d371518996ec70d3af86402b7eba61208093c82955b9807a7ab39604b47320"
ASR_REVISION = "a86b604c346caf7148c37512eafe783a16420adb"
LLM_REVISION = "cdbee75"
SAMPLE_PLAN = [
    {"id": "train_0019", "group": "empty"},
    {"id": "train_0116", "group": "ask_only"},
    {"id": "train_0025", "group": "ask_after"},
    {"id": "train_0003", "group": "multi_step"},
    {"id": "train_0008", "group": "history"},
]
PACKAGES = ["transformers==4.57.6", "accelerate==1.10.1",
            "huggingface-hub==0.36.0", "jsonschema==4.25.1", "rapidfuzz==3.14.3"]
SAMPLE_DEBUG_SECONDS = 180  # soft guard, not the official A30 30-second limit


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract(archive, target):
    target = Path(target).resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if not (target / member.filename).resolve().is_relative_to(target):
                raise ValueError(f"Unsafe archive path: {member.filename}")
        zipped.extractall(target)


def run_command(command, log):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path(log).write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}; see {Path(log).name}")


def make_bundle(output):
    bundle = Path(output) / "smoke_artifacts.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(Path(output).rglob("*")):
            if path.is_file() and path != bundle:
                zipped.write(path, path.relative_to(output))
    return bundle


def main():
    work = Path(os.environ.get("LIFEMATE_SMOKE_INPUTS", "/kaggle/temp/lifemate-smoke"))
    output = Path(os.environ.get("LIFEMATE_SMOKE_OUTPUT", "/kaggle/working/lifemate_smoke"))
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    summary = {"status": "RUNNING", "evidence": "GPU_SMOKE_NOT_BENCHMARK",
               "source_commit": REPO_COMMIT, "sample_plan": SAMPLE_PLAN,
               "seed": 42, "history_policy": "ASR for all user audio, including train history",
               "hardware_is_a30": False, "records": []}
    write_json(output / "summary.json", summary)
    started = time.perf_counter()

    def phase(name):
        summary["phase"] = name
        summary["elapsed_seconds"] = time.perf_counter() - started
        write_json(output / "summary.json", summary)
        print(f"PHASE {name} elapsed={summary['elapsed_seconds']:.1f}s", flush=True)

    try:
        phase("dependencies")
        os.environ.update({"USE_TF": "0", "USE_FLAX": "0", "HF_HUB_DISABLE_TELEMETRY": "1",
                           "HF_HUB_DISABLE_XET": "1", "TOKENIZERS_PARALLELISM": "false"})
        # This isolated audio/text notebook does not need torchvision. Remove
        # that optional dependency to avoid an unrelated torchvision::nms ABI error.
        run_command([sys.executable, "-m", "pip", "uninstall", "-y", "torchvision"], output / "remove_optional_vision.log")
        run_command([sys.executable, "-m", "pip", "install", "-q", *PACKAGES], output / "dependencies.log")

        phase("hardware_preflight")
        import importlib.metadata
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("No CUDA GPU; stop before downloading data/weights")
        if torch.cuda.device_count() < 2:
            raise RuntimeError("This smoke placement requires the requested two T4 GPUs")
        version = tuple(int(p) for p in torch.__version__.split("+")[0].split(".")[:2])
        if version < (2, 6):
            raise RuntimeError("PhoWhisper pytorch_model.bin requires torch >= 2.6; no automatic torch replacement")
        gpu = torch.cuda.get_device_properties(0)
        if gpu.total_memory < 14 * 1024**3:
            raise RuntimeError("GPU0 has insufficient memory for this unquantized smoke")
        summary["environment"] = {
            "python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda,
            "gpu0": gpu.name, "gpu0_bytes": gpu.total_memory, "gpu_count": torch.cuda.device_count(),
            "device_used": "ASR cuda:0; LLM balanced across cuda:0 and cuda:1", "packages": {p.split("==")[0]: importlib.metadata.version(p.split("==")[0]) for p in PACKAGES},
        }

        phase("source")
        source_zip = work / "source.zip"
        run_command(["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
                     "-o", str(source_zip), f"https://codeload.github.com/lenamkhanhh/ZaloAIC/zip/{REPO_COMMIT}"], output / "source_download.log")
        safe_extract(source_zip, work / "source")
        repo = work / "source" / f"ZaloAIC-{REPO_COMMIT}"
        if not (repo / "lifemate" / "run.py").is_file():
            raise RuntimeError("Pinned source archive does not have expected layout")
        summary["source_archive_sha256"] = sha256(source_zip)
        sys.path.insert(0, str(repo))

        phase("data_download_and_verify")
        data_zip = work / "train+public_test.zip"
        for attempt in range(3):
            try:
                run_command(["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
                             "--connect-timeout", "30", "--max-time", "900", "--continue-at", "-",
                             "-o", str(data_zip), DATA_URL], output / f"data_download_{attempt}.log")
                break
            except RuntimeError:
                if attempt == 2:
                    raise
        if data_zip.stat().st_size != DATA_BYTES or sha256(data_zip) != DATA_SHA256:
            raise RuntimeError("Dataset identity mismatch; do not run models")
        summary["dataset"] = {"bytes": DATA_BYTES, "sha256": DATA_SHA256}
        safe_extract(data_zip, work / "data")
        data = work / "data" / "train+public_test"
        summary["dataset"]["version"] = (data / "VERSION").read_text(encoding="utf-8")

        from lifemate.loader import load_catalog, load_split, catalog_tools_for_sample
        from lifemate.config import PipelineConfig
        from lifemate.adapter import ZaicEnv
        from lifemate.agent import AgentLoop
        from lifemate.asr import build_asr
        from lifemate.llm import build_generator
        from lifemate.scoring import score_sample

        assignment_file = repo / "lifemate" / "splits" / "train_dev_heldout.json"
        assignment = json.loads(assignment_file.read_text())
        by_id = {s.id: s for s in load_split(data, "train")}
        for item in SAMPLE_PLAN:
            if item["id"] not in by_id or assignment[item["id"]] != "dev":
                raise RuntimeError("Smoke plan contains a missing or non-dev ID")
        summary["split_assignment_sha256"] = sha256(assignment_file)
        catalog = load_catalog(data, "train")
        from lifemate.loader import fuzzy_params
        fuzzy = fuzzy_params(catalog)

        phase("weights")
        from huggingface_hub import snapshot_download
        allow = ["*.json", "*.safetensors", "*.bin", "*.txt", "*.model", "*.jinja"]
        asr_path = snapshot_download("vinai/PhoWhisper-small", revision=ASR_REVISION, allow_patterns=allow)
        llm_path = snapshot_download("Qwen/Qwen3-4B-Instruct-2507", revision=LLM_REVISION, allow_patterns=allow)
        summary["models"] = {"asr": "vinai/PhoWhisper-small", "asr_revision": ASR_REVISION,
                             "llm": "Qwen/Qwen3-4B-Instruct-2507", "llm_snapshot": Path(llm_path).name}
        config = PipelineConfig.from_json(repo / "lifemate" / "configs" / "recommended.json")
        config.asr_checkpoint, config.llm_checkpoint = asr_path, llm_path
        config.asr_backend, config.llm_backend = "transformers", "transformers"
        # V1 loaded both models but 4/5 prompts exhausted GPU0 attention
        # memory. Preserve FP16 weights/seed/prompt; distribute weights to
        # leave activation headroom on both assigned T4s. Not an A30 test.
        config.llm_device_map = "balanced"
        config.llm_max_memory_gib = {"0": 6, "1": 6}
        config.local_files_only = True
        config.check_budget()
        write_json(output / "resolved_config.json", dataclasses.asdict(config))

        phase("load_models")
        load_start = time.perf_counter()
        asr = build_asr(config, device="cuda:0")
        llm = build_generator(config, device="cuda:0")
        summary["llm_device_map"] = getattr(llm.model, "hf_device_map", {})
        summary["model_load_seconds"] = time.perf_counter() - load_start
        raw_text = {"value": None}
        original_decode = llm.tokenizer.decode

        def traced_decode(*args, **kwargs):
            text = original_decode(*args, **kwargs)
            raw_text["value"] = text
            return text
        llm.tokenizer.decode = traced_decode

        phase("inference_dev5")
        with open(output / "submission.jsonl", "w", encoding="utf-8") as submission:
            for item in SAMPLE_PLAN:
                sample = copy.deepcopy(by_id[item["id"]])
                record = {**item, "trace": [], "history_asr": [], "gold_transcript": sample.audio_text}
                env = ZaicEnv(data, "train", sample.id)
                sample_start = time.perf_counter()
                for device in (0, 1):
                    with torch.cuda.device(device):
                        torch.cuda.empty_cache()
                        torch.cuda.reset_peak_memory_stats(device)
                try:
                    tick = time.perf_counter()
                    transcript = asr.transcribe(data / "train" / sample.audio)
                    record.update({"asr_transcript": transcript, "asr_current_seconds": time.perf_counter() - tick})
                    for turn in sample.history:
                        if turn.role == "user" and turn.audio:
                            tick = time.perf_counter()
                            gold_text = turn.audio_text
                            turn.audio_text = asr.transcribe(data / "train" / turn.audio)
                            record["history_asr"].append({"audio": turn.audio, "gold": gold_text,
                                                          "asr": turn.audio_text, "seconds": time.perf_counter() - tick})
                    tools = catalog_tools_for_sample(catalog, sample)
                    original_call, original_validate = env.call, env.validate

                    def call(name, arguments):
                        result = original_call(name, arguments)
                        record["trace"].append({"event": "tool", "name": name, "arguments": arguments, "result": result})
                        return result

                    def validate(name, arguments):
                        result = original_validate(name, arguments)
                        if not result.get("ok"):
                            record["trace"].append({"event": "validation_rejected", "name": name,
                                                    "arguments": arguments, "result": result})
                        return result

                    env.call, env.validate = call, validate

                    def generate(prompt, tools):
                        if time.perf_counter() - sample_start > SAMPLE_DEBUG_SECONDS:
                            raise TimeoutError("180-second smoke debug budget exceeded (not an A30 timing claim)")
                        tick = time.perf_counter()
                        raw_text["value"] = None
                        try:
                            result = llm(prompt, tools)
                        except Exception as exc:
                            record["trace"].append({"event": "generation_error", "prompt": prompt,
                                                    "error": repr(exc), "seconds": time.perf_counter() - tick})
                            raise
                        record["trace"].append({"event": "generation", "prompt": prompt, "parsed": result,
                                                "raw_text": raw_text["value"], "seconds": time.perf_counter() - tick})
                        return result

                    line = AgentLoop(config, tools).run(sample, transcript, env, generate)
                    record["status"] = "INFERRED"
                except Exception:
                    line = env.submission_line()
                    record.update({"status": "ERROR", "error": traceback.format_exc()})
                record["inference_seconds"] = time.perf_counter() - sample_start
                record["gpu_peak_allocated_bytes"] = {str(device): torch.cuda.max_memory_allocated(device) for device in (0, 1)}
                # Gold is replayed only after inference, on a separate diagnostic env.
                gold_env = ZaicEnv(data, "train", sample.id)
                for gold_call in sample.label["tool_calls"]:
                    gold_env.call(gold_call["name"], gold_call["arguments"])
                record["proxy"] = score_sample(line, sample, gold_env.state_hash(), fuzzy)
                record["gold_tool_calls"] = sample.label["tool_calls"]
                record["submission"] = line
                submission.write(json.dumps(line, ensure_ascii=False) + "\n")
                submission.flush()
                write_json(output / f"{sample.id}.json", record)
                summary["records"].append({k: record[k] for k in ("id", "group", "status", "inference_seconds", "proxy")})
                write_json(output / "summary.json", summary)
                print(f"SAMPLE {sample.id} {record['status']} proxy={record['proxy']['score']:.4f} seconds={record['inference_seconds']:.1f}", flush=True)

        summary["status"] = "SMOKE_COMPLETED" if all(r["status"] == "INFERRED" for r in summary["records"]) else "SMOKE_HAS_ERRORS"
        summary["proxy_mean"] = sum(r["proxy"]["score"] for r in summary["records"]) / len(SAMPLE_PLAN)
        summary["is_official_score"] = False
        summary["is_baseline_quality_estimate"] = False
        summary["phase"] = "finished"
        if summary["status"] != "SMOKE_COMPLETED":
            raise RuntimeError("Some samples failed; inspect artifact traces before any rerun")
    except Exception:
        summary["status"] = "FAILED" if not summary["records"] else "SMOKE_HAS_ERRORS"
        summary["fatal_error"] = traceback.format_exc()
        raise
    finally:
        summary["elapsed_seconds"] = time.perf_counter() - started
        write_json(output / "summary.json", summary)
        bundle = make_bundle(output)
        print(f"ARTIFACTS {bundle}", flush=True)


if __name__ == "__main__":
    main()
