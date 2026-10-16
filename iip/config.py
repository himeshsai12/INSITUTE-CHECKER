from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
IST = timezone(timedelta(hours=5, minutes=30))
PROVIDER_LABELS = {"openai": "OpenAI", "gemini": "Google Gemini", "anthropic": "Anthropic Claude", "groq": "Groq", "openrouter": "OpenRouter"}
GROQ_SEARCH_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b", "openai/gpt-oss-safeguard-20b"}


def today():
    return datetime.now(IST).date()


def now_iso():
    return datetime.now(IST).isoformat(timespec="seconds")


def _integer(name, default, low, high, values=None):
    try:
        return max(low, min(high, int((values or {}).get(name, default))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # repr=False prevents credentials appearing in debug output.
    openai_key: str = field(default="", repr=False)
    tavily_key: str = field(default="", repr=False)
    gemini_key: str = field(default="", repr=False)
    anthropic_key: str = field(default="", repr=False)
    groq_key: str = field(default="", repr=False)
    openrouter_key: str = field(default="", repr=False)
    provider: str = "auto"
    model: str = "gpt-4.1-mini"
    gemini_model: str = "gemini-3.8-flash"
    anthropic_model: str = "claude-haiku-5-5"
    groq_model: str = "openai/gpt-oss-20b"
    openrouter_model: str = "google/gemini-2.5-flash"
    cache_hours: int = 24
    daily_limit: int = 30
    max_tokens: int = 2400
    timeout: int = 45
    database: Path = ROOT / "data" / "intelligence.db"

    @property
    def research_enabled(self):
        return bool(self.tavily_key or (self.selected_provider == "openai" and self.openai_key) or (self.selected_provider == "groq" and self.groq_key and self.groq_model in GROQ_SEARCH_MODELS))

    def provider_key(self, provider):
        return {"openai": self.openai_key, "gemini": self.gemini_key, "anthropic": self.anthropic_key, "groq": self.groq_key, "openrouter": self.openrouter_key}.get(provider, "")

    def provider_model(self, provider):
        return {"openai": self.model, "gemini": self.gemini_model, "anthropic": self.anthropic_model, "groq": self.groq_model, "openrouter": self.openrouter_model}.get(provider, "")

    @property
    def available_providers(self):
        return [p for p in PROVIDER_LABELS if self.provider_key(p)]

    @property
    def selected_provider(self):
        if self.provider != "auto":
            return self.provider
        return next(iter(self.available_providers), None)

    @property
    def synthesis_enabled(self):
        return bool(self.provider_key(self.selected_provider))

    @property
    def selected_model(self):
        return self.provider_model(self.selected_provider)


def load_settings(secrets=None, env_path=None):
    # Read the file afresh. Loading it into os.environ makes saved key changes
    # stick to the first value seen by a long-running Streamlit process.
    env_file = dotenv_values(env_path or ROOT / ".env")
    def value(name, default=""):
        return str((secrets or {}).get(name) or os.getenv(name) or env_file.get(name) or default).strip()
    tuning = {name: value(name) for name in ["RESEARCH_CACHE_HOURS", "DAILY_API_REQUEST_LIMIT", "OPENAI_MAX_OUTPUT_TOKENS", "API_TIMEOUT_SECONDS"]}
    return Settings(
        openai_key=value("OPENAI_API_KEY"),
        tavily_key=value("TAVILY_API_KEY"),
        gemini_key=value("GEMINI_API_KEY") or value("GOOGLE_API_KEY"),
        anthropic_key=value("ANTHROPIC_API_KEY"),
        groq_key=value("GROQ_API_KEY"),
        openrouter_key=value("OPENROUTER_API_KEY"),
        provider=value("AI_PROVIDER", "auto").casefold(),
        model=value("OPENAI_MODEL", "gpt-4.1-mini"),
        gemini_model=value("GEMINI_MODEL", "gemini-3.8-flash"),
        anthropic_model=value("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        groq_model=value("GROQ_MODEL", "openai/gpt-oss-20b"),
        openrouter_model=value("OPENROUTER_MODEL", "google/gemini-2.5-flash"),
        cache_hours=_integer("RESEARCH_CACHE_HOURS", 24, 1, 168, tuning),
        daily_limit=_integer("DAILY_API_REQUEST_LIMIT", 30, 1, 500, tuning),
        max_tokens=_integer("OPENAI_MAX_OUTPUT_TOKENS", 2400, 500, 8000, tuning),
        timeout=_integer("API_TIMEOUT_SECONDS", 45, 10, 90, tuning),
        database=Path(value("IIP_DATABASE_PATH", str(ROOT / "data" / "intelligence.db"))),
    )
