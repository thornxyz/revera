"""Google Gemini client wrapper for embeddings and LLM inference."""

import logging
from google import genai
from google.genai import types

from app.core.config import get_settings, GEMINI_EMBEDDING_MODEL, GEMINI_MODEL

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API."""

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.embedding_model = GEMINI_EMBEDDING_MODEL
        self.model = GEMINI_MODEL

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        result = self.client.models.embed_content(
            model=self.embedding_model,
            contents=text,
        )
        if result.embeddings and len(result.embeddings) > 0:
            values = result.embeddings[0].values
            if values is not None:
                return values
        return []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        embeddings: list[list[float]] = []
        batch_size = 100  # Gemini API limit for BatchEmbedContents

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            result = self.client.models.embed_content(
                model=self.embedding_model,
                contents=[
                    types.Content(parts=[types.Part(text=text)]) for text in batch
                ],
            )
            if result.embeddings is None:
                continue
            embeddings.extend(
                [e.values for e in result.embeddings if e.values is not None]
            )

        return embeddings

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Generate text response from LLM."""
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
        )

        if system_instruction:
            config.system_instruction = system_instruction

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text or ""

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate structured JSON response.

        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum output tokens

        Returns:
            Raw response text (should be valid JSON)
        """
        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
        )

        if max_tokens is not None:
            config.max_output_tokens = max_tokens

        if system_instruction:
            config.system_instruction = system_instruction

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            response_text = response.text or ""

            # Log response metadata for monitoring
            response_length = len(response_text)
            logger.debug(
                f"[Gemini] JSON generation complete. "
                f"Length: {response_length} chars, "
                f"Temperature: {temperature}"
            )

            # Validate response is not empty
            if not response_text.strip():
                logger.warning("[Gemini] Received empty response from model")
                return "{}"

            # Log preview of response for debugging (only first 300 chars)
            if logger.isEnabledFor(logging.DEBUG):
                preview = response_text[:300] + ("..." if response_length > 300 else "")
                logger.debug(f"[Gemini] Response preview: {preview}")

            return response_text

        except Exception as e:
            logger.error(f"[Gemini] Error generating JSON response: {e}", exc_info=True)
            raise


# Singleton instance
_gemini_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Get or create Gemini client instance."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client
