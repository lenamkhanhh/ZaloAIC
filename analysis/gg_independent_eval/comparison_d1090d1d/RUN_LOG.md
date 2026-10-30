# Comparison run log

started: 2026-10-30T01:09:17+0000
python: 3.12.3 (/usr/bin/python3)

## Snapshots
baseline:  4bd95a51f713cd8c6cbfa984baab23bf4a753d89  (dir /home/hatch/workspace/zaic-eval/baseline/lifemate)
candidate: d1090d1d2c78d1354c653826d8b1d96e1c107ec8 (dir /home/hatch/workspace/zaic-eval/candidate/lifemate)

## lifemate_*.py sha256 (files actually imported)
baseline:
  lifemate_callback_negation.py: b240b805c9c113f2220f3ab86b4ceea059f79d0f2827cd45aac353a138b11fdb
  lifemate_evidence_lifecycle.py: 6c5f43dd421f4a737549a68f46ccfd64978fed7354a1f4fcce02048bce503ce3
  lifemate_gates.py: 7a9fc216146824f9bb62d4f704c6996b4972654e44eec11e1b911960aed08100
  lifemate_gates_adapter.py: ef9cd90155c49ad00ab4566a9898c3bc94590c83ef5b96a27c17363c9a778911
  lifemate_phone_callback_evidence.py: f0e9117fb0aa14e09d0e9261e61ca8c41e10e753c474039af84d2ed658e7c5bc
  lifemate_provenance.py: 009b4dddeeae54fc620cb275a64b0c73b12ce4d20229014fc3f166589fb1ff29
candidate:
  lifemate_callback_negation.py: 5aa575c82e95b64a1b50ee3e8ee0fe38b5fe58f541ba0f4a14a230c6e4e591b8
  lifemate_evidence_lifecycle.py: 12c231206d3d1e6b4b65cd30eb168b5ee20caff1f675d673691bb459476d01ad
  lifemate_gates.py: 7a9fc216146824f9bb62d4f704c6996b4972654e44eec11e1b911960aed08100
  lifemate_gates_adapter.py: 0c0ac0ee6316d422ed75954e270bc5e956efc37b1268eca8a8118d012b69b4af
  lifemate_phone_callback_evidence.py: f0e9117fb0aa14e09d0e9261e61ca8c41e10e753c474039af84d2ed658e7c5bc
  lifemate_provenance.py: c36da2645e196acfb1e94abea2396be0041e9526f8f5cc3946ea9343fd7be107

## Commands (separate processes, no shared module cache)
baseline:  /usr/bin/python3 /home/hatch/workspace/zaic-eval/work/analysis/gg_independent_eval/challenge_suite.py --lifemate-dir /home/hatch/workspace/zaic-eval/baseline/lifemate --baseline-sha 4bd95a51f713cd8c6cbfa984baab23bf4a753d89 --sealed /home/hatch/workspace/zaic-eval/sealed/sealed_cases.py --out /home/hatch/workspace/zaic-eval/work/analysis/gg_independent_eval/comparison_d1090d1d/baseline_results.json
  -> returncode 1, 0.1s
candidate: /usr/bin/python3 /home/hatch/workspace/zaic-eval/work/analysis/gg_independent_eval/challenge_suite.py --lifemate-dir /home/hatch/workspace/zaic-eval/candidate/lifemate --baseline-sha d1090d1d2c78d1354c653826d8b1d96e1c107ec8 --sealed /home/hatch/workspace/zaic-eval/sealed/sealed_cases.py --out /home/hatch/workspace/zaic-eval/work/analysis/gg_independent_eval/comparison_d1090d1d/candidate_results.json
  -> returncode 1, 0.2s

## Case counts
baseline:  {'PASS': 34, 'FAIL': 10, 'KNOWN-OPEN-FAIL': 2, 'RECORDED': 10}
candidate: {'PASS': 35, 'FAIL': 10, 'KNOWN-OPEN-FAIL': 1, 'RECORDED': 10}
changed verdicts: 1
