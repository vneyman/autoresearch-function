import json

from autoresearch_function.benchmark import (
    compare_outputs,
    evaluate_error_handling,
    load_config,
    load_scenarios,
    run_benchmark,
)


def sample_candidate(payload):
    operation = payload["operation"]
    values = payload["values"]
    if operation == "add":
        return sum(values)
    if operation == "subtract":
        head, *tail = values
        return head - sum(tail)
    raise ValueError(f"unsupported operation: {operation}")


def readiness_candidate(payload):
    if payload["mode"] == "error":
        raise ValueError("forced")
    return payload["value"]


def test_compare_outputs_supports_tolerance() -> None:
    assert compare_outputs(1.0000001, 1.0, 1e-6)
    assert not compare_outputs(1.01, 1.0, 1e-6)
    assert compare_outputs([1.0000001, 2.0], [1.0, 2.0], 1e-6)


def test_error_handling_uses_readiness_scenarios(tmp_path) -> None:
    scenarios_path = tmp_path / "readiness.json"
    scenarios_path.write_text(
        json.dumps(
            [
                {"name": "ok", "kind": "readiness", "input": {"mode": "ok", "value": 1}, "expect_error": None},
                {"name": "err", "kind": "readiness", "input": {"mode": "error", "value": 1}, "expect_error": "ValueError"},
            ]
        )
    )
    scenarios = load_scenarios(scenarios_path)
    assert evaluate_error_handling(readiness_candidate, scenarios) == 1.0


def test_runner_metrics_for_sample_function(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    scenarios_path = tmp_path / "scenarios.json"
    config_path.write_text(
        json.dumps(
            {
                "correctness": {"tolerance": 1e-9},
                "benchmark": {
                    "warmup_runs": 2,
                    "timed_runs": 5,
                    "concurrency_workers": 2,
                    "concurrency_repeats": 5,
                },
                "score": {
                    "weights": {
                        "correctness": 0.45,
                        "latency": 0.18,
                        "memory": 0.08,
                        "concurrency": 0.14,
                        "production_readiness": 0.15,
                    },
                    "targets": {
                        "latency_ms": 0.05,
                        "memory_kb": 16.0,
                        "concurrency_ops_per_s": 1000.0,
                    },
                },
            }
        )
    )
    scenarios_path.write_text(
        json.dumps(
            [
                {
                    "name": "basic-addition",
                    "input": {"operation": "add", "values": [2, 3]},
                    "expected": 5,
                },
                {
                    "name": "subtraction-chain",
                    "input": {"operation": "subtract", "values": [10, 3, 2]},
                    "expected": 5,
                },
            ]
        )
    )

    config = load_config(config_path)
    scenarios = load_scenarios(scenarios_path)
    result = run_benchmark(sample_candidate, scenarios, config)

    assert result.correctness == 1.0
    assert result.scenarios_passed == len(scenarios)
    assert result.median_latency_ms >= 0.0
    assert result.peak_memory_kb >= 0.0
    assert result.concurrency_ops_per_s > 0.0
    assert 0.0 <= result.production_readiness <= 1.0
    assert result.production_readiness_source in ("heuristic", "heuristic_fallback", "llm")
    assert isinstance(result.production_readiness_breakdown, dict)
    assert isinstance(result.production_readiness_rationale, str)
    assert isinstance(result.judge_provider, str)
    assert result.judge_error is None or isinstance(result.judge_error, str)
    assert result.overall_score > 0.0
