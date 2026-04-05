import json
import subprocess
import sys
from pathlib import Path


def test_runner_cli_writes_summary(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    scenarios_path = tmp_path / "scenarios.json"
    output_path = tmp_path / "summary.json"
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
                    "name": "return-basic",
                    "input": {
                        "date_start": "2026-01-01",
                        "date_end": "2026-03-31",
                        "profit_loss_ptd": 50000.0,
                        "profit_loss_ytd": 150000.0,
                        "fees_ptd": 5000.0,
                        "nav_begin": 1000000.0,
                        "nav_end": 1050000.0,
                        "subscriptions": 20000.0,
                        "redemptions": 10000.0,
                    },
                    "expected": [0.04955, 0.03609],
                }
            ]
        )
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "autoresearch_function.runner",
            "--config",
            str(config_path),
            "--scenarios",
            str(scenarios_path),
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "---" in completed.stdout
    summary = json.loads(output_path.read_text())
    assert summary["correctness"] >= 0.0
    assert "production_readiness" in summary
