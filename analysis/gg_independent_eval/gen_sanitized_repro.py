#!/usr/bin/env python3
"""Generate verified sanitized repros for sealed findings.

Writes fresh minimal examples (NOT the sealed fixture texts) that
demonstrate the same bug patterns, with outputs verified against the
given snapshot. Output: sealed_repro_sanitized.md (safe to publish).

Usage:
  python3 gen_sanitized_repro.py --lifemate-dir <dir> --sha <full sha>
      --out <md path>
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROBE = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from lifemate_gates_adapter import decide

N = "0903111444"
KINDS = {"phone.call": "write"}
CALL = {"name": "phone.call", "arguments": {"phone_number": N}}

def run(text, prefix):
    d = decide(CALL, prefix, [], text, KINDS,
               proposal_position=len(prefix))
    adj = d.adjustments[0] if d.adjustments else {}
    return {"fired": d.fired, "baseline_fired": d.baseline_fired,
            "selection": adj.get("selection"),
            "selection_reason": adj.get("selection_reason"),
            "mechanism": adj.get("mechanism")}

cases = [
    ("control-negation",
     "Đừng gọi số 0903111444", []),
    ("SEAL-003/emphatic-dung-co-ma",
     "Đừng có mà gọi số 0903111444 đấy", []),
    ("SEAL-003/emphatic-dung-ma",
     "Đừng mà gọi số 0903111444", []),
    ("control-wh-question",
     "Gọi số nào?",
     [{"kind": "user_turn", "text": "Gọi số 0903111444 giúp tôi",
       "position": 0}]),
    ("SEAL-004/wh-nhi-echo",
     "Lúc nãy em bảo gọi số 0903111444 nhỉ?",
     [{"kind": "user_turn", "text": "Gọi số 0903111444 giúp tôi",
       "position": 0}]),
]
out = [{"label": l, "text": t,
        "prefix": p, "result": run(t, p)} for l, t, p in cases]
print(json.dumps(out, ensure_ascii=False))
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lifemate-dir", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    proc = subprocess.run(
        [sys.executable, "-c", PROBE, args.lifemate_dir],
        capture_output=True, text=True, timeout=120,
        cwd=tempfile.mkdtemp())
    if proc.returncode != 0:
        raise SystemExit("probe failed: " + proc.stderr[-1000:])
    rows = json.loads(proc.stdout)

    lines = [
        "# Sanitized repros — sealed contract findings (candidate "
        + args.sha[:8] + ")",
        "",
        "Fresh minimal examples (NOT the sealed fixture texts) reproducing",
        "the two sealed contract bugs. Verified against snapshot "
        + args.sha + ".",
        "Each call: `decide({name: phone.call, phone_number: 0903111444},",
        "prefix, roster=[], text, kinds, proposal_position=len(prefix))`.",
        "Baseline fires in all rows (unestablished reference, empty",
        "roster); the question is whether the candidate keeps the fire.",
        "",
    ]
    for r in rows:
        res = r["result"]
        lines += [
            f"## {r['label']}",
            f"- text: `{r['text']}`",
            f"- prefix: `{json.dumps(r['prefix'], ensure_ascii=False)}`",
            f"- fired={res['fired']} (baseline_fired={res['baseline_fired']})",
            f"- selection={res['selection']} "
            f"reason={res['selection_reason']} "
            f"mechanism={res['mechanism']}",
            "",
        ]
    lines += [
        "## Reading",
        "- control-negation: plain `Đừng gọi` keeps the fire (correct —",
        "  the negation vetoes the callback un-fire).",
        "- SEAL-003 rows: emphatic `đừng (có) mà` is MISSED as negation;",
        "  the number is read as positive selection and the fire is",
        "  wrongly un-fired (fired=False).",
        "- control-wh-question: `Gọi số nào?` keeps the fire (correct).",
        "- SEAL-004 row: `... số 0903111444 nhỉ?` (wh-question echoing the",
        "  number with the `nhỉ` particle) is read as positive selection;",
        "  the fire is wrongly un-fired. The question inventory covers",
        "  `có…không`/`hả`/`chứ`/`có được không` but not this construction.",
    ]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
