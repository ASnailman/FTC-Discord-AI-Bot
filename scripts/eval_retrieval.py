"""Measure retrieval quality: does the vector search return chunks that
actually belong to the asked team+season, or does it pull in noise from
every other team ever cached?

Builds a mixed corpus (multiple teams, multiple seasons -- mirrors
production reality) in a temporary Chroma store using the deterministic
hash embedding function (no model download, no API cost), then runs each
golden question through the retriever with and without the metadata filter.

    python scripts/eval_retrieval.py --mode before --report evals/before_retrieval.json
    python scripts/eval_retrieval.py --mode after  --report evals/after_retrieval.json
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402

from tests.support.embeddings import DeterministicHashEmbeddingFunction  # noqa: E402
from vectordb import VectorDBManager  # noqa: E402
from rag_chain import _build_where  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "ftcscout"
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "golden" / "qa_golden.yaml"

CORPUS_FIXTURES = [
    ("team_14469_2022.json", 14469, 2022),
    ("team_14469_2025.json", 14469, 2025),
    ("team_21333_2024.json", 21333, 2024),
    ("team_9295_2025.json", 9295, 2025),
    ("team_112_2022.json", 112, 2022),
]


def build_corpus(tmp_dir):
    client = chromadb.PersistentClient(path=str(tmp_dir))
    manager = VectorDBManager(client=client, embedding_function=DeterministicHashEmbeddingFunction())
    for fname, team, season in CORPUS_FIXTURES:
        with open(FIXTURES / fname, encoding="utf-8") as f:
            raw = json.load(f)
        manager.upsert_team_data(raw, season=season, region="All")
    return manager


def evaluate_case(manager, case, k, filtered):
    where = _build_where([case["team"]], case["season"]) if filtered else None
    search_kwargs = {"where": where} if where else {}
    result = manager.collection.query(
        query_texts=[case["question"]], n_results=k, include=["metadatas", "documents"], **search_kwargs,
    )
    metadatas = result["metadatas"][0] if result["metadatas"] else []
    documents = result["documents"][0] if result["documents"] else []

    if not metadatas:
        return {"team_precision": 0.0, "season_precision": 0.0, "context_purity": 0.0,
                "n_foreign_teams": 0, "wasted_context_chars": 0, "facts_chunk_in_topk": False, "n_retrieved": 0}

    team_match = [m["team"] == case["team"] for m in metadatas]
    season_match = [m["season"] == case["season"] for m in metadatas]
    both = [t and s for t, s in zip(team_match, season_match)]

    foreign_teams = {m["team"] for m in metadatas if m["team"] != case["team"]}
    wasted_chars = sum(len(d) for d, ok in zip(documents, both) if not ok)
    facts_id = f"{case['team']}|{case['season']}|facts"
    facts_in_topk = any(
        m.get("type") == "season_facts" and m["team"] == case["team"] and m["season"] == case["season"]
        for m in metadatas
    )

    n = len(metadatas)
    return {
        "team_precision": sum(team_match) / n,
        "season_precision": sum(season_match) / n,
        "context_purity": sum(both) / n,
        "n_foreign_teams": len(foreign_teams),
        "wasted_context_chars": wasted_chars,
        "facts_chunk_in_topk": facts_in_topk,
        "n_retrieved": n,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["before", "after"], required=True)
    p.add_argument("--k", type=int, default=40)
    p.add_argument("--report")
    args = p.parse_args()

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        cases = [c for c in yaml.safe_load(f) if c.get("team") is not None]

    tmp = tempfile.mkdtemp()
    manager = None
    try:
        manager = build_corpus(Path(tmp))
        per_case = {}
        for case in cases:
            per_case[case["id"]] = evaluate_case(manager, case, args.k, filtered=(args.mode == "after"))
    finally:
        del manager
        shutil.rmtree(tmp, ignore_errors=True)

    def avg(key):
        vals = [v[key] for v in per_case.values()]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    summary = {
        "mode": args.mode,
        "k": args.k,
        "n_cases": len(cases),
        "team_precision_at_k": avg("team_precision"),
        "season_precision_at_k": avg("season_precision"),
        "context_purity_at_k": avg("context_purity"),
        "facts_chunk_in_topk_rate": round(
            sum(1 for v in per_case.values() if v["facts_chunk_in_topk"]) / len(per_case), 3
        ) if per_case else 0.0,
        "avg_foreign_teams_in_context": avg("n_foreign_teams"),
        "avg_wasted_context_chars": avg("wasted_context_chars"),
        "per_case": per_case,
    }

    print(json.dumps({k: v for k, v in summary.items() if k != "per_case"}, indent=2))
    print(
        "\nNote: facts_chunk_in_topk_rate measures whether pure similarity "
        "ranking surfaces the aggregate-facts chunk on its own -- this is "
        "expected to stay low even after filtering, which is exactly why "
        "ask_bot() force-includes it via a direct id lookup instead of "
        "relying on retrieval to find it."
    )

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\nWrote {args.report}")


if __name__ == "__main__":
    main()
