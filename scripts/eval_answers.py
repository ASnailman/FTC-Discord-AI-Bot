"""Score ask_bot()'s actual answers against the golden Q/A set. Requires a
real Gemini call per question (GOOGLE_API_KEY) and an already-seeded
ChromaDB store (see scripts/reindex.py) -- this is the live tier.

    python scripts/reindex.py --wipe --teams 14469,21333,9295,112 --seasons 2022,2024,2025
    python scripts/eval_answers.py --mode after --runs 3 --report evals/after_answers.json

`--mode before` calls ask_bot() with team_nums=None, reproducing the
original unfiltered retrieval exactly, so both modes exercise the same code
path with only the filter toggled.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rag_chain import ask_bot  # noqa: E402

GOLDEN_PATH = ROOT / "tests" / "fixtures" / "golden" / "qa_golden.yaml"


def score_answer(answer: str, case: dict) -> dict:
    lower = answer.lower()
    required_present = all(s.lower() in lower for s in case.get("must_contain", []))
    forbidden_absent = not any(s.lower() in lower for s in case.get("must_not_contain", []))
    truncated = not answer.rstrip().endswith((".", "!", "?", '"', "'"))
    return {
        "required_facts_present": required_present,
        "forbidden_facts_absent": forbidden_absent,
        "truncated": truncated,
        "length": len(answer),
    }


def run_case(case, mode, runs):
    team_nums = None if mode == "before" else ([case["team"]] if case.get("team") else None)
    season = None if mode == "before" else case.get("season")
    region = case.get("region", "All")

    attempts = []
    for _ in range(runs):
        start = time.time()
        try:
            answer = ask_bot(case["question"], team_nums=team_nums, season=season, region=region)
        except Exception as e:  # noqa: BLE001
            answer = f"__ERROR__: {e}"
        latency = time.time() - start
        scored = score_answer(answer, case)
        scored["latency_s"] = round(latency, 2)
        scored["answer"] = answer
        attempts.append(scored)
    return attempts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["before", "after"], required=True)
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--report")
    args = p.parse_args()

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        cases = [c for c in yaml.safe_load(f) if c.get("expect_type") != "refusal"]

    all_results = {}
    for case in cases:
        print(f"Running [{case['id']}]...")
        all_results[case["id"]] = run_case(case, args.mode, args.runs)

    n_cases = len(cases)
    n_runs = args.runs
    total = n_cases * n_runs

    required_ok = sum(1 for r in all_results.values() for a in r if a["required_facts_present"])
    forbidden_ok = sum(1 for r in all_results.values() for a in r if a["forbidden_facts_absent"])
    truncated = sum(1 for r in all_results.values() for a in r if a["truncated"])
    errored = sum(1 for r in all_results.values() for a in r if a["answer"].startswith("__ERROR__"))
    latencies = sorted(a["latency_s"] for r in all_results.values() for a in r)

    stable_cases = 0
    for case_id, attempts in all_results.items():
        # crude stability check: do all runs for this case agree on required-facts presence?
        if len({a["required_facts_present"] for a in attempts}) == 1:
            stable_cases += 1

    def pct(n):
        return round(n / total, 3) if total else 0.0

    def p_at(pctl):
        if not latencies:
            return None
        idx = min(len(latencies) - 1, int(len(latencies) * pctl))
        return round(latencies[idx], 2)

    summary = {
        "mode": args.mode,
        "n_cases": n_cases,
        "runs_per_case": n_runs,
        "required_facts_present_rate": pct(required_ok),
        "forbidden_facts_absent_rate": pct(forbidden_ok),
        "truncation_rate": pct(truncated),
        "error_rate": pct(errored),
        "answer_stability": round(stable_cases / n_cases, 3) if n_cases else 1.0,
        "p50_latency_s": p_at(0.5),
        "p95_latency_s": p_at(0.95),
        "results": all_results,
    }

    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\nWrote {args.report}")


if __name__ == "__main__":
    main()
