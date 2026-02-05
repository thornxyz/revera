"""
Service for generating short chat titles from queries and filenames.
Uses spaCy NLP for intelligent title generation.
Models are cached in ./models_cache/spacy/ directory.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

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


class SpacyTitleGenerator:
    """
    NLP-based title generation using spaCy.

    Extracts noun phrases, named entities, and key terms while preserving
    compound terms like "machine learning" and maintaining natural phrasing.
    """

    def __init__(self, nlp_model):
        """
        Initialize with a spaCy language model.

        Args:
            nlp_model: Pre-loaded spaCy model (e.g., en_core_web_sm)
        """
        self.nlp = nlp_model

    def generate(self, query: str, max_words: int = 5) -> str:
        """
        Generate a natural title using NLP-based extraction.

        Algorithm:
        1. Handle short queries (≤2 words) - return as-is
        2. Parse with spaCy for POS tagging and entity recognition
        3. Extract noun chunks (preserves compounds like "machine learning")
        4. Extract named entities (proper nouns like "Python", "TensorFlow")
        5. Extract important nouns (NOUN, PROPN tags)
        6. Add context verbs if meaningful (e.g., "compare", "analyze")
        7. Score and rank: named_entities > noun_chunks > nouns > verbs
        8. Maintain natural word order from original query
        9. Limit to max_words
        10. Title case formatting

        Examples:
            >>> gen.generate("What are the main benefits of machine learning?")
            "Benefits Machine Learning"

            >>> gen.generate("How do neural networks process information?")
            "Neural Networks Process Information"

            >>> gen.generate("Compare Python and JavaScript")
            "Python JavaScript Comparison"

        Args:
            query: The research query string
            max_words: Maximum words in title (default: 5)

        Returns:
            Short, natural title with preserved context
        """
        if not query or not query.strip():
            return "New Chat"

        # Clean query
        cleaned = query.strip().rstrip("?.!")
        words = cleaned.split()

        # Handle short queries - use as-is (preserve "Hello", "What is AI", etc.)
        if len(words) <= 2:
            return " ".join(word.capitalize() for word in words)

        # Parse with spaCy
        doc = self.nlp(cleaned)

        # Extract candidates with positions for ordering
        candidates = []

        # 1. Extract noun chunks (high priority - preserves compounds)
        for chunk in doc.noun_chunks:
            # Get the root noun phrase without determiners/articles
            chunk_text = chunk.text.lower()

            # Skip pure articles/determiners
            if chunk_text in {"a", "an", "the", "this", "that", "these", "those"}:
                continue

            # Remove leading articles/determiners from chunk
            chunk_words = []
            for token in chunk:
                # Skip determiners and some common question words
                if token.pos_ in {"DET"} or token.lower_ in {
                    "what",
                    "which",
                    "whose",
                }:
                    continue
                chunk_words.append(token.text.lower())

            if chunk_words:
                cleaned_chunk = " ".join(chunk_words)
                candidates.append(
                    {
                        "text": cleaned_chunk,
                        "start": chunk.start,
                        "priority": 3,  # High priority
                        "type": "noun_chunk",
                    }
                )

        # 2. Extract named entities (highest priority)
        for ent in doc.ents:
            candidates.append(
                {
                    "text": ent.text.lower(),
                    "start": ent.start,
                    "priority": 4,  # Highest priority
                    "type": "entity",
                }
            )

        # 3. Extract important standalone nouns (medium priority)
        for token in doc:
            if token.pos_ in {"NOUN", "PROPN"} and not token.is_stop:
                # Check if already covered by noun chunk or entity
                already_included = any(
                    token.text.lower() in c["text"]
                    for c in candidates
                    if c["type"] in {"noun_chunk", "entity"}
                )
                if not already_included:
                    candidates.append(
                        {
                            "text": token.text.lower(),
                            "start": token.i,
                            "priority": 2,  # Medium priority
                            "type": "noun",
                        }
                    )

        # 4. Add meaningful verbs for context (low priority)
        # Only include if they add value - skip generic ones like "explain", "tell"
        meaningful_verbs = {
            "compare",
            "analyze",
            "understand",
            "learn",
            "implement",
            "build",
            "create",
            "optimize",
            "improve",
        }
        for token in doc:
            if token.pos_ == "VERB" and token.lemma_ in meaningful_verbs:
                candidates.append(
                    {
                        "text": token.text.lower(),
                        "start": token.i,
                        "priority": 1,  # Low priority
                        "type": "verb",
                    }
                )

        # Remove duplicates (keep highest priority)
        seen_texts = {}
        for candidate in candidates:
            text = candidate["text"]
            if (
                text not in seen_texts
                or candidate["priority"] > seen_texts[text]["priority"]
            ):
                seen_texts[text] = candidate

        # Sort by priority (desc) then by position in query (asc) to maintain natural order
        unique_candidates = sorted(
            seen_texts.values(), key=lambda x: (-x["priority"], x["start"])
        )

        # Select top candidates up to max_words (count actual words)
        selected = []
        word_count = 0
        for candidate in unique_candidates:
            candidate_words = candidate["text"].split()
            if word_count + len(candidate_words) <= max_words:
                selected.append(candidate)
                word_count += len(candidate_words)
            if word_count >= max_words:
                break

        # Sort selected by original position to maintain natural order
        selected.sort(key=lambda x: x["start"])

        # Build title
        if selected:
            title_parts = [c["text"] for c in selected]
            title = " ".join(title_parts)
            # Title case each word
            title = " ".join(word.capitalize() for word in title.split())
            return title

        # Fallback: no candidates found
        return "New Chat"


def _initialize_spacy():
    """
    Load spaCy model from cache or download if missing.

    Returns:
        SpacyTitleGenerator instance with loaded model
    """
    import spacy
    from pathlib import Path

    # Use centralized models_cache directory (same as ColBERT/BM25)
    models_cache = Path("./models_cache/spacy")
    models_cache.mkdir(parents=True, exist_ok=True)

    model_name = "en_core_web_sm"
    model_path = models_cache / model_name

    logger.info(f"[TITLE] Checking for spaCy model at {model_path}...")

    # Try loading from cache first
    if model_path.exists():
        logger.info(f"[TITLE] Loading from cache: {model_path}")
        nlp = spacy.load(model_path)
        logger.info("[TITLE] ✓ spaCy title generator ready (loaded from cache)")
        return SpacyTitleGenerator(nlp)

    # Try loading from system-wide installation
    try:
        nlp = spacy.load(model_name)
        logger.info("[TITLE] ✓ spaCy title generator ready (loaded from system)")
        return SpacyTitleGenerator(nlp)
    except OSError:
        pass  # Model not in system, proceed to download

    # Model not found - download it automatically
    logger.info("[TITLE] spaCy model not found. Downloading to models_cache...")
    _download_model_to_cache(model_path, model_name)

    # Load from cache after download
    nlp = spacy.load(model_path)
    logger.info("[TITLE] ✓ spaCy title generator ready (auto-downloaded)")
    return SpacyTitleGenerator(nlp)


def _download_model_to_cache(model_path, model_name):
    """Download spaCy model and save to cache directory."""
    import subprocess
    import sys
    import shutil
    import tempfile
    from pathlib import Path

    model_url = "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

    # Download to temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Check if we're in a uv environment
        uv_path = shutil.which("uv")

        logger.info("[TITLE] Downloading model (12MB)...")
        if uv_path:
            # Use uv pip if available
            result = subprocess.run(
                [
                    uv_path,
                    "pip",
                    "install",
                    "--target",
                    str(temp_path),
                    model_url,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            # Fallback to regular pip
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--target",
                    str(temp_path),
                    model_url,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        if result.returncode != 0:
            raise Exception(f"Download failed: {result.stderr}")

        # Find the installed model directory
        # spaCy models install to: temp_path/en_core_web_sm/en_core_web_sm-3.8.0/
        possible_locations = [
            temp_path / model_name / f"{model_name}-3.8.0",
            temp_path / model_name / model_name,
            temp_path / model_name,
        ]

        installed_model = None
        for loc in possible_locations:
            if loc.exists() and (loc / "meta.json").exists():
                installed_model = loc
                break

        if not installed_model:
            # List what we got
            contents = list(temp_path.rglob("*"))
            raise Exception(
                f"Model not found in expected location. Contents: {contents[:10]}"
            )

        # Copy to cache
        logger.info(f"[TITLE] Copying model to cache: {model_path}")
        shutil.copytree(installed_model, model_path, dirs_exist_ok=True)
        logger.info("[TITLE] ✓ Model cached successfully")


# Singleton instance
_title_generator: Optional[SpacyTitleGenerator] = None


def _get_title_generator() -> SpacyTitleGenerator:
    """Get or initialize the singleton title generator."""
    global _title_generator
    if _title_generator is None:
        _title_generator = _initialize_spacy()
    return _title_generator


def generate_title_from_query(query: str, max_words: int = 5) -> str:
    """
    Generate a short, meaningful title from a research query.

    Public API function using spaCy NLP for intelligent title generation.

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
    generator = _get_title_generator()
    return generator.generate(query, max_words)


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
