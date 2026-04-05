# autoresearch-function

This project adapts the autoresearch pattern to CPU-only function optimization.

## Setup

1. Read `README.md`, `scenarios/config.json`, and `scenarios/scenarios.json`.
2. Treat `autoresearch_function/runner.py` as the fixed evaluator.
3. Treat `autoresearch_function/target_function.py` as the only file to modify during optimization.
4. Do not change the benchmark harness when comparing experiments.
5. Run `python -m autoresearch_function.runner` to produce metrics.

## Goal

Maximize correctness first, then improve:

- speed
- memory efficiency
- concurrent throughput 
- production ready code 

Correctness is a hard gate. A faster function with worse outputs is not acceptable.

## Output

The evaluator prints:

```text
---
correctness:            1.000000
median_latency_ms:      0.012345
peak_memory_kb:         8.500000
concurrency_ops_per_s:  15234.567890
production_readiness:   0.950000
overall_score:          0.923451
scenarios_passed:       4/4
```

## Rules

- CPU-only execution.
- No new dependencies unless explicitly approved.
- Keep changes small and reviewable.
- Prefer simpler code when metrics are effectively tied.
- If correctness drops, discard the change. 
- Result should be rounded to 5 decimal places
