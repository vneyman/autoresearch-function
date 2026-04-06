from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    target: str
    evaluate_cmd: str
    summary_file: str
    metric: str
    metric_direction: str
    correctness_metric: str
    correctness_threshold: float
    time_budget_minutes: int


@dataclass(frozen=True)
class Summary:
    overall_score: float
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


def load_config(path: str | Path) -> ExperimentConfig:
    values: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()

    return ExperimentConfig(
        name=values["name"],
        target=values["target"],
        evaluate_cmd=values["evaluate_cmd"],
        summary_file=values["summary_file"],
        metric=values["metric"],
        metric_direction=values["metric_direction"],
        correctness_metric=values["correctness_metric"],
        correctness_threshold=float(values["correctness_threshold"]),
        time_budget_minutes=int(values["time_budget_minutes"]),
    )


def load_summary(path: str | Path) -> Summary:
    raw = json.loads(Path(path).read_text())
    def _float(key: str, default: float | None = None) -> float | None:
        value = raw.get(key)
        if value is None:
            return default
        return float(value)

    def _str(key: str, default: str) -> str:
        value = raw.get(key)
        if value is None:
            return default
        return str(value)

    breakdown_raw = raw.get("production_readiness_breakdown")
    if isinstance(breakdown_raw, dict):
        breakdown: dict[str, float] = {
            str(k): float(v) for k, v in breakdown_raw.items() if v is not None
        }
    else:
        breakdown = {}

    return Summary(
        overall_score=float(raw["overall_score"]),
        correctness=float(raw["correctness"]),
        median_latency_ms=float(raw["median_latency_ms"]),
        peak_memory_kb=float(raw["peak_memory_kb"]),
        concurrency_ops_per_s=float(raw["concurrency_ops_per_s"]),
        production_readiness=float(raw["production_readiness"]),
        production_readiness_source=_str("production_readiness_source", "heuristic"),
        production_readiness_breakdown=breakdown,
        production_readiness_rationale=_str("production_readiness_rationale", ""),
        judge_provider=_str("judge_provider", "heuristic"),
        judge_model=raw.get("judge_model"),
        judge_latency_ms=_float("judge_latency_ms"),
        judge_error=raw.get("judge_error"),
    )


def get_best_score(results_path: str | Path) -> float | None:
    path = Path(results_path)
    if not path.exists():
        return None

    scores: list[float] = []
    for line in path.read_text().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 8 or parts[7] != "keep":
            continue
        try:
            scores.append(float(parts[1]))
        except ValueError:
            continue
    return max(scores) if scores else None


def is_improvement(metric_direction: str, candidate: float, best: float | None) -> bool:
    if best is None:
        return True
    if metric_direction == "lower":
        return candidate < best
    return candidate > best


def _sanitize_readiness_rationale(rationale: str) -> str:
    return " ".join(line.strip() for line in rationale.splitlines() if line.strip())


def _describe_readiness(summary: Summary) -> str:
    rationale = _sanitize_readiness_rationale(summary.production_readiness_rationale)
    if not rationale:
        rationale = "no comment"
    provider = summary.judge_provider
    model_info = f"/{summary.judge_model}" if summary.judge_model else ""
    return (
        f"{summary.production_readiness_source} {summary.production_readiness:.3f}"
        f" ({provider}{model_info}) – {rationale}"
    )


def append_result(results_path: str | Path, commit: str, summary: Summary | None, status: str, description: str) -> None:
    metric = "N/A"
    correctness = "N/A"
    latency = "N/A"
    peak_memory = "N/A"
    concurrency = "N/A"
    readiness = "N/A"
    readiness_note = ""
    if summary is not None:
        metric = f"{summary.overall_score:.6f}"
        correctness = f"{summary.correctness:.6f}"
        latency = f"{summary.median_latency_ms:.6f}"
        peak_memory = f"{summary.peak_memory_kb:.6f}"
        concurrency = f"{summary.concurrency_ops_per_s:.6f}"
        readiness = f"{summary.production_readiness:.6f}"
        readiness_note = _describe_readiness(summary)

    final_description = description
    if readiness_note:
        final_description = f"{description} | readiness: {readiness_note}"

    with Path(results_path).open("a") as handle:
        handle.write(
            "\t".join(
                [
                    commit,
                    metric,
                    correctness,
                    latency,
                    peak_memory,
                    concurrency,
                    readiness,
                    status,
                    description,
                ]
            )
            + "\n"
        )


def run_command(command: str, cwd: str | Path, timeout_seconds: float, log_path: str | Path) -> tuple[int, float]:
    started = time.time()
    try:
        with Path(log_path).open("w") as handle:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
        return completed.returncode, time.time() - started
    except subprocess.TimeoutExpired:
        return -1, time.time() - started


def git_stdout(args: list[str], cwd: str | Path) -> str | None:
    completed = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def current_commit(cwd: str | Path) -> str:
    commit = git_stdout(["rev-parse", "--short", "HEAD"], cwd)
    return commit or "nogit"


def can_rollback_last_commit(cwd: str | Path) -> bool:
    inside = git_stdout(["rev-parse", "--is-inside-work-tree"], cwd)
    if inside != "true":
        return False
    parent = git_stdout(["rev-parse", "--verify", "HEAD~1"], cwd)
    return parent is not None


def rollback_last_commit(cwd: str | Path) -> bool:
    completed = subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def latest_results(results_path: str | Path, limit: int = 10) -> list[dict[str, str]]:
    path = Path(results_path)
    if not path.exists():
        return []

    rows = path.read_text().splitlines()
    if len(rows) <= 1:
        return []
    headers = rows[0].split("\t")
    items: list[dict[str, str]] = []
    for row in rows[1:][-limit:]:
        values = row.split("\t")
        items.append(dict(zip(headers, values)))
    return items
