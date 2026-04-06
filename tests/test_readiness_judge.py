import json

from autoresearch_function.readiness_judge import (
    OpenAIReadinessJudge,
    build_readiness_judge,
    extract_response_text,
)


def sample_func(payload):
    return payload


def sample_score_fn(func, scenarios) -> float:  # noqa: ARG001
    return 0.42


def test_build_readiness_judge_defaults_to_heuristic_without_key() -> None:
    judge = build_readiness_judge(sample_score_fn, env={})
    result = judge.evaluate(sample_func, [])
    assert result.source == "heuristic"
    assert result.score == 0.42


def test_build_readiness_judge_uses_openai_then_falls_back_on_invalid_json() -> None:
    def broken_post(payload, api_key, timeout_seconds):  # noqa: ARG001
        return {"output_text": "not-json"}

    judge = build_readiness_judge(
        sample_score_fn,
        env={
            "LLM_JUDGE_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-key",
            "LLM_JUDGE_MODEL": "gpt-4.1-mini",
        },
        http_post=broken_post,
    )
    result = judge.evaluate(sample_func, [])
    assert result.source == "heuristic_fallback"
    assert result.score == 0.42
    assert result.error is not None


def test_openai_judge_parses_structured_json_output() -> None:
    payload = {
        "score": 0.9,
        "breakdown": {
            "defensive_checks": 0.8,
            "input_validation": 0.9,
            "error_signaling": 0.9,
            "clarity_maintainability": 0.95,
            "operational_safety": 0.95,
        },
        "rationale": "Clear defensive checks and explicit failure handling.",
    }

    def ok_post(request_payload, api_key, timeout_seconds):  # noqa: ARG001
        assert request_payload["model"] == "gpt-4.1-mini"
        return {"output_text": json.dumps(payload)}

    judge = OpenAIReadinessJudge(
        api_key="test-key",
        model="gpt-4.1-mini",
        timeout_seconds=5,
        http_post=ok_post,
    )
    result = judge.evaluate(sample_func, [])
    assert result.source == "llm"
    assert result.provider == "openai"
    assert result.score == 0.9
    assert "defensive_checks" in result.breakdown
    assert result.error is None


def test_extract_response_text_supports_output_chunks() -> None:
    response = {
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"score":0.5,"breakdown":{},"rationale":"ok"}',
                    }
                ]
            }
        ]
    }
    text = extract_response_text(response)
    assert '"score":0.5' in text
