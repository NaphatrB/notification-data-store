"""LLM client for calling Ollama API to extract structured pricing data."""

import json
import logging

import httpx

from app.parser.config import LLM_ENDPOINT, LLM_MODEL

logger = logging.getLogger(__name__)

# Max input length in characters (~2k tokens ≈ 8k chars for English)
MAX_INPUT_CHARS = 8000

SYSTEM_PROMPT = """\
You are a pricing data extraction assistant. You receive notification messages \
that contain pricing information for products sold by weight (kg).

You must extract structured pricing data and respond with ONLY valid JSON. \
No explanations, no markdown, no code fences — just raw JSON.

Required JSON schema:
{
  "supplier": "string (name of the supplier/sender)",
  "currency": "string (e.g. THB, USD, EUR)",
  "total_kg": number (total weight in kg),
  "items": [
    {
      "size": "string (product size/category)",
      "grade": "string (product grade/quality)",
      "quantity_kg": number (weight in kg for this item),
      "price_per_kg": number (price per kg)
    }
  ],
  "confidence": number (0.0 to 1.0, your confidence in the extraction accuracy)
}

Rules:
- Extract ALL line items found in the message
- If currency is not explicitly stated, infer from context
- If supplier name is not clear, use the sender/title
- Set confidence lower if the message is ambiguous
- Respond with ONLY the JSON object, nothing else\
"""


def _build_prompt(title: str | None, text: str | None, big_text: str | None) -> str:
    """Build the user prompt from notification fields."""
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if text:
        parts.append(f"Text: {text}")
    if big_text:
        parts.append(f"Full message: {big_text}")

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

    Returns parsed JSON dict on success, None on failure.
    """
    prompt = _build_prompt(title, text, big_text)

    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 1024,
        },
        "format": "json",
    }

    url = f"{LLM_ENDPOINT.rstrip('/')}/api/generate"

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("LLM HTTP error: %s", e)
        return None

    try:
        result = response.json()
        raw_text = result.get("response", "")
        return json.loads(raw_text)
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("LLM response not valid JSON: %s", e)
        return None
