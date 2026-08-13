"""Scores /portfolio's structural completeness against a small set of
sample inputs: are all six FTC judging-rubric categories represented, are
image references all resolvable, and does the output stay under the size
cap. Hits the real Gemini API (like eval_answers.py) -- this is a
manually-run live eval, not part of the offline test suite.

    python scripts/eval_portfolio.py --report evals/portfolio.json
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
from portfolio.compose import compose  # noqa: E402
from portfolio.extract import ExtractedText  # noqa: E402
from portfolio.render import render_html, render_markdown  # noqa: E402

_REQUIRED_CATEGORIES = ("motivate", "connect", "think", "design", "innovate", "control")

SAMPLE_CASES = [
    {
        "id": "roboctopi_style",
        "team_number": 14496,
        "season_label": "Decode (2025)",
        "instructions": "Emphasize our outreach and our control system improvements.",
        "texts": [
            ExtractedText(
                filename="notes.md",
                text=(
                    "We raised $8000 from 4 sponsors. We recruited 2 new members and 3 mentors. "
                    "Our robot uses a bi-directional arm with integrated sample and specimen "
                    "capabilities. We implemented physics-based motor control with sensor fusion "
                    "between odometry and IMU for improved localization accuracy. We organized an "
                    "official off-season event with 12 teams and over 500 participants."
                ),
            ),
        ],
    },
    {
        "id": "sparse_input",
        "team_number": 21333,
        "season_label": "Into the Deep (2024)",
        "instructions": "",
        "texts": [ExtractedText(filename="notes.md", text="We are a rookie team building our first robot.")],
    },
]


def _score_case(case: dict) -> dict:
    doc, images = compose(
        team_number=case["team_number"],
        season_label=case["season_label"],
        instructions=case.get("instructions", ""),
        texts=case.get("texts", []),
        images=case.get("images", []),
        captions=case.get("captions", {}),
    )
    html_doc = render_html(doc, images)
    render_markdown(doc)  # exercise the second output path too

    titles = " ".join(p.title.lower() for p in doc.pages)
    covered = [c for c in _REQUIRED_CATEGORIES if c in titles]

    referenced_indices = set()
    for page in doc.pages:
        for block in page.blocks:
            if block.kind == "figure_grid":
                referenced_indices.update(block.images)
    unresolved = sorted(i for i in referenced_indices if i < 0 or i >= len(images))

    size_mb = len(html_doc.encode("utf-8")) / (1024 * 1024)

    return {
        "id": case["id"],
        "ok": True,
        "n_pages": len(doc.pages),
        "categories_covered": covered,
        "categories_missing": [c for c in _REQUIRED_CATEGORIES if c not in covered],
        "unresolved_image_refs": unresolved,
        "output_size_mb": round(size_mb, 3),
        "under_size_cap": size_mb <= config.PORTFOLIO_MAX_OUTPUT_MB,
    }


def run(cases: list[dict]) -> list[dict]:
    results = []
    for case in cases:
        try:
            results.append(_score_case(case))
        except Exception as exc:
            results.append({"id": case["id"], "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", help="path to write JSON results")
    args = p.parse_args()

    results = run(SAMPLE_CASES)

    for r in results:
        if not r["ok"]:
            print(f"[{r['id']}] FAILED: {r['error']}")
            continue
        print(
            f"[{r['id']}] pages={r['n_pages']} missing={r['categories_missing']} "
            f"unresolved_image_refs={r['unresolved_image_refs']} "
            f"size={r['output_size_mb']}MB under_cap={r['under_size_cap']}"
        )

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote {args.report}")


if __name__ == "__main__":
    main()
