#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from autoresearch_function.experiment import get_best_score, latest_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Show autoresearch-function experiment status.")
    parser.add_argument(
        "--experiment",
        default="engineering/portfolio-return",
        help="Experiment path under .autoresearch/",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent rows to show.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    results_path = project_root / ".autoresearch" / args.experiment / "results.tsv"
    rows = latest_results(results_path, limit=args.limit)
    best = get_best_score(results_path)

    print(f"Experiment: {args.experiment}")
    print(f"Best overall_score: {'None' if best is None else f'{best:.6f}'}")
    print(f"Recent runs: {len(rows)}")
    print("commit\toverall_score\tcorrectness\tstatus\tdescription")
    for row in rows:
        print(
            "\t".join(
                [
                    row.get("commit", ""),
                    row.get("overall_score", ""),
                    row.get("correctness", ""),
                    row.get("status", ""),
                    row.get("description", ""),
                ]
            )
        )


if __name__ == "__main__":
    main()
