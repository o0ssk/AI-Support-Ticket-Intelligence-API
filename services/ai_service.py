"""
services/ai_service.py — AI integration layer.

This module is responsible for ONE thing: taking a customer message
and returning structured analysis from the AI.

Why a separate service (not inside the route)?
  - The route should only handle HTTP concerns (request parsing, responses).
  - The AI logic can be tested independently of Flask.
  - If we switch AI providers, we change ONLY this file.
  - Clean separation of concerns = easier debugging.

Flow:
  analyze_ticket(message)
    → build prompt
    → call OpenRouter API
    → parse JSON response
    → validate fields
    → return clean dict
"""

import json
import os
from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError

from config import get_config
from utils.logger import logger

# ------------------------------------------------------------------
# Allowed values for AI output fields.
# The AI is instructed to use ONLY these values.
# We validate against these sets after every AI response.
# ------------------------------------------------------------------
ALLOWED_CATEGORIES = {"payment", "shipping", "account", "product", "technical", "other"}
ALLOWED_PRIORITIES = {"low", "medium", "high", "urgent"}
ALLOWED_SENTIMENTS = {"positive", "neutral", "negative"}

# ------------------------------------------------------------------
# The system prompt tells the AI exactly what role it plays and
# what format to respond in. Being explicit about JSON format and
# allowed values dramatically improves reliability.
# ------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert customer support analyst.

Your job is to analyze customer support tickets and return a structured JSON analysis.

You MUST respond with ONLY valid JSON — no markdown, no explanation, no code blocks.
Do not wrap the JSON in ```json or any other formatting.

The JSON must have exactly these fields:
{
  "category": one of ["payment", "shipping", "account", "product", "technical", "other"],
  "priority": one of ["low", "medium", "high", "urgent"],
  "sentiment": one of ["positive", "neutral", "negative"],
  "summary": "A single sentence (max 20 words) summarizing the customer's issue.",
  "suggested_action": "A single sentence (max 25 words) describing the recommended action for the support team."
}

Priority guidelines:
- urgent: financial loss, security breach, complete service failure
- high: major functionality broken, payment issues
- medium: partial functionality affected, delays
- low: general questions, minor inconveniences

Do not add any fields beyond what is listed above.
Do not include explanations outside the JSON object.
"""


def _build_client() -> OpenAI:
    """
    Build and return an OpenAI-compatible client pointed at OpenRouter.

    OpenRouter is 100% OpenAI API compatible — we just change base_url and api_key.
    This means our code works with any OpenAI-compatible provider.
    """
    config = get_config()
    return OpenAI(
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        timeout=30.0,  # seconds — fail fast if AI is unresponsive
    )


def _parse_ai_response(raw_content: str) -> dict:
    """
    Parse the raw string response from the AI into a Python dict.

    The AI is instructed to return plain JSON, but LLMs sometimes
    wrap output in markdown code blocks (```json ... ```).
    This function strips that defensively before parsing.

    Args:
        raw_content: The raw string from the AI message content.

    Returns:
        Parsed dictionary.

    Raises:
        ValueError: If the content is not valid JSON after cleanup.
    """
    content = raw_content.strip()

    # Strip markdown code fences if the model added them anyway
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first line (```json or ```) and last line (```)
        content = "\n".join(lines[1:-1]).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("AI response is not valid JSON. Raw: %s", raw_content[:300])
        raise ValueError(f"AI returned invalid JSON: {e}") from e


def _validate_ai_result(data: dict) -> dict:
    """
    Validate that the AI's parsed response has all required fields
    with allowed values.

    Why validate AI output?
    LLMs are probabilistic — they can occasionally return wrong values,
    hallucinated fields, or slightly different spellings. Validating
    before saving to the database ensures data integrity.

    Args:
        data: Parsed dict from the AI response.

    Returns:
        The same dict if all fields are valid.

    Raises:
        ValueError: If any required field is missing or has an invalid value.
    """
    required_fields = ["category", "priority", "sentiment", "summary", "suggested_action"]

    # Check all required fields are present
    for field in required_fields:
        if field not in data:
            raise ValueError(f"AI response missing required field: '{field}'")
        if not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(f"AI response field '{field}' must be a non-empty string")

    # Normalise to lowercase for consistent validation
    category = data["category"].lower().strip()
    priority = data["priority"].lower().strip()
    sentiment = data["sentiment"].lower().strip()

    if category not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"AI returned invalid category '{category}'. "
            f"Allowed: {ALLOWED_CATEGORIES}"
        )
    if priority not in ALLOWED_PRIORITIES:
        raise ValueError(
            f"AI returned invalid priority '{priority}'. "
            f"Allowed: {ALLOWED_PRIORITIES}"
        )
    if sentiment not in ALLOWED_SENTIMENTS:
        raise ValueError(
            f"AI returned invalid sentiment '{sentiment}'. "
            f"Allowed: {ALLOWED_SENTIMENTS}"
        )

    # Return cleaned, normalised values
    return {
        "category": category,
        "priority": priority,
        "sentiment": sentiment,
        "summary": data["summary"].strip(),
        "suggested_action": data["suggested_action"].strip(),
    }


def analyze_ticket(message: str) -> dict:
    """
    Main public function: analyze a customer support ticket using AI.

    This is the only function routes should call from this module.

    Args:
        message: The raw customer support message.

    Returns:
        A validated dict with keys:
        {category, priority, sentiment, summary, suggested_action}

    Raises:
        ConnectionError: If the AI API is unreachable.
        TimeoutError: If the AI API times out.
        ValueError: If the AI returns an invalid or malformed response.
        RuntimeError: For unexpected AI API errors.
    """
    config = get_config()
    model = config.OPENROUTER_MODEL

    logger.info("Sending ticket to AI model: %s", model)
    logger.debug("Ticket message (first 100 chars): %s", message[:100])

    client = _build_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this support ticket:\n\n{message}"},
            ],
            temperature=0.1,   # Low temperature = more deterministic/consistent JSON
            max_tokens=300,    # The response is always a small JSON object
        )

    except APIConnectionError as e:
        logger.error("AI API connection failed: %s", str(e))
        raise ConnectionError("Could not connect to AI service. Please try again.") from e

    except APITimeoutError as e:
        logger.error("AI API request timed out")
        raise TimeoutError("AI service timed out. Please try again.") from e

    except APIStatusError as e:
        logger.error("AI API returned error status %d: %s", e.status_code, e.message)
        raise RuntimeError(
            f"AI service returned an error (HTTP {e.status_code})."
        ) from e

    # Extract the text content from the response.
    # Free-tier models on OpenRouter can return an empty choices list
    # when they are rate-limited, overloaded, or temporarily unavailable.
    if not response.choices:
        # OpenRouter sometimes returns an error payload in a non-standard field
        raw = response.model_dump() if hasattr(response, "model_dump") else {}
        provider_error = raw.get("error", {})
        if provider_error:
            error_msg = provider_error.get("message", "Unknown provider error")
            logger.error("OpenRouter provider error: %s", error_msg)
            raise RuntimeError(f"AI provider error: {error_msg}")
        logger.error(
            "AI returned zero choices. Full response: %s",
            response.model_dump_json() if hasattr(response, "model_dump_json") else str(response),
        )
        raise ValueError(
            "AI returned no content (empty choices). "
            "The model may be rate-limited or temporarily unavailable."
        )

    raw_content = response.choices[0].message.content

    if not raw_content:
        logger.error(
            "AI returned None content. Full response: %s",
            response.model_dump_json() if hasattr(response, "model_dump_json") else str(response),
        )
        raise ValueError("AI returned an empty response.")

    logger.info("AI response received. Parsing and validating...")
    logger.debug("Raw AI response: %s", raw_content[:500])

    # Parse JSON and validate all fields
    parsed = _parse_ai_response(raw_content)
    validated = _validate_ai_result(parsed)

    logger.info(
        "AI analysis complete — category=%s priority=%s sentiment=%s",
        validated["category"],
        validated["priority"],
        validated["sentiment"],
    )

    return validated
