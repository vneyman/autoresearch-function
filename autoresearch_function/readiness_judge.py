from __future__ import annotations

import inspect
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ReadinessJudgment:
    score: float
    source: str
    breakdown: dict[str, float]
    rationale: str
    provider: str
    model: str | None
    latency_ms: float | None
    error: str | None = None


class ReadinessJudge(Protocol):
    def evaluate(self, func: Callable[[Any], Any], readiness_scenarios: Sequence[Any]) -> ReadinessJudgment:
        ...


class HeuristicReadinessJudge:
    def __init__(
        self,
        score_fn: Callable[[Callable[[Any], Any], Sequence[Any]], float],
        source: str = "heuristic",
        provider: str = "heuristic",
        error: str | None = None,
    ) -> None:
        self._score_fn = score_fn
        self._source = source
        self._provider = provider
        self._error = error

    def evaluate(self, func: Callable[[Any], Any], readiness_scenarios: Sequence[Any]) -> ReadinessJudgment:
        score = clamp_score(self._score_fn(func, readiness_scenarios))
        return ReadinessJudgment(
            score=score,
            source=self._source,
            breakdown={},
            rationale="heuristic readiness evaluation",
            provider=self._provider,
            model=None,
            latency_ms=None,
            error=self._error,
        )


class OpenAIReadinessJudge:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        http_post: Callable[[dict[str, Any], str, float], dict[str, Any]] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._http_post = http_post or _default_openai_post

    def evaluate(self, func: Callable[[Any], Any], readiness_scenarios: Sequence[Any]) -> ReadinessJudgment:
        started = time.perf_counter()
        source = safe_source(func)
        scenarios_payload = normalize_scenarios(readiness_scenarios)
        request_payload = build_openai_payload(self._model, source, scenarios_payload)
        raw = self._http_post(request_payload, self._api_key, self._timeout_seconds)
        response_text = extract_response_text(raw)
        parsed = parse_judge_payload(response_text)
        return ReadinessJudgment(
            score=clamp_score(parsed["score"]),
            source="llm",
            breakdown=parsed["breakdown"],
            rationale=parsed["rationale"],
            provider="openai",
            model=self._model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            error=None,
        )


class LLMWithFallbackJudge:
    def __init__(self, primary: ReadinessJudge, fallback: ReadinessJudge) -> None:
        self._primary = primary
        self._fallback = fallback

    def evaluate(self, func: Callable[[Any], Any], readiness_scenarios: Sequence[Any]) -> ReadinessJudgment:
        try:
            return self._primary.evaluate(func, readiness_scenarios)
        except Exception as exc:  # noqa: BLE001
            fallback = self._fallback.evaluate(func, readiness_scenarios)
            return ReadinessJudgment(
                score=fallback.score,
                source="heuristic_fallback",
                breakdown=fallback.breakdown,
                rationale=fallback.rationale,
                provider=fallback.provider,
                model=fallback.model,
                latency_ms=fallback.latency_ms,
                error=str(exc),
            )


def build_readiness_judge(
    score_fn: Callable[[Callable[[Any], Any], Sequence[Any]], float],
    *,
    provider: str | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
    env: Mapping[str, str] | None = None,
    http_post: Callable[[dict[str, Any], str, float], dict[str, Any]] | None = None,
) -> ReadinessJudge:
    environ = env if env is not None else os.environ
    selected_provider = (environ.get("LLM_JUDGE_PROVIDER") or provider or "auto").strip().lower()
    selected_model = (environ.get("LLM_JUDGE_MODEL") or model or "gpt-4.1-mini").strip()
    timeout_raw = environ.get("LLM_JUDGE_TIMEOUT_SECONDS")
    selected_timeout = timeout_seconds if timeout_seconds is not None else 15.0
    if timeout_raw:
        try:
            selected_timeout = float(timeout_raw)
        except ValueError:
            selected_timeout = 15.0

    fallback = HeuristicReadinessJudge(score_fn)
    api_key = environ.get("OPENAI_API_KEY", "").strip()

    if selected_provider in ("heuristic", "none", "off"):
        return fallback

    if selected_provider == "auto" and not api_key:
        return fallback

    if selected_provider in ("openai", "auto"):
        if not api_key:
            return HeuristicReadinessJudge(
                score_fn,
                source="heuristic_fallback",
                error="OPENAI_API_KEY is required for provider=openai",
            )
        primary = OpenAIReadinessJudge(api_key, selected_model, selected_timeout, http_post=http_post)
        return LLMWithFallbackJudge(primary, fallback)

    return HeuristicReadinessJudge(
        score_fn,
        source="heuristic_fallback",
        error=f"unknown provider: {selected_provider}",
    )


def build_openai_payload(model: str, function_source: str, readiness_scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    system_prompt = (
        "You are a strict software production-readiness reviewer. "
        "Score only what is observable in the provided function source and readiness scenarios. "
        "Return valid JSON only."
    )
    user_prompt = {
        "rubric": [
            "defensive_checks",
            "input_validation",
            "error_signaling",
            "clarity_maintainability",
            "operational_safety",
        ],
        "instructions": (
            "Return object with keys: score (0..1), breakdown (object with rubric keys, each 0..1), "
            "rationale (max 240 chars). score should be the arithmetic mean of breakdown values."
        ),
        "function_source": function_source,
        "readiness_scenarios": readiness_scenarios,
    }
    return {
        "model": model,
        "temperature": 0,
        "max_output_tokens": 500,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(user_prompt)}],
            },
        ],
    }


def _default_openai_post(payload: dict[str, Any], api_key: str, timeout_seconds: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=data,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"openai http {exc.code}: {body}") from exc


def extract_response_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output_items = response.get("output")
    if isinstance(output_items, list):
        chunks: list[str] = []
        for item in output_items:
            if not isinstance(item, dict):
                continue
            contents = item.get("content")
            if not isinstance(contents, list):
                continue
            for content in contents:
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks)
    raise RuntimeError("no textual output found in OpenAI response")


def parse_judge_payload(text: str) -> dict[str, Any]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid judge json: {exc}") from exc

    if not isinstance(raw, dict):
        raise RuntimeError("judge payload must be an object")

    score = raw.get("score")
    breakdown = raw.get("breakdown")
    rationale = raw.get("rationale")
    if not isinstance(score, (int, float)):
        raise RuntimeError("judge payload missing numeric score")
    if not isinstance(breakdown, dict):
        raise RuntimeError("judge payload missing breakdown object")
    if not isinstance(rationale, str):
        raise RuntimeError("judge payload missing rationale string")

    normalized_breakdown: dict[str, float] = {}
    for key, value in breakdown.items():
        if not isinstance(key, str) or not isinstance(value, (int, float)):
            continue
        normalized_breakdown[key] = clamp_score(float(value))

    return {
        "score": clamp_score(float(score)),
        "breakdown": normalized_breakdown,
        "rationale": rationale.strip()[:240],
    }


def safe_source(func: Callable[[Any], Any]) -> str:
    try:
        return inspect.getsource(func)
    except (OSError, TypeError):
        return ""


def normalize_scenarios(readiness_scenarios: Sequence[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for scenario in readiness_scenarios:
        normalized.append(
            {
                "name": str(getattr(scenario, "name", "unknown")),
                "input": json.loads(json.dumps(getattr(scenario, "input", None), default=str)),
                "expect_error": getattr(scenario, "expect_error", None),
            }
        )
    return normalized


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
