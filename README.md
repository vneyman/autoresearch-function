# autoresearch-function

CPU-only function optimization scaffold inspired by the reference `autoresearch/` repo.

Instead of training a model and measuring validation loss, this project evaluates a single function against:

- correctness of the produced output
- median execution time
- peak memory usage
- concurrent execution throughput
- production readiness

The fixed harness reads scenario inputs and expected outputs from JSON, runs the target function on CPU, and prints a summary that is suitable for local runs and GitHub Actions.

## Project shape

This project mirrors the reference repo's core idea:

- `autoresearch_function/target_function.py` is the only file meant to be iterated on
- `autoresearch_function/runner.py` is the fixed evaluator entrypoint
- `scenarios/` contains test cases, expected outputs, and scoring config
- `program.md` defines the working protocol for future autonomous iterations

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m autoresearch_function.runner
pytest
```

## Scenario format

Edit `scenarios/scenarios.json` to provide the inputs and expected outputs for your function:

```json
[
  {
    "name": "basic-addition",
    "input": {"operation": "add", "values": [2, 3]},
    "expected": 5
  }
]
```

The bundled example uses a simple calculator-style function because you said you will provide the calculations and expected results later.

## Config format

`scenarios/config.json` controls the benchmark:

- `correctness.tolerance`: numeric comparison tolerance
- `benchmark.warmup_runs`: warmup calls before measuring speed
- `benchmark.timed_runs`: measured calls per scenario
- `benchmark.concurrency_workers`: worker count for the threaded concurrency check
- `score.weights`: weights used to combine the normalized metrics
- `score.targets`: target values used for score normalization
- `production_readiness`: lightweight static quality checks for the target function

## GitHub Actions

The workflow at `.github/workflows/autoresearch.yml` runs on GitHub-hosted CPU runners, executes measured experiment iterations, uploads evaluation artifacts, and commits `.autoresearch/.../results.tsv` and `.autoresearch/.../run.log` back to the repo.

`workflow_dispatch` inputs:

- `cadence`: `5m`, `30m`, `1h`, `2h`, `daily`
- `max_iterations`: defaults to `5` (override allowed)
- `rollback`: `true`/`false`
- `description`: free-form run description

Scheduled runs are also supported for the same cadence options. Configure scheduled behavior with repo variables:

- `AUTORESEARCH_SCHEDULE_CADENCE`: active schedule cadence (default `5m`)
- `AUTORESEARCH_MAX_ITERATIONS`: max iterations per scheduled run (default `5`)

## Autoresearch Loop

Project-local experiment state lives under `.autoresearch/`.

Default experiment:

- `.autoresearch/engineering/portfolio-return/config.cfg`
- `.autoresearch/engineering/portfolio-return/results.tsv`

Run one measured iteration:

```bash
python scripts/run_experiment.py --description "baseline"
```

Show recent experiment history:

```bash
python scripts/status.py
```

If you are using git and you commit one experiment change at a time, you can ask the runner to rollback the last commit on discard or crash:

```bash
python scripts/run_experiment.py --description "try fee gate change" --rollback
```

## Notes

- No GPU code is used.
- The harness uses only the Python standard library.
- If you later want a true autonomous search loop, this scaffold is already structured so an agent can repeatedly edit `target_function.py` and call the fixed evaluator.
