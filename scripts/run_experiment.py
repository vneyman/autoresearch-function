#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from autoresearch_function.experiment import (
    append_result,
    can_rollback_last_commit,
    current_commit,
    get_best_score,
    is_improvement,
    load_config,
    load_summary,
    rollback_last_commit,
    run_command,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one autoresearch-function experiment iteration.")
    parser.add_argument(
        "--experiment",
        default="engineering/portfolio-return",
        help="Experiment path under .autoresearch/",
    )
    parser.add_argument(
        "--description",
        default="manual benchmark run",
        help="Short description for the results log.",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the last git commit on discard/crash when possible.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    experiment_root = project_root / ".autoresearch" / args.experiment
    config = load_config(experiment_root / "config.cfg")
    results_path = experiment_root / "results.tsv"
    log_path = experiment_root / "run.log"
    summary_path = project_root / config.summary_file

    best_score = get_best_score(results_path)
    timeout_seconds = config.time_budget_minutes * 60 * 2.5

    returncode, elapsed = run_command(config.evaluate_cmd, project_root, timeout_seconds, log_path)
    commit = current_commit(project_root)

    if returncode != 0:
        append_result(results_path, commit, None, "crash", f"{args.description} (exit={returncode}, elapsed={elapsed:.1f}s)")
        if args.rollback and can_rollback_last_commit(project_root):
            rollback_last_commit(project_root)
        raise SystemExit(returncode if returncode > 0 else 1)

    summary = load_summary(summary_path)
    if summary.correctness < config.correctness_threshold:
        append_result(
            results_path,
            commit,
            summary,
            "discard",
            f"{args.description} (correctness gate: {summary.correctness:.6f})",
        )
        if args.rollback and can_rollback_last_commit(project_root):
            rollback_last_commit(project_root)
        print(f"DISCARD correctness={summary.correctness:.6f} below threshold={config.correctness_threshold:.6f}")
        return

    if is_improvement(config.metric_direction, summary.overall_score, best_score):
        append_result(results_path, commit, summary, "keep", args.description)
        baseline_text = "None" if best_score is None else f"{best_score:.6f}"
        print(f"KEEP overall_score={summary.overall_score:.6f} best={baseline_text}")
        return

    append_result(
        results_path,
        commit,
        summary,
        "discard",
        f"{args.description} (no improvement over {best_score:.6f})",
    )
    if args.rollback and can_rollback_last_commit(project_root):
        rollback_last_commit(project_root)
    print(f"DISCARD overall_score={summary.overall_score:.6f} best={best_score:.6f}")


if __name__ == "__main__":
    main()
