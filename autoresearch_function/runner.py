from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from autoresearch_function.benchmark import load_config, load_scenarios, run_benchmark
from autoresearch_function.target_function import candidate_portfolio_return_gross_net


def benchmark_target(payload: dict[str, object]) -> object:
    adapted = dict(payload)
    for key in ("date_start", "date_end"):
        value = adapted.get(key)
        if isinstance(value, str):
            adapted[key] = date.fromisoformat(value)
    return candidate_portfolio_return_gross_net(**adapted)


def format_summary(summary: dict[str, object]) -> str:
    return "\n".join(
        [
            "---",
            f"correctness:            {summary['correctness']:.6f}",
            f"median_latency_ms:      {summary['median_latency_ms']:.6f}",
            f"peak_memory_kb:         {summary['peak_memory_kb']:.6f}",
            f"concurrency_ops_per_s:  {summary['concurrency_ops_per_s']:.6f}",
            f"production_readiness:   {summary['production_readiness']:.6f}",
            f"readiness_source:       {summary.get('production_readiness_source', 'heuristic')}",
            f"overall_score:          {summary['overall_score']:.6f}",
            f"scenarios_passed:       {summary['scenarios_passed']}/{summary['scenario_count']}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CPU-only function benchmark.")
    parser.add_argument(
        "--config",
        default="scenarios/config.json",
        help="Path to benchmark config JSON.",
    )
    parser.add_argument(
        "--scenarios",
        default="scenarios/scenarios.json",
        help="Path to scenario JSON.",
    )
    parser.add_argument(
        "--output",
        default="benchmark-summary.json",
        help="Where to write the JSON summary.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    scenarios = load_scenarios(args.scenarios)
    result = run_benchmark(benchmark_target, scenarios, config)
    summary = result.to_dict()

    Path(args.output).write_text(json.dumps(summary, indent=2) + "\n")
    print(format_summary(summary))


if __name__ == "__main__":
    main()
