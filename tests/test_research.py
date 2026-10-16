from dataclasses import replace
import io
import json
from urllib.error import HTTPError

import pytest

from iip.config import Settings
from iip.research import ResearchService, ResearchError, is_official
from iip.repository import LimitReached


class Response:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def read(self, size):
        return json.dumps(self.value).encode()


def tavily_response():
    return {"results": [{"title": "Primary report", "url": "https://www.nirfindia.org/example.pdf", "content": "Example Institute reported 812 registrations for 2025-26."}]}


def output_response(text, annotations=None):
    return {"status": "completed", "usage": {"input_tokens": 120, "output_tokens": 60}, "output": [{"type": "message", "content": [{"type": "output_text", "text": text, "annotations": annotations or []}]}]}


def test_official_host_allowlist_prevents_lookalikes():
    assert is_official("https://www.ugc.gov.in/report")
    assert not is_official("https://ugc.gov.in.evil.example/report")
    assert not is_official("https://notugc.gov.in/report")


def test_tavily_cache_avoids_paid_calls_and_scopes_options(repository, monkeypatch):
    calls = []
    def post(request, timeout):
        calls.append(json.loads(request.data))
        return Response(tavily_response())
    monkeypatch.setattr("iip.research.urlopen", post)
    service = ResearchService(Settings(tavily_key="test-key"), repository)
    first = service.search("Example Institute", synthesise=False)
    second = service.search("Example Institute", synthesise=False)
    assert first.sources and not first.cached and second.cached
    assert len(calls) == 1 and repository.usage()["requests"] == 1
    assert calls[0]["search_depth"] == "basic" and calls[0]["auto_parameters"] is False
    service.search("Example Institute", official_only=True, synthesise=False)
    assert len(calls) == 2
    assert "include_domains" in calls[-1]
    assert "test-key" not in json.dumps(repository.cache_get(service._cache_key("Example Institute", "Executive diligence", False, 6, False)))


def test_cache_fingerprint_changes_with_credentials_and_model(repository):
    a = ResearchService(Settings(tavily_key="a", openai_key="o"), repository)
    b = ResearchService(Settings(tavily_key="b", openai_key="o"), repository)
    c = ResearchService(Settings(tavily_key="a", openai_key="o", model="another-model"), repository)
    arguments = ("Example", "Admissions", False, 6, False)
    assert len({s._cache_key(*arguments) for s in [a, b, c]}) == 3


def test_fresh_search_replaces_saved_sources(repository, monkeypatch):
    calls = []
    def post(request, timeout):
        calls.append(request)
        data = tavily_response()
        data["results"][0]["content"] = f"Retrieved version {len(calls)}"
        return Response(data)
    monkeypatch.setattr("iip.research.urlopen", post)
    service = ResearchService(Settings(tavily_key="test-key"), repository)
    first = service.search("Example Institute", synthesise=False)
    fresh = service.search("Example Institute", synthesise=False, force_refresh=True)
    saved = service.search("Example Institute", synthesise=False)
    assert first.sources[0].snippet == "Retrieved version 1"
    assert fresh.sources[0].snippet == "Retrieved version 2" and not fresh.cached
    assert saved.sources[0].snippet == fresh.sources[0].snippet and saved.cached
    assert len(calls) == 2 and repository.usage()["requests"] == 2


def test_fresh_search_cannot_bypass_daily_limit(repository, monkeypatch):
    monkeypatch.setattr("iip.research.urlopen", lambda *a, **k: Response(tavily_response()))
    service = ResearchService(Settings(tavily_key="test-key", daily_limit=1), repository)
    service.search("Example Institute", synthesise=False)
    with pytest.raises(LimitReached):
        service.search("Example Institute", synthesise=False, force_refresh=True)
    assert service.search("Example Institute", synthesise=False).cached
    assert repository.usage()["requests"] == 1


def test_synthesis_drops_claims_with_invented_source_ids(repository, monkeypatch):
    calls = []
    synthesis = {"summary": "Two claims to review", "claims": [
        {"topic": "Admissions", "statement": "812 registrations", "source_ids": ["S1"], "caveat": "Unverified submission"},
        {"topic": "Unknown", "statement": "Invented", "source_ids": ["S99"], "caveat": "Missing"},
    ], "missing_information": ["Current affiliation"]}
    def post(request, timeout):
        calls.append(json.loads(request.data))
        return Response(tavily_response() if "tavily" in request.full_url else output_response(json.dumps(synthesis)))
    monkeypatch.setattr("iip.research.urlopen", post)
    result = ResearchService(Settings(tavily_key="t", openai_key="o"), repository).search("Example Institute")
    assert len(result.claims) == 1 and result.claims[0].source_ids == ["S1"]
    assert any("discarded" in note for note in result.missing_information)
    schema = calls[-1]["text"]["format"]["schema"]
    assert calls[-1]["store"] is False and schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert repository.usage()["input_tokens"] == 120


def test_retry_consumes_quota_and_no_credentials_leak(repository, monkeypatch):
    calls = []
    def fail(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 429, "secret-key-in-error-text", {}, io.BytesIO())
    monkeypatch.setattr("iip.research.urlopen", fail)
    monkeypatch.setattr("iip.research.time.sleep", lambda _: None)
    service = ResearchService(Settings(tavily_key="secret-key"), repository)
    with pytest.raises(ResearchError) as exc:
        service.search("Example Institute")
    assert "secret-key" not in str(exc.value)
    assert len(calls) == 2 and repository.usage()["requests"] == 2
    assert repository.usage()["failed"] == 2


def test_quota_can_interrupt_retry(repository, monkeypatch):
    def fail(request, timeout):
        raise HTTPError(request.full_url, 503, "unavailable", {}, io.BytesIO())
    monkeypatch.setattr("iip.research.urlopen", fail)
    monkeypatch.setattr("iip.research.time.sleep", lambda _: None)
    with pytest.raises(LimitReached):
        ResearchService(Settings(tavily_key="test", daily_limit=1), repository).search("Example Institute")
    assert repository.usage()["requests"] == 1


def test_openai_only_renders_clickable_citations(repository, monkeypatch):
    text = "Example fact [citation]."
    annotation = {"type": "url_citation", "url": "https://www.nirfindia.org/example.pdf", "title": "NIRF report", "start_index": 13, "end_index": 23}
    payloads = []
    def post(request, timeout):
        payloads.append(json.loads(request.data))
        return Response(output_response(text, [annotation]))
    monkeypatch.setattr("iip.research.urlopen", post)
    result = ResearchService(Settings(openai_key="test"), repository).search("Example Institute")
    assert "[NIRF report](<https://www.nirfindia.org/example.pdf>)" in result.summary
    assert result.sources[0].url.endswith("example.pdf")
    assert payloads[0]["tools"][0]["type"] == "web_search"
    assert payloads[0]["tools"][0]["external_web_access"] is True


def test_search_requires_sources_and_handles_missing_keys(repository, monkeypatch):
    with pytest.raises(ResearchError, match="Configure"):
        ResearchService(Settings(), repository).search("Example Institute")
    monkeypatch.setattr("iip.research.urlopen", lambda *a, **k: Response(output_response("Unsourced narrative")))
    with pytest.raises(ResearchError, match="citations"):
        ResearchService(Settings(openai_key="test"), repository).search("Example Institute")


def test_synthesis_failure_preserves_discovered_sources(repository, monkeypatch):
    def post(request, timeout):
        if "openai" in request.full_url:
            raise HTTPError(request.full_url, 401, "Invalid key", {}, io.BytesIO())
        return Response(tavily_response())
    monkeypatch.setattr("iip.research.urlopen", post)
    result = ResearchService(Settings(tavily_key="t", openai_key="o"), repository).search("Example Institute")
    assert result.sources and result.provider == "Tavily"
    assert any("unavailable" in gap for gap in result.missing_information)


@pytest.mark.parametrize("provider,key_field", [
    ("gemini", "gemini_key"), ("anthropic", "anthropic_key"),
    ("groq", "groq_key"), ("openrouter", "openrouter_key"),
])
def test_alternative_providers_use_correct_auth_and_validate_citations(repository, monkeypatch, provider, key_field):
    synthesis = {"summary": "Example finding to review", "claims": [{"topic": "Admissions", "statement": "812 registrations", "source_ids": ["S1"], "caveat": "Source submission; not independently verified"}], "missing_information": ["Current affiliation"]}
    text = json.dumps(synthesis)
    calls = []
    def post(request, timeout):
        calls.append(request)
        if "tavily" in request.full_url:
            return Response(tavily_response())
        if provider == "gemini":
            return Response({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}], "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50, "thoughtsTokenCount": 10}})
        if provider == "anthropic":
            return Response({"stop_reason": "end_turn", "content": [{"type": "text", "text": text}], "usage": {"input_tokens": 100, "output_tokens": 60}})
        return Response({"choices": [{"finish_reason": "stop", "message": {"content": text}}], "usage": {"prompt_tokens": 100, "completion_tokens": 60}})
    monkeypatch.setattr("iip.research.urlopen", post)
    configuration = Settings(provider=provider, tavily_key="search", **{key_field: "provider-secret"})
    service = ResearchService(configuration, repository)
    result = service.search("Example Institute")
    assert len(result.claims) == 1 and result.claims[0].source_ids == ["S1"]
    assert result.provider.startswith("Tavily + ")
    assert repository.usage()["input_tokens"] == 100 and repository.usage()["output_tokens"] == 60
    assert service.search("Example Institute").cached and len(calls) == 2
    request = calls[1]
    payload = json.loads(request.data)
    assert "provider-secret" not in request.full_url and "provider-secret" not in repr(configuration)
    if provider == "gemini":
        assert request.get_header("X-goog-api-key") == "provider-secret"
        assert request.get_header("Authorization") is None
        assert payload["generationConfig"]["responseJsonSchema"]["additionalProperties"] is False
    elif provider == "anthropic":
        assert request.get_header("X-api-key") == "provider-secret"
        assert request.get_header("Anthropic-version") == "2023-06-01"
        assert payload["output_config"]["format"]["type"] == "json_schema"
    else:
        assert request.get_header("Authorization") == "Bearer provider-secret"
        if provider == "groq":
            assert payload["model"] == "openai/gpt-oss-20b"
            assert payload["response_format"]["type"] == "json_schema"
        else:
            assert payload["provider"]["require_parameters"] is True
            assert payload["response_format"]["type"] == "json_schema"


def test_explicit_provider_never_silently_uses_another_key(repository):
    configuration = Settings(provider="gemini", openai_key="openai", tavily_key="tavily")
    with pytest.raises(ResearchError, match="Google Gemini"):
        ResearchService(configuration, repository).search("Example Institute")
    assert repository.usage()["requests"] == 0


def test_alternative_provider_needs_live_source_discovery_key(repository):
    configuration = Settings(provider="gemini", gemini_key="gemini")
    assert configuration.synthesis_enabled and not configuration.research_enabled
    with pytest.raises(ResearchError, match="TAVILY_API_KEY"):
        ResearchService(configuration, repository).search("Example Institute")


def test_switching_provider_model_or_key_invalidates_cache(repository):
    configuration = Settings(provider="gemini", gemini_key="g", groq_key="r", tavily_key="t")
    variants = [configuration, replace(configuration, provider="groq"), replace(configuration, gemini_key="another"), replace(configuration, gemini_model="another-model")]
    arguments = ("Example", "Admissions", False, 6, True)
    assert len({ResearchService(v, repository)._cache_key(*arguments) for v in variants}) == 4


def test_auto_selects_available_non_openai_provider():
    configuration = Settings(gemini_key="gemini", groq_key="groq", tavily_key="search")
    assert configuration.selected_provider == "gemini" and configuration.research_enabled


def test_gemini_incomplete_response_preserves_sources(repository, monkeypatch):
    def post(request, timeout):
        if "tavily" in request.full_url:
            return Response(tavily_response())
        return Response({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial"}]}}]})
    monkeypatch.setattr("iip.research.urlopen", post)
    result = ResearchService(Settings(provider="gemini", gemini_key="g", tavily_key="t"), repository).search("Example Institute")
    assert result.sources and not result.claims and result.provider == "Tavily"
    assert any("incomplete" in gap for gap in result.missing_information)


def test_invalid_provider_fails_before_spending_quota(repository):
    with pytest.raises(ResearchError, match="Unknown AI_PROVIDER"):
        ResearchService(Settings(provider="unknown", tavily_key="t"), repository).search("Example Institute")
    assert repository.usage()["requests"] == 0


def test_other_groq_models_use_validated_json_object_mode(repository, monkeypatch):
    payloads = []
    def post(request, timeout):
        payloads.append(json.loads(request.data))
        if "tavily" in request.full_url:
            return Response(tavily_response())
        return Response({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"summary": "Unverified", "claims": [], "missing_information": ["University confirmation"]})}}]})
    monkeypatch.setattr("iip.research.urlopen", post)
    result = ResearchService(Settings(provider="groq", groq_key="g", groq_model="another-groq-model", tavily_key="t"), repository).search("Example Institute")
    assert result.provider == "Tavily + Groq"
    assert payloads[-1]["response_format"]["type"] == "json_object"


def test_exhausted_billing_quota_is_reported_without_wasted_retry(repository, monkeypatch):
    calls = []
    def fail(request, timeout):
        calls.append(request)
        body = json.dumps({"error": {"type": "insufficient_quota", "code": "insufficient_quota", "message": "Raw message contains secret-key"}}).encode()
        raise HTTPError(request.full_url, 429, "Limit", {}, io.BytesIO(body))
    monkeypatch.setattr("iip.research.urlopen", fail)
    with pytest.raises(ResearchError, match="billing credits") as exc:
        ResearchService(Settings(openai_key="secret-key"), repository).search("Example Institute")
    assert len(calls) == 1 and "secret-key" not in str(exc.value)
    assert repository.usage()["requests"] == 1
