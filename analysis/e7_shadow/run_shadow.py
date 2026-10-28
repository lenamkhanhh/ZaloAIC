"""Read-only E7 corpus audit: causal prefixes only, no executor/model/state IO."""
import argparse
from collections import Counter, defaultdict
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from analysis.e7_shadow.guard import assess
from lifemate.loader import load_catalog, load_split, catalog_tools_for_sample


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def history(sample, cached=None):
    turns = [asdict(turn) for turn in sample.history]
    if cached is not None:
        for turn in turns:
            if turn['role'] == 'user' and turn.get('audio'):
                turn['audio_text'] = cached['history_asr'][turn['audio']]
    return turns


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def run(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    assignment_path = REPO / 'lifemate/splits/train_dev_heldout.json'
    assignment = json.loads(assignment_path.read_text())
    # Loader parses the package; only dev samples are retained or assessed.
    samples = {s.id: s for s in load_split(args.data, 'train') if assignment[s.id] == 'dev'}
    catalog = load_catalog(args.data, 'train')
    cache = json.loads(Path(args.cache).read_text(encoding='utf-8'))['inputs']
    assert len(cache) == 20 and set(cache) <= set(samples)
    source_hash = sha(Path(__file__).with_name('guard.py'))
    rows, gold_rows, known, paired, paired_arguments = [], [], [], [], []
    # IDs are diagnostic manifest entries only, never passed to assess().
    known_targets = [('train_0219', 'rule'), ('train_0220', 'rule'),
                     ('train_0287', 'rule'), ('train_0360', 'rule'),
                     ('train_0780', 'rule'), ('train_0353', 'control')]
    known_seen = set()
    with zipfile.ZipFile(args.traces) as archive:
        assert archive.testzip() is None
        summary = json.loads(archive.read('summary.json'))
        assert summary['status'] == 'SMOKE_COMPLETED'
        plan = summary['sample_plan']
        assert {s['id'] for s in plan} == set(cache)
        for item in plan:
            sample = samples[item['id']]
            tools = catalog_tools_for_sample(catalog, sample)
            for arm in ('control', 'rule'):
                record = json.loads(archive.read(arm + '_' + sample.id + '.json'))
                cached = cache[sample.id]
                assert record['model_current_transcript'] == cached['current_asr']
                observations, generation = [], 0
                for event in record['trace']:
                    if event['event'] == 'tool':
                        observations.append(({'name': event['name'], 'arguments': event['arguments']}, event['result']))
                        continue
                    if event['event'] != 'generation':
                        continue
                    generation += 1
                    proposed = event['parsed']
                    if not isinstance(proposed, dict) or tools.get(proposed.get('name'), {}).get('kind') != 'write':
                        continue
                    call = {'name': proposed['name'], 'arguments': proposed.get('arguments', {})}
                    before = copy.deepcopy(call)
                    asr = assess(call, tools, cached['current_asr'], sample.context,
                                 observations=observations, history=history(sample, cached))
                    gold = assess(call, tools, sample.audio_text, sample.context,
                                  observations=observations, history=history(sample))
                    assert call == before
                    row = {'id': sample.id, 'arm': arm, 'generation': generation,
                           'tool': call['name'], 'proposed_arguments': call['arguments'],
                           'asr': asr, 'gold_text': gold,
                           'observation_prefix_length': len(observations)}
                    rows.append(row)
                    if asr['scoped']:
                        paired.append({'id': sample.id, 'arm': arm, 'generation': generation,
                                       'ASR': asr['status'], 'GOLD_TEXT': gold['status']})
                        assert set(asr['arguments']) == set(gold['arguments'])
                        for slot in asr['arguments']:
                            paired_arguments.append({'id': sample.id, 'arm': arm, 'generation': generation,
                                                     'slot': slot, 'ASR': asr['arguments'][slot],
                                                     'GOLD_TEXT': gold['arguments'][slot]})
                    identity = (sample.id, arm)
                    if identity in known_targets and identity not in known_seen and 'time' in call['arguments']:
                        known.append(row)
                        known_seen.add(identity)
    assert known_seen == set(known_targets)
    # Full-dev gold-prefix screen, excluding the20 ask-only samples. No simulator
    # call is made: each prior label result is appended ONLY after its own step.
    total_gold_writes = 0
    missing_asr_gold_writes = 0
    for sample in samples.values():
        if sample.id in cache:
            assert sample.label['tool_calls'][0]['name'] == 'sys.ask_missing_info'
            assert len(sample.label['tool_calls']) == 1
            continue
        tools = catalog_tools_for_sample(catalog, sample)
        calls, results = sample.label['tool_calls'], sample.label['tool_results']
        assert len(calls) == len(results)
        observations = []
        for index, (call, result) in enumerate(zip(calls, results)):
            if tools.get(call['name'], {}).get('kind') == 'write':
                total_gold_writes += 1
                missing_asr_gold_writes += 1
                decision = assess(call, tools, sample.audio_text, sample.context,
                                  observations=observations, history=history(sample))
                gold_rows.append({'id': sample.id, 'call_index': index, 'tool': call['name'],
                                  'arguments': call['arguments'], 'decision': decision,
                                  'ASR': 'UNAVAILABLE',
                                  'gold_result_ok': result.get('ok'),
                                  'gold_result_done': result.get('done'),
                                  'observation_prefix_length': len(observations)})
            observations.append((call, result))
    assert source_hash == sha(Path(__file__).with_name('guard.py'))
    scoped_gold = [r for r in gold_rows if r['decision']['scoped']]
    false_blocks = [r for r in scoped_gold if r['decision']['status'] == 'BLOCK']
    invalid_gold = [r for r in false_blocks if r['gold_result_ok'] is not True or r['gold_result_done'] is False]
    slots = Counter()
    for row in scoped_gold:
        for key, value in row['decision']['arguments'].items():
            slots[key, value['status'], value['reason']] += 1
    counts = lambda rs, key: dict(Counter(r[key]['status'] for r in rs if r[key]['scoped']))
    transitions = Counter((r['GOLD_TEXT'], r['ASR']) for r in paired)
    argument_transitions = Counter((r['GOLD_TEXT']['status'], r['ASR']['status']) for r in paired_arguments)
    report = {
        'scope': 'E7_PHASE0_SHADOW_ONLY_NOT_LIVE_READY', 'guard_sha256': source_hash,
        'split_sha256': sha(assignment_path), 'trace_zip_sha256': sha(args.traces),
        'dev_samples': len(samples), 'heldout_assessed': 0, 'models_run': 0, 'gpu_jobs': 0,
        'v13_traces': 40, 'v13_write_proposals': len(rows),
        'v13_scoped_proposals': sum(r['asr']['scoped'] for r in rows),
        'v13_ASR_decisions': counts(rows, 'asr'), 'v13_GOLD_TEXT_decisions': counts(rows, 'gold_text'),
        'known_fill_total': len(known),
        'known_fill_ASR_status': dict(Counter(r['asr']['status'] for r in known)),
        'gold_write_count': total_gold_writes, 'gold_scoped_writes': len(scoped_gold),
        'gold_decisions': counts(gold_rows, 'decision'), 'candidate_gold_false_blocks': len(false_blocks),
        'false_blocks_with_failed_gold_result': len(invalid_gold),
        'gold_writes_ASR_unavailable': missing_asr_gold_writes,
        'ASR_GOLD_transition_on_observed_V13_prefixes': {a + '->' + b: n for (a, b), n in transitions.items()},
        'ASR_GOLD_argument_transition_on_observed_V13_prefixes': {a + '->' + b: n for (a, b), n in argument_transitions.items()},
        'gold_scoped_arguments': sum(slots.values()),
        'gold_slot_breakdown': [{'slot': k, 'status': s, 'reason': reason, 'count': n} for (k, s, reason), n in slots.items()],
    }
    reasons = []
    if false_blocks:
        reasons.append('GOLD_CANDIDATE_FALSE_BLOCK')
    if any(r['decision']['status'] == 'UNKNOWN' for r in scoped_gold):
        reasons.append('GOLD_SOURCE_COVERAGE_UNRESOLVED')
    if any(r['asr']['status'] != 'BLOCK' for r in known):
        reasons.append('KNOWN_FILL_NOT_CONFIDENTLY_BLOCKED')
    report['gate_reasons'] = reasons
    report['gate'] = 'CPU_NOT_READY' if reasons else 'SHADOW_GATE_ONLY_NOT_GPU_AUTHORIZATION'
    save(out / 'v13_proposal_decisions.json', rows)
    save(out / 'known_fill_manifest.json', known)
    save(out / 'ASR_GOLD_argument_comparison.json', paired_arguments)
    save(out / 'gold_write_decisions.json', gold_rows)
    save(out / 'gold_candidate_false_blocks.json', false_blocks)
    save(out / 'summary.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'gold_slot_breakdown'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=REPO.parent / 'train+public_test/train+public_test')
    parser.add_argument('--traces', type=Path, default=REPO.parent / 'artifacts/lifemate-e5/result/lifemate_smoke/smoke_artifacts.zip')
    parser.add_argument('--cache', type=Path, default=REPO.parent / 'artifacts/lifemate-e5/cpu-result/e5_cpu/validated_inputs.json')
    parser.add_argument('--out', type=Path, default=REPO.parent / 'artifacts/lifemate-e7-shadow/v1')
    run(parser.parse_args())
