"""
Service for generating short chat titles from queries and filenames.
Uses Google Gemini 3 Flash for intelligent title generation.
"""

import logging
import re

from app.llm.gemini import GeminiClient

logger = logging.getLogger(__name__)


def generate_title_from_query(query: str, max_words: int = 5) -> str:
    """
    Generate a short, meaningful title from a research query using Gemini 3 Flash.

    Uses Google Gemini 3 Flash for intelligent, context-aware title generation.

    Examples:
        >>> generate_title_from_query("What are the main benefits of machine learning?")
        "Benefits Machine Learning"

        >>> generate_title_from_query("How does photosynthesis work in plants?")
        "Photosynthesis Work Plants"

        >>> generate_title_from_query("Explain transformer architecture")
        "Transformer Architecture"

    Args:
        query: The research query string
        max_words: Maximum words in title (default: 5)

    Returns:
        Short title (e.g., "Machine Learning Benefits")
    """
    if not query or not query.strip():
        return "New Chat"

    # Handle very short queries
    cleaned = query.strip().rstrip("?.!")
    words = cleaned.split()
    if len(words) <= 2:
        return " ".join(word.capitalize() for word in words)

    # Use Gemini 3 Flash for title generation
    gemini = GeminiClient(timeout=10)

    system_instruction = """You are a title generator. Your task is to extract key concepts from a query and create a short, descriptive title.

Instructions:
1. Identify the main concepts, technologies, and topics in the query
2. Remove all question words: what, how, why, who, when, where, which
3. Remove filler words: is, are, the, a, an, do, does, can, could, will, would, should, I, me, my, in, on, for
4. Keep important nouns, verbs (compare, analyze, implement), and technical terms
5. Use title case (capitalize each important word)
6. Maximum 5 words
7. Return ONLY the title, no explanation or quotes

Examples:
Query: "What are the main benefits of machine learning?"
Benefits Machine Learning

Query: "How does photosynthesis work in plants?"
Photosynthesis Plants

Query: "Compare Python and JavaScript for web development"
Python Javascript Comparison

Query: "Explain transformer architecture in detail"
Transformer Architecture

Query: "How do I implement a REST API in FastAPI?"
Rest Api Fastapi Implementation"""

    user_prompt = f"{query}"

    title = gemini.generate(
        prompt=user_prompt,
        system_instruction=system_instruction,
        max_tokens=20,
    ).strip()

    # Remove quotes if present
    title = title.strip("\"'")

    # Sanitize and validate
    if not title or len(title) == 0 or title.startswith("{"):
        raise ValueError(f"Invalid title generated from query: {title}")

    # Ensure title case
    title = " ".join(word.capitalize() for word in title.split())
    return sanitize_title(title, max_length=100)


def generate_title_from_filename(filename: str, max_words: int = 5) -> str:
    """
    Generate a title from a PDF filename.

    Algorithm:
    - Remove .pdf extension
    - Replace underscores/hyphens with spaces
    - Remove extra whitespace
    - Title case
    - Limit to max_words

    Examples:
        >>> generate_title_from_filename("machine_learning_guide.pdf")
        "Machine Learning Guide"

        >>> generate_title_from_filename("2024-Q4-Report.pdf")
        "2024 Q4 Report"

        >>> generate_title_from_filename("very-long-filename-with-many-words.pdf")
        "Very Long Filename With Many"

    Args:
        filename: The PDF filename
        max_words: Maximum words in title (default: 5)

    Returns:
        Short title derived from filename
    """
    if not filename or not filename.strip():
        return "Untitled Document"

    # Remove .pdf extension (case insensitive)
    cleaned = re.sub(r"\.pdf$", "", filename.strip(), flags=re.IGNORECASE)

    # Replace underscores and hyphens with spaces
    cleaned = cleaned.replace("_", " ").replace("-", " ")

    # Remove extra whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return "Untitled Document"

    # Split into words and limit
    words = cleaned.split()[:max_words]

    # Title case
    title = " ".join(word.capitalize() for word in words)

    return title if title else "Untitled Document"


def sanitize_title(title: str, max_length: int = 100) -> str:
    """
    Sanitize a title to ensure it's safe for storage and display.

    Args:
        title: The title to sanitize
        max_length: Maximum character length (default: 100)

    Returns:
        Sanitized title
    """
    if not title:
        return "New Chat"

    # Remove any control characters or excessive whitespace
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", title)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rsplit(" ", 1)[0] + "..."

    return sanitized if sanitized else "New Chat"
