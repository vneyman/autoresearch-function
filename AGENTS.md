# AGENTS.md

The `autoresearch-function` project mimics the original `autoresearch` workflow but targets a CPU-bound function. Follow these steps before editing `target_function.py`:

1. **Setup**: review `README.md`, `.autoresearch/engineering/portfolio-return/config.cfg`, `scenarios/*.json`, and `scripts/run_experiment.py`. Ensure `.venv/` is active so `python -m autoresearch_function.runner` works.
2. **Baseline run**: run `python scripts/run_experiment.py --description baseline` to capture the current `overall_score` in `.autoresearch/engineering/portfolio-return/results.tsv`.
3. **One change**: edit only `autoresearch_function/target_function.py`, touching a single idea per experiment so you can attribute improvements cleanly.
4. **Evaluate**: execute `python scripts/run_experiment.py --description "<what changed>"` (+`--rollback` if you commit the change and want the runner to revert losers). The script runs the benchmark, writes `benchmark-summary.json`, and logs the score.
5. **Log**: inspect `.autoresearch/engineering/portfolio-return/results.tsv` for `keep`/`discard` history, and run `python scripts/status.py` or the GitHub Actions workflow (`.github/workflows/autoresearch.yml`) to visualize progress.
6. **Iterate**: keep a change when overall_score improves (function still must pass correctness gate) and discard otherwise; the runner already handles `git reset` on failures when requested.
7. **Automation**: the scheduled workflow triggers the same `scripts/run_experiment.py` for recurring CPU experiments; adjust the `description` input when you manually trigger it from GitHub.

Keep the function batch small, prioritize correctness, then latency/memory/concurrency, and treat the production readiness score as a tie-breaker.
