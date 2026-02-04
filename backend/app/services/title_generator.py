"""
Service for generating short chat titles from queries and filenames.
Uses keyword extraction algorithm to create 3-5 word titles.
"""

import re
from typing import Optional

# Common question words to remove from titles
QUESTION_WORDS = {
    "what",
    "how",
    "why",
    "when",
    "where",
    "who",
    "which",
    "whose",
    "whom",
    "can",
    "could",
    "will",
    "would",
    "should",
    "may",
    "might",
    "must",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "please",
    "tell",
    "explain",
    "describe",
    "show",
    "give",
    "provide",
}

# Common stop words to remove from titles
STOP_WORDS = {
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "about",
    "into",
    "through",
    "during",
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
    "my",
    "your",
    "his",
    "its",
    "our",
    "their",
    "this",
    "that",
    "these",
    "those",
}


def generate_title_from_query(query: str, max_words: int = 5) -> str:
    """
    Generate a short, meaningful title from a research query.

    Algorithm:
    1. Remove question words (what, how, why, etc.)
    2. Remove stop words (is, the, a, an, etc.)
    3. Extract key nouns and important terms
    4. Title case capitalization
    5. Limit to max_words

    Examples:
        >>> generate_title_from_query("What are the main benefits of machine learning?")
        "Main Benefits Machine Learning"

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

    # Remove punctuation and normalize
    cleaned = query.strip().rstrip("?.!")

    # Split into words (alphanumeric only)
    words = re.findall(r"\b\w+\b", cleaned.lower())

    if not words:
        return "New Chat"

    # Filter out question words and stop words
    filtered = [
        word for word in words if word not in QUESTION_WORDS and word not in STOP_WORDS
    ]

    # If too few words remain, fall back to original words (minus question words)
    if len(filtered) < 2:
        filtered = [w for w in words if w not in QUESTION_WORDS]

    # Still empty? Use first words of original query
    if not filtered:
        filtered = words[:max_words]

    # Take first max_words
    title_words = filtered[:max_words]

    # Title case
    title = " ".join(word.capitalize() for word in title_words)

    # Final fallback
    if not title:
        title = "New Chat"

    return title


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
