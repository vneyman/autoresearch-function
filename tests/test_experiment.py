import json
from pathlib import Path

from autoresearch_function.experiment import (
    append_result,
    get_best_score,
    is_improvement,
    latest_results,
    load_config,
    load_summary,
)


def test_load_config_and_summary(tmp_path: Path) -> None:
    config_path = tmp_path / "config.cfg"
    summary_path = tmp_path / "summary.json"
    config_path.write_text(
        "\n".join(
            [
                "name: demo",
                "target: demo.py",
                "evaluate_cmd: python demo.py",
                "summary_file: benchmark-summary.json",
                "metric: overall_score",
                "metric_direction: higher",
                "correctness_metric: correctness",
                "correctness_threshold: 1.0",
                "time_budget_minutes: 5",
            ]
        )
    )
    summary_path.write_text(
        json.dumps(
            {
                "overall_score": 0.9,
                "correctness": 1.0,
                "median_latency_ms": 1.2,
                "peak_memory_kb": 3.4,
                "concurrency_ops_per_s": 99.0,
                "production_readiness": 0.8,
            }
        )
    )

    config = load_config(config_path)
    summary = load_summary(summary_path)

    assert config.metric == "overall_score"
    assert summary.correctness == 1.0


def test_results_helpers(tmp_path: Path) -> None:
    results_path = tmp_path / "results.tsv"
    results_path.write_text(
        "commit\toverall_score\tcorrectness\tmedian_latency_ms\tpeak_memory_kb\tconcurrency_ops_per_s\tproduction_readiness\tstatus\tdescription\n"
    )

    summary_a = load_summary(
        _write_summary(
            tmp_path / "a.json",
            0.91,
            1.0,
        )
    )
    summary_b = load_summary(
        _write_summary(
            tmp_path / "b.json",
            0.88,
            1.0,
        )
    )

    append_result(results_path, "abc1234", summary_a, "keep", "baseline")
    append_result(results_path, "def5678", summary_b, "discard", "worse")

    assert get_best_score(results_path) == 0.91
    assert is_improvement("higher", 0.92, 0.91)
    assert not is_improvement("higher", 0.89, 0.91)
    assert latest_results(results_path, limit=1)[0]["commit"] == "def5678"


def _write_summary(path: Path, overall_score: float, correctness: float) -> Path:
    path.write_text(
        json.dumps(
            {
                "overall_score": overall_score,
                "correctness": correctness,
                "median_latency_ms": 1.0,
                "peak_memory_kb": 2.0,
                "concurrency_ops_per_s": 3.0,
                "production_readiness": 0.6,
            }
        )
    )
    return path
