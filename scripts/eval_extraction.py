"""Measure extract_info's precision/recall against the golden dataset.

Fully offline -- no network, no API key. Run any time:

    python scripts/eval_extraction.py --report evals/extraction.json
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from extraction import extract_team_numbers  # noqa: E402
from _original_extract_info import extract_info_original  # noqa: E402

GOLDEN_PATH = ROOT / "tests" / "fixtures" / "golden" / "extract_info_cases.yaml"
INDEX_PATH = ROOT / "tests" / "fixtures" / "teams_index" / "USIL.json"


def run(cases, index, mode="after"):
    extractor = extract_info_original if mode == "before" else extract_team_numbers

    confusions = []
    tag_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    tp = fp = fn = 0
    exact_matches = 0

    for case in cases:
        got = set(extractor(case["question"], index))
        expected = set(case["expect"])

        case_tp = len(got & expected)
        case_fp = len(got - expected)
        case_fn = len(expected - got)

        tp += case_tp
        fp += case_fp
        fn += case_fn
        if got == expected:
            exact_matches += 1

        for tag in case.get("tags", []):
            tag_stats[tag]["tp"] += case_tp
            tag_stats[tag]["fp"] += case_fp
            tag_stats[tag]["fn"] += case_fn

        if got != expected:
            confusions.append({
                "id": case["id"], "question": case["question"],
                "expected": sorted(expected), "got": sorted(got),
                "spurious": sorted(got - expected), "missed": sorted(expected - got),
            })

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 1.0

    per_tag = {}
    for tag, s in tag_stats.items():
        p = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else 1.0
        r = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) else 1.0
        per_tag[tag] = {"precision": round(p, 3), "recall": round(r, 3)}

    return {
        "n_cases": len(cases),
        "exact_match_rate": round(exact_matches / len(cases), 3) if cases else 1.0,
        "micro_precision": round(precision, 3),
        "micro_recall": round(recall, 3),
        "micro_f1": round(f1, 3),
        "per_tag": per_tag,
        "confusions": confusions,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["before", "after"], default="after",
                   help="'before' runs the original pre-fix algorithm for comparison")
    p.add_argument("--report", help="path to write JSON results")
    args = p.parse_args()

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        cases = yaml.safe_load(f)
    with open(INDEX_PATH, encoding="utf-8") as f:
        index = json.load(f)

    results = run(cases, index, mode=args.mode)
    results["mode"] = args.mode

    print(f"Mode: {args.mode}")
    print(f"Cases: {results['n_cases']}  Exact-match rate: {results['exact_match_rate']}")
    print(f"Micro precision: {results['micro_precision']}  recall: {results['micro_recall']}  f1: {results['micro_f1']}")
    print("\nPer-tag:")
    for tag, s in sorted(results["per_tag"].items()):
        print(f"  {tag:25s} precision={s['precision']:.3f} recall={s['recall']:.3f}")
    if results["confusions"]:
        print(f"\n{len(results['confusions'])} case(s) with mismatches:")
        for c in results["confusions"]:
            print(f"  [{c['id']}] {c['question']!r} -> got={c['got']} expected={c['expected']} "
                  f"spurious={c['spurious']} missed={c['missed']}")

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote {args.report}")


if __name__ == "__main__":
    main()
