"""
backend/ai_engine.py

OpenAI API integration for CSV Doctor.
Handles dataset analysis (issue detection + code generation) and follow-up chat.
"""

import json
import os
from typing import List

from openai import OpenAI, APIError, RateLimitError, AuthenticationError


def _get_client() -> OpenAI:
    """Create an OpenAI client using the API key from the environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Please add it to your .env file."
        )
    return OpenAI(api_key=api_key)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """You are CSV Doctor, an expert data engineering assistant helping students learn to clean messy datasets.

You will receive:
1. A dataset profile (shape, column stats, duplicate count, sample rows)
2. Relevant data engineering rules from a rulebook

Your job is to:
- Identify ALL data quality issues present in the dataset
- Explain each issue clearly in plain English for a beginner
- Generate complete, runnable Python/Pandas cleaning code

IMPORTANT RULES:
- Only report issues that are actually present in the data (do not invent problems)
- Be specific: name the exact column(s) affected
- Severity levels: "high" (data is unusable without fixing), "medium" (will cause analysis errors), "low" (best practice improvement)
- The cleaning code must be self-contained: assume the CSV is loaded as a DataFrame named `df`
- The cleaning code must save the result as `df_cleaned`
- The cleaning code must be complete and runnable without modification
- Include comments in the code explaining each step

You MUST respond with valid JSON matching this exact schema:
{
  "issues": [
    {
      "column": "column_name or 'multiple' or 'entire dataset'",
      "issue_type": "one of: missing_values | duplicates | type_mismatch | invalid_values | inconsistent_format | outliers | other",
      "description": "plain English explanation of the issue",
      "severity": "high | medium | low",
      "suggested_fix": "brief description of how to fix it"
    }
  ],
  "cleaning_code": "complete Python/Pandas code string",
  "summary": "2-3 sentence overall assessment of the dataset quality"
}"""


CHAT_SYSTEM_PROMPT = """You are CSV Doctor, an expert data engineering assistant helping students learn to clean messy datasets.

You are in a follow-up conversation. The user has already uploaded a CSV dataset and received an initial analysis. 
You have the dataset profile available as context.

Answer questions clearly and helpfully. When explaining code, use concrete examples from the actual dataset.
If asked to simplify code, provide a simpler version. If asked to explain a concept, use beginner-friendly language.
Keep responses focused and practical."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_dataset(profile: dict, rules: str) -> dict:
    """
    Analyze a dataset profile and return identified issues + cleaning code.

    Args:
        profile: The dataset profile dict from profiler.py
        rules: Formatted rulebook rules string from rulebook.py

    Returns:
        dict with keys: issues (list), cleaning_code (str), summary (str)

    Raises:
        ValueError: If the API key is missing or response is malformed
        RuntimeError: For API errors (rate limits, network issues)
    """
    client = _get_client()

    user_message = f"""Please analyze this dataset and identify all data quality issues.

## Dataset Profile
{profile.get('raw_summary', 'No summary available')}

## Full Profile (JSON)
{json.dumps(profile, indent=2, default=str)}

## {rules}

Based on the dataset profile and the rulebook rules above, identify all data quality issues and generate complete cleaning code."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,  # Low temperature for consistent, factual analysis
            max_tokens=4096,
        )
    except AuthenticationError:
        raise ValueError(
            "Invalid OpenAI API key. Please check your OPENAI_API_KEY in the .env file."
        )
    except RateLimitError:
        raise RuntimeError(
            "OpenAI rate limit reached. Please wait a moment and try again."
        )
    except APIError as e:
        raise RuntimeError(f"OpenAI API error: {e}")

    raw = response.choices[0].message.content
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}\nRaw response: {raw[:500]}")

    # Validate required keys
    if "issues" not in result:
        result["issues"] = []
    if "cleaning_code" not in result:
        result["cleaning_code"] = "# No cleaning code generated\ndf_cleaned = df.copy()"
    if "summary" not in result:
        result["summary"] = "Analysis complete."

    return result


def chat_followup(profile: dict, history: List[dict], user_message: str) -> str:
    """
    Handle a follow-up question in the context of the analyzed dataset.

    Args:
        profile: The dataset profile dict (for context)
        history: List of prior messages [{"role": "user"|"assistant", "content": str}]
        user_message: The new user question

    Returns:
        The assistant's reply as a string

    Raises:
        ValueError: If the API key is missing
        RuntimeError: For API errors
    """
    client = _get_client()

    # Build the system message with dataset context
    profile_context = profile.get("raw_summary", "Dataset profile not available.")
    system_content = f"""{CHAT_SYSTEM_PROMPT}

## Current Dataset Profile
{profile_context}"""

    # Build message list: system + history + new user message
    messages = [{"role": "system", "content": system_content}]

    # Include up to last 10 history messages to stay within context limits
    recent_history = history[-10:] if len(history) > 10 else history
    messages.extend(recent_history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4,
            max_tokens=1024,
        )
    except AuthenticationError:
        raise ValueError(
            "Invalid OpenAI API key. Please check your OPENAI_API_KEY in the .env file."
        )
    except RateLimitError:
        raise RuntimeError(
            "OpenAI rate limit reached. Please wait a moment and try again."
        )
    except APIError as e:
        raise RuntimeError(f"OpenAI API error: {e}")

    return response.choices[0].message.content
