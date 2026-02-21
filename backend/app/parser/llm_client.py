"""LLM client for calling Ollama API to extract structured pricing data."""

import json
import logging
import time
from pathlib import Path

import httpx

from app.parser.config import (
    LLM_CONNECT_TIMEOUT,
    LLM_ENDPOINT,
    LLM_FALLBACK_ENDPOINT,
    LLM_MODEL,
    LLM_READ_TIMEOUT,
)
from app.parser.metrics import (
    llm_call_duration,
    llm_call_total,
    llm_error_total,
    llm_prompt_tokens,
    llm_completion_tokens,
)

logger = logging.getLogger(__name__)

# Max input length in characters (~2k tokens ≈ 8k chars for English)
MAX_INPUT_CHARS = 8000

# Timeouts: short connect (detect sleeping host fast), long read (LLM generation)
_TIMEOUT = httpx.Timeout(connect=LLM_CONNECT_TIMEOUT, read=LLM_READ_TIMEOUT, write=30.0, pool=10.0)


class LLMUnavailableError(Exception):
    """Raised when the LLM endpoint is unreachable (host sleeping, connection refused, etc.).

    This is distinct from a *bad response* — the caller should NOT dead-letter
    the event, just back off and retry later.
    """
    pass


def check_llm_available() -> str | None:
    """Quick connectivity check — returns the reachable endpoint URL, or None.

    Tries primary first, then fallback.
    """
    for endpoint in (LLM_ENDPOINT, LLM_FALLBACK_ENDPOINT):
        if not endpoint:
            continue
        try:
            with httpx.Client(timeout=LLM_CONNECT_TIMEOUT) as client:
                r = client.get(f"{endpoint.rstrip('/')}/api/tags")
                if r.status_code == 200:
                    return endpoint
        except httpx.HTTPError:
            continue
    return None

# Load system prompt from external file so it's easy to tweak
_PROMPT_PATH = Path(__file__).with_name("system_prompt.txt")
SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_prompt(title: str | None, text: str | None, big_text: str | None) -> str:
    """Build the user prompt from notification fields.

    For WhatsApp group chats, big_text is the *expanded notification* showing
    the full chat history (multiple stacked messages), while text is just the
    latest individual message.  Sending big_text causes the LLM to re-parse
    old messages that were already processed in earlier events.

    Strategy:
    - Use text when it has real content (>20 chars, not a trivial reply).
    - Fall back to big_text only when text is absent or trivially short,
      since for 1:1 chats big_text may be the only source.
    """
    parts = []
    if title:
        parts.append(f"Sender: {title}")

    # Prefer text (latest message) over big_text (chat history)
    if text and len(text.strip()) > 20:
        parts.append(f"Message: {text}")
    elif big_text:
        parts.append(f"Message: {big_text}")
    elif text:
        parts.append(f"Message: {text}")

    content = "\n".join(parts)

    # Truncate if too long
    if len(content) > MAX_INPUT_CHARS:
        logger.warning(
            "Input truncated from %d to %d characters",
            len(content),
            MAX_INPUT_CHARS,
        )
        content = content[:MAX_INPUT_CHARS]

    return content


def call_llm(
    title: str | None,
    text: str | None,
    big_text: str | None,
) -> dict | None:
    """Call Ollama to extract pricing data.

    Returns parsed JSON dict on success (with _llm_meta injected), None on failure.
    """
    prompt = _build_prompt(title, text, big_text)

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 1024,
        },
        "format": "json",
    }

    # Build ordered list of endpoints to try: primary first, then fallback
    endpoints = [LLM_ENDPOINT]
    if LLM_FALLBACK_ENDPOINT and LLM_FALLBACK_ENDPOINT != LLM_ENDPOINT:
        endpoints.append(LLM_FALLBACK_ENDPOINT)

    llm_call_total.inc()
    t0 = time.monotonic()
    last_connect_err: Exception | None = None

    for endpoint in endpoints:
        url = f"{endpoint.rstrip('/')}/api/chat"
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.warning("LLM at %s unreachable: %s", endpoint, e)
            last_connect_err = e
            continue  # try next endpoint
        except httpx.HTTPError as e:
            duration = time.monotonic() - t0
            llm_call_duration.observe(duration)
            llm_error_total.inc()
            logger.error("LLM HTTP error at %s (%.1fs): %s", endpoint, duration, e)
            return None

        # Got a successful response from this endpoint
        duration = time.monotonic() - t0
        llm_call_duration.observe(duration)

        is_fallback = (endpoint != LLM_ENDPOINT)
        if is_fallback:
            logger.info("Using fallback LLM at %s", endpoint)

        raw_text = ""
        try:
            result = response.json()
            raw_text = result.get("message", {}).get("content", "")

            prompt_tokens = result.get("prompt_eval_count", 0)
            completion_tokens = result.get("eval_count", 0)
            model_used = result.get("model", LLM_MODEL)

            llm_prompt_tokens.inc(prompt_tokens)
            llm_completion_tokens.inc(completion_tokens)

            logger.info(
                "LLM call: %.1fs | endpoint=%s | model=%s | prompt_tokens=%d | completion_tokens=%d | response_len=%d",
                duration,
                "fallback" if is_fallback else "primary",
                model_used,
                prompt_tokens,
                completion_tokens,
                len(raw_text),
            )

            parsed = json.loads(raw_text)

            parsed["_llm_meta"] = {
                "duration_s": round(duration, 2),
                "model": model_used,
                "endpoint": endpoint,
                "is_fallback": is_fallback,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }

            return parsed
        except (json.JSONDecodeError, KeyError) as e:
            llm_error_total.inc()
            logger.error("LLM response not valid JSON (%.1fs): %s — raw: %s", duration, e, raw_text[:500])
            return None

    # All endpoints unreachable
    duration = time.monotonic() - t0
    llm_call_duration.observe(duration)
    llm_error_total.inc()
    logger.warning("All LLM endpoints unreachable (%.1fs)", duration)
    raise LLMUnavailableError(str(last_connect_err)) from last_connect_err
