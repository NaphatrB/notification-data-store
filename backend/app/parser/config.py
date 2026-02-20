"""Parser configuration — all from environment variables."""

import os


RAW_DATABASE_URL: str = os.environ.get(
    "RAW_DATABASE_URL",
    os.environ.get("DATABASE_URL", ""),
)

LLM_ENDPOINT: str = os.environ.get(
    "LLM_ENDPOINT",
    "http://llm.buffalo-cliff.ts.net:11434",
)

PARSER_BATCH_SIZE: int = int(os.environ.get("PARSER_BATCH_SIZE", "10"))

PARSER_NAME: str = os.environ.get("PARSER_NAME", "pricing_v1")

POLL_INTERVAL_SECONDS: int = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))

# Versioned parser identifier — bump when prompt changes
PARSER_VERSION: str = "pricing_v1_prompt1"

# LLM model name for Ollama
LLM_MODEL: str = os.environ.get("LLM_MODEL", "qwen3:8b")

# --------------------------------------------------------------------------
# Candidate filters (comma-separated allowlists, empty = accept all)
# --------------------------------------------------------------------------

def _parse_csv(env_key: str) -> list[str]:
    """Parse a comma-separated env var into a lowercase list, ignoring blanks."""
    raw = os.environ.get(env_key, "")
    return [v.strip().lower() for v in raw.split(",") if v.strip()] if raw.strip() else []


PARSER_SOURCE_FILTER: list[str] = _parse_csv("PARSER_SOURCE_FILTER")
PARSER_PACKAGE_FILTER: list[str] = _parse_csv("PARSER_PACKAGE_FILTER")
PARSER_APP_FILTER: list[str] = _parse_csv("PARSER_APP_FILTER")

# When True, events must also pass text heuristics (kg / numeric patterns)
# When False, all events matching the metadata filters are sent to the LLM
PARSER_TEXT_FILTER_ENABLED: bool = os.environ.get(
    "PARSER_TEXT_FILTER_ENABLED", "false"
).lower() in ("1", "true", "yes")
