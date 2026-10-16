import os

from iip.config import load_settings


def test_saved_keys_reload_without_mutating_process_environment(tmp_path, monkeypatch):
    monkeypatch.setattr("iip.config.ROOT", tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    assert not load_settings().gemini_key
    env_file.write_text("GEMINI_API_KEY=test-first\n", encoding="utf-8")
    assert load_settings().gemini_key == "test-first"
    env_file.write_text("GEMINI_API_KEY=test-second\n", encoding="utf-8")
    assert load_settings().gemini_key == "test-second"
    assert "GEMINI_API_KEY" not in os.environ
    env_file.write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    assert not load_settings().gemini_key


def test_configuration_precedence_and_file_tuning(tmp_path, monkeypatch):
    monkeypatch.setattr("iip.config.ROOT", tmp_path)
    monkeypatch.delenv("DAILY_API_REQUEST_LIMIT", raising=False)
    monkeypatch.delenv("RESEARCH_CACHE_HOURS", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-file\nDAILY_API_REQUEST_LIMIT=8\nRESEARCH_CACHE_HOURS=invalid\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-process")
    assert load_settings().openai_key == "test-process"
    configured = load_settings({"OPENAI_API_KEY": "test-secrets", "DAILY_API_REQUEST_LIMIT": 12})
    assert configured.openai_key == "test-secrets"
    assert configured.daily_limit == 12
    assert configured.cache_hours == 24
    monkeypatch.delenv("OPENAI_API_KEY")
    assert load_settings().openai_key == "test-file"
    assert load_settings().daily_limit == 8
