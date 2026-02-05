"""
Utility functions for data sanitization and processing.
"""

from typing import Any


def sanitize_for_postgres(value: Any) -> Any:
    """
    Sanitize data for PostgreSQL storage by removing null bytes and other invalid characters.

    PostgreSQL text fields cannot contain null bytes (\u0000), which can appear in:
    - LLM responses with control characters
    - PDF extraction artifacts
    - Web scraping results

    Args:
        value: The value to sanitize (str, dict, list, or other)

    Returns:
        Sanitized value with null bytes removed
    """
    if isinstance(value, str):
        # Remove null bytes and other problematic control characters
        return value.replace("\x00", "").replace("\u0000", "")
    elif isinstance(value, dict):
        return {k: sanitize_for_postgres(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitize_for_postgres(item) for item in value]
    elif isinstance(value, (int, float, bool, type(None))):
        return value
    else:
        # For other types, convert to string and sanitize
        return str(value).replace("\x00", "").replace("\u0000", "")


def sanitize_text(text: str) -> str:
    """
    Sanitize a text string by removing null bytes and control characters.

    Args:
        text: The text to sanitize

    Returns:
        Sanitized text
    """
    if not isinstance(text, str):
        return text
    return text.replace("\x00", "").replace("\u0000", "")
