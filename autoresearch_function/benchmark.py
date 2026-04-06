from __future__ import annotations

import json
import math
import statistics
import time
import tracemalloc
import inspect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from autoresearch_function.readiness_judge import build_readiness_judge


@dataclass(frozen=True)
class Scenario:
    name: str
    input: Any
    expected: Any | None = None
    expect_error: str | None = None
    kind: str = "correctness"


@dataclass(frozen=True)
class BenchmarkConfig:
    tolerance: float
    warmup_runs: int
    timed_runs: int
    concurrency_workers: int
    concurrency_repeats: int
    score_weights: dict[str, float]
    score_targets: dict[str, float]
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 15.0


@dataclass(frozen=True)
class BenchmarkResult:
    correctness: float
    median_latency_ms: float
    peak_memory_kb: float
    concurrency_ops_per_s: float
    production_readiness: float
    production_readiness_source: str
    production_readiness_breakdown: dict[str, float]
    production_readiness_rationale: str
    judge_provider: str
    judge_model: str | None
    judge_latency_ms: float | None
    judge_error: str | None
    overall_score: float
    scenarios_passed: int
    scenario_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "correctness": self.correctness,
            "median_latency_ms": self.median_latency_ms,
            "peak_memory_kb": self.peak_memory_kb,
            "concurrency_ops_per_s": self.concurrency_ops_per_s,
            "production_readiness": self.production_readiness,
            "production_readiness_source": self.production_readiness_source,
            "production_readiness_breakdown": self.production_readiness_breakdown,
            "production_readiness_rationale": self.production_readiness_rationale,
            "judge_provider": self.judge_provider,
            "judge_model": self.judge_model,
            "judge_latency_ms": self.judge_latency_ms,
            "judge_error": self.judge_error,
            "overall_score": self.overall_score,
            "scenarios_passed": self.scenarios_passed,
            "scenario_count": self.scenario_count,
        }


def load_scenarios(path: str | Path) -> list[Scenario]:
    raw = json.loads(Path(path).read_text())
    return [Scenario(**item) for item in raw]


def load_config(path: str | Path) -> BenchmarkConfig:
    raw = json.loads(Path(path).read_text())
    llm_judge = raw.get("llm_judge", {})
    return BenchmarkConfig(
        tolerance=float(raw["correctness"]["tolerance"]),
        warmup_runs=int(raw["benchmark"]["warmup_runs"]),
        timed_runs=int(raw["benchmark"]["timed_runs"]),
        concurrency_workers=int(raw["benchmark"]["concurrency_workers"]),
        concurrency_repeats=int(raw["benchmark"]["concurrency_repeats"]),
        score_weights=dict(raw["score"]["weights"]),
        score_targets=dict(raw["score"]["targets"]),
        llm_provider=str(llm_judge.get("provider", "auto")),
        llm_model=str(llm_judge.get("model", "gpt-4.1-mini")),
        llm_timeout_seconds=float(llm_judge.get("timeout_seconds", 15.0)),
    )


def compare_outputs(actual: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        if len(actual) != len(expected):
            return False
        return all(compare_outputs(a, e, tolerance) for a, e in zip(actual, expected))
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            return False
        return all(compare_outputs(actual[key], expected[key], tolerance) for key in actual)
    return actual == expected


def split_scenarios(scenarios: list[Scenario]) -> tuple[list[Scenario], list[Scenario]]:
    correctness_scenarios = [scenario for scenario in scenarios if scenario.kind != "readiness"]
    readiness_scenarios = [scenario for scenario in scenarios if scenario.kind == "readiness"]
    return correctness_scenarios, readiness_scenarios


def evaluate_correctness(
    func: Callable[[Any], Any],
    scenarios: list[Scenario],
    tolerance: float,
) -> tuple[float, int]:
    if not scenarios:
        return 1.0, 0

    passed = 0
    for scenario in scenarios:
        actual = func(scenario.input)
        if compare_outputs(actual, scenario.expected, tolerance):
            passed += 1
    return passed / len(scenarios), passed


def measure_latency_ms(
    func: Callable[[Any], Any],
    scenarios: list[Scenario],
    warmup_runs: int,
    timed_runs: int,
) -> float:
    if not scenarios:
        return 0.0

    timings_ms: list[float] = []
    for scenario in scenarios:
        for _ in range(warmup_runs):
            func(scenario.input)
        for _ in range(timed_runs):
            start = time.perf_counter()
            func(scenario.input)
            end = time.perf_counter()
            timings_ms.append((end - start) * 1000.0)
    return statistics.median(timings_ms)


def measure_peak_memory_kb(
    func: Callable[[Any], Any],
    scenarios: list[Scenario],
) -> float:
    if not scenarios:
        return 0.0

    peak_bytes = 0
    for scenario in scenarios:
        tracemalloc.start()
        try:
            func(scenario.input)
            _, peak = tracemalloc.get_traced_memory()
            peak_bytes = max(peak_bytes, peak)
        finally:
            tracemalloc.stop()
    return peak_bytes / 1024.0


def measure_concurrency_ops_per_s(
    func: Callable[[Any], Any],
    scenarios: list[Scenario],
    workers: int,
    repeats: int,
) -> float:
    if not scenarios:
        return 0.0

    calls = [scenario.input for scenario in scenarios] * repeats
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(func, payload) for payload in calls]
        for future in futures:
            future.result()
    end = time.perf_counter()
    elapsed = end - start
    if elapsed <= 0:
        return float("inf")
    return len(calls) / elapsed


def evaluate_static_readiness(func: Callable[[Any], Any]) -> float:
    score = 0.0

    if func.__doc__ and func.__doc__.strip():
        score += 0.25

    annotations = getattr(func, "__annotations__", {})
    if "return" in annotations:
        score += 0.15
    if annotations:
        score += 0.15

    signature = inspect.signature(func)
    parameters = list(signature.parameters.values())
    if parameters and all(param.annotation is not inspect._empty for param in parameters):
        score += 0.15

    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        source = ""

    lowered = source.lower()
    if "todo" not in lowered and "fixme" not in lowered:
        score += 0.15

    if "raise " in source or "ValueError" in source or "TypeError" in source:
        score += 0.15

    return min(1.0, score)


def evaluate_error_handling(
    func: Callable[[Any], Any],
    scenarios: list[Scenario],
) -> float:
    if not scenarios:
        return 1.0

    passed = 0
    for scenario in scenarios:
        try:
            func(scenario.input)
        except Exception as exc:  # noqa: BLE001
            if scenario.expect_error and exc.__class__.__name__ == scenario.expect_error:
                passed += 1
        else:
            if not scenario.expect_error:
                passed += 1
    return passed / len(scenarios)


def evaluate_production_readiness(
    func: Callable[[Any], Any],
    readiness_scenarios: list[Scenario],
) -> float:
    static_readiness = evaluate_static_readiness(func)
    error_handling = evaluate_error_handling(func, readiness_scenarios)
    return (static_readiness + error_handling) / 2.0


def compute_overall_score(
    correctness: float,
    latency_ms: float,
    memory_kb: float,
    concurrency_ops_per_s: float,
    production_readiness: float,
    weights: dict[str, float],
    targets: dict[str, float],
) -> float:
    latency_score = targets["latency_ms"] / max(latency_ms, 1e-9)
    memory_score = targets["memory_kb"] / max(memory_kb, 1e-9)
    concurrency_score = concurrency_ops_per_s / max(targets["concurrency_ops_per_s"], 1e-9)

    score = (
        weights["correctness"] * correctness
        + weights["latency"] * latency_score
        + weights["memory"] * memory_score
        + weights["concurrency"] * concurrency_score
        + weights["production_readiness"] * production_readiness
    )
    return max(0.0, score)


def run_benchmark(
    func: Callable[[Any], Any],
    scenarios: list[Scenario],
    config: BenchmarkConfig,
) -> BenchmarkResult:
    correctness_scenarios, readiness_scenarios = split_scenarios(scenarios)
    correctness, passed = evaluate_correctness(func, correctness_scenarios, config.tolerance)
    latency_ms = measure_latency_ms(func, correctness_scenarios, config.warmup_runs, config.timed_runs)
    memory_kb = measure_peak_memory_kb(func, correctness_scenarios)
    concurrency_ops_per_s = measure_concurrency_ops_per_s(
        func,
        correctness_scenarios,
        config.concurrency_workers,
        config.concurrency_repeats,
    )
    judge = build_readiness_judge(
        evaluate_production_readiness,
        provider=config.llm_provider,
        model=config.llm_model,
        timeout_seconds=config.llm_timeout_seconds,
    )
    judgment = judge.evaluate(func, readiness_scenarios)
    production_readiness = judgment.score
    overall_score = compute_overall_score(
        correctness,
        latency_ms,
        memory_kb,
        concurrency_ops_per_s,
        production_readiness,
        config.score_weights,
        config.score_targets,
    )
    return BenchmarkResult(
        correctness=correctness,
        median_latency_ms=latency_ms,
        peak_memory_kb=memory_kb,
        concurrency_ops_per_s=concurrency_ops_per_s,
        production_readiness=production_readiness,
        production_readiness_source=judgment.source,
        production_readiness_breakdown=judgment.breakdown,
        production_readiness_rationale=judgment.rationale,
        judge_provider=judgment.provider,
        judge_model=judgment.model,
        judge_latency_ms=judgment.latency_ms,
        judge_error=judgment.error,
        overall_score=overall_score,
        scenarios_passed=passed,
        scenario_count=len(correctness_scenarios),
    )
