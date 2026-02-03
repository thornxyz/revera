"""Google Gemini client wrapper for embeddings and LLM inference."""

import logging
from google import genai
from google.genai import types

from app.core.config import (
    get_settings,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_MODEL,
    GEMINI_THINKING_LEVEL,
)

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API."""

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.embedding_model = GEMINI_EMBEDDING_MODEL
        self.model = GEMINI_MODEL
        self.thinking_level = GEMINI_THINKING_LEVEL

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

    async def embed_texts_async(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts asynchronously (non-blocking)."""
        embeddings: list[list[float]] = []
        batch_size = 100

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            result = await self.client.aio.models.embed_content(
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

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        include_thoughts: bool = True,
    ):
        """
        Stream text response from LLM with optional thinking/reasoning.

        Yields dicts with 'type' and 'content':
        - type='thought': reasoning/thinking content (if enabled)
        - type='text': actual response content

        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum output tokens
            include_thoughts: Whether to include thinking/reasoning tokens

        Yields:
            dict: {"type": "thought"|"text", "content": str}
        """
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        if system_instruction:
            config.system_instruction = system_instruction

        # Enable thinking if requested (supported on Gemini 3+ models)
        # Note: Gemini 3 models use thinking_level parameter
        if include_thoughts:
            config.thinking_config = types.ThinkingConfig(
                include_thoughts=True,
                thinking_level=self.thinking_level,  # type: ignore
            )

        try:
            # Use ASYNC streaming API for true token-by-token streaming
            response_stream = await self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=config,
            )

            async for chunk in response_stream:
                # Check for thinking/reasoning in parts
                if hasattr(chunk, "candidates") and chunk.candidates:
                    for candidate in chunk.candidates:
                        if hasattr(candidate, "content") and candidate.content:
                            for part in candidate.content.parts or []:
                                # Yield thought content if present (must be string, not bool)
                                if hasattr(part, "thought") and part.thought:
                                    if isinstance(part.thought, str):
                                        logger.info(
                                            f"[Gemini] Thought chunk: {len(part.thought)} chars"
                                        )
                                        yield {
                                            "type": "thought",
                                            "content": part.thought,
                                        }
                                    else:
                                        logger.info(
                                            f"[Gemini] Skipping non-string thought: "
                                            f"type={type(part.thought).__name__}, value={part.thought}"
                                        )
                                # Yield text content
                                if hasattr(part, "text") and part.text:
                                    yield {"type": "text", "content": part.text}
                # Fallback: use chunk.text directly
                elif hasattr(chunk, "text") and chunk.text:
                    yield {"type": "text", "content": chunk.text}

            logger.info("[Gemini] Stream complete")

        except Exception as e:
            logger.error(f"[Gemini] Error in streaming generation: {e}", exc_info=True)
            raise


# Singleton instance
_gemini_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Get or create Gemini client instance."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client
