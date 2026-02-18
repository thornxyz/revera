"""Google Gemini client wrapper for embeddings and LLM inference."""

import asyncio
import logging
from google import genai
from google.genai import types

from app.core.config import (
    get_settings,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_MODEL,
    GEMINI_IMAGE_MODEL,
    GEMINI_THINKING_LEVEL,
)

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API."""

    def __init__(self, timeout_seconds: int = 300):
        """
        Initialize Gemini client.

        Args:
            timeout_seconds: Request timeout in seconds (default: 300 = 5 minutes)
        """
        settings = get_settings()
        # HttpOptions expects milliseconds; convert from seconds.
        timeout_ms = int(timeout_seconds * 1000)
        http_options = types.HttpOptions(timeout=timeout_ms)
        self.client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=http_options,
        )
        self.embedding_model = GEMINI_EMBEDDING_MODEL
        self.model = GEMINI_MODEL
        self.image_model = GEMINI_IMAGE_MODEL
        self.thinking_level = GEMINI_THINKING_LEVEL
        self.default_timeout = timeout_seconds

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
        """Generate text response from LLM (minimal thinking, no streaming)."""
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            # Use minimal thinking so the token budget mostly goes to the answer.
            # This method is used for simple tasks (e.g. title generation)
            # where deep thinking is unnecessary.
            thinking_config=types.ThinkingConfig(
                thinking_level="minimal",  # type: ignore
            ),
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
        timeout_seconds: int | None = None,
    ) -> str:
        """
        Generate structured JSON response.

        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum output tokens
            timeout_seconds: Request timeout in seconds (overrides default)

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

        if timeout_seconds is not None:
            config.http_options = types.HttpOptions(timeout=int(timeout_seconds * 1000))

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

    async def generate_json_async(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """
        Generate structured JSON response asynchronously (respects asyncio.wait_for timeout).

        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum output tokens
            timeout_seconds: Request timeout in seconds (overrides default)

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

        if timeout_seconds is not None:
            config.http_options = types.HttpOptions(timeout=int(timeout_seconds * 1000))

        try:
            # Use async API which properly respects asyncio cancellation
            response = await self.client.aio.models.generate_content(
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
                                # Skip parts without text
                                if not hasattr(part, "text") or not part.text:
                                    continue

                                # Check if this is a thought part (part.thought is a boolean flag)
                                if hasattr(part, "thought") and part.thought is True:
                                    logger.info(
                                        f"[Gemini] Thought chunk: {len(part.text)} chars"
                                    )
                                    yield {
                                        "type": "thought",
                                        "content": part.text,
                                    }
                                else:
                                    # Regular text content
                                    yield {"type": "text", "content": part.text}
                # Fallback: use chunk.text directly
                elif hasattr(chunk, "text") and chunk.text:
                    yield {"type": "text", "content": chunk.text}

            logger.info("[Gemini] Stream complete")

        except Exception as e:
            logger.error(f"[Gemini] Error in streaming generation: {e}", exc_info=True)
            raise

    # =========================================
    # Multimodal (Image) Methods
    # =========================================

    async def generate_image_description(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> str:
        """
        Generate a detailed text description from an image for RAG indexing.

        Uses Gemini Vision to extract searchable content from the image.

        Args:
            image_bytes: Raw image bytes
            mime_type: MIME type (e.g., "image/jpeg", "image/png")

        Returns:
            Detailed text description of the image
        """
        try:
            # Use v1alpha for media_resolution support
            settings = get_settings()
            vision_client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options={"api_version": "v1alpha"},
            )

            prompt = """Analyze this image and provide a detailed description for search indexing.
Include:
1. Main subjects and objects visible
2. Text or labels if any (transcribe exactly)
3. Colors, layout, and visual structure
4. Context and purpose of the image
5. Any diagrams, charts, or data visualizations

Be thorough but factual - only describe what you can see."""

            response = await vision_client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part(text=prompt),
                            types.Part(
                                inline_data=types.Blob(
                                    mime_type=mime_type,
                                    data=image_bytes,
                                ),
                            ),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.3,  # Lower temp for factual description
                    max_output_tokens=2048,
                ),
            )

            description = response.text or ""
            logger.info(
                f"[Gemini] Generated image description: {len(description)} chars"
            )
            return description

        except Exception as e:
            logger.error(
                f"[Gemini] Error generating image description: {e}", exc_info=True
            )
            raise

    async def generate_with_images(
        self,
        prompt: str,
        images: list[dict],
        system_instruction: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
    ) -> str:
        """
        Generate a response using text prompt and images (multimodal synthesis).

        Args:
            prompt: Text prompt/question
            images: List of dicts with 'bytes' and 'mime_type' keys
            system_instruction: Optional system instruction
            temperature: Sampling temperature (default 1.0 for Gemini 3)
            max_tokens: Maximum output tokens

        Returns:
            Generated text response
        """
        try:
            # Build multimodal content parts
            parts: list[types.Part] = [types.Part(text=prompt)]

            for img in images:
                parts.append(
                    types.Part.from_bytes(
                        data=img["bytes"],
                        mime_type=img["mime_type"],
                    )
                )

            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

            if system_instruction:
                config.system_instruction = system_instruction

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[types.Content(parts=parts)],
                config=config,
            )

            return response.text or ""

        except Exception as e:
            logger.error(f"[Gemini] Error in multimodal generation: {e}", exc_info=True)
            raise

    async def generate_stream_with_images(
        self,
        prompt: str,
        images: list[dict],
        system_instruction: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        include_thoughts: bool = True,
    ):
        """
        Stream a response using text prompt and images (multimodal streaming).

        Yields dicts with 'type' and 'content' like generate_stream.

        Args:
            prompt: Text prompt/question
            images: List of dicts with 'bytes' and 'mime_type' keys
            system_instruction: Optional system instruction
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            include_thoughts: Whether to include thinking tokens

        Yields:
            dict: {"type": "thought"|"text", "content": str}
        """
        try:
            # Build multimodal content parts
            parts: list[types.Part] = [types.Part(text=prompt)]

            for img in images:
                parts.append(
                    types.Part.from_bytes(
                        data=img["bytes"],
                        mime_type=img["mime_type"],
                    )
                )

            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

            if system_instruction:
                config.system_instruction = system_instruction

            if include_thoughts:
                config.thinking_config = types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_level=self.thinking_level,  # type: ignore
                )

            response_stream = await self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=[types.Content(parts=parts)],
                config=config,
            )

            async for chunk in response_stream:
                if hasattr(chunk, "candidates") and chunk.candidates:
                    for candidate in chunk.candidates:
                        if hasattr(candidate, "content") and candidate.content:
                            for part in candidate.content.parts or []:
                                # Skip parts without text
                                if not hasattr(part, "text") or not part.text:
                                    continue

                                # part.thought is a boolean flag, content is in part.text
                                if hasattr(part, "thought") and part.thought is True:
                                    yield {"type": "thought", "content": part.text}
                                else:
                                    yield {"type": "text", "content": part.text}
                elif hasattr(chunk, "text") and chunk.text:
                    yield {"type": "text", "content": chunk.text}

            logger.info("[Gemini] Multimodal stream complete")

        except Exception as e:
            logger.error(f"[Gemini] Error in multimodal streaming: {e}", exc_info=True)
            raise

    # =========================================
    # Image Generation (Text-to-Image)
    # =========================================

    async def generate_image(
        self,
        prompt: str,
        number_of_images: int = 1,
    ) -> list[bytes]:
        """
        Generate images from a text prompt.

        Args:
            prompt: Text description of the image to generate
            number_of_images: How many images to generate (default 1)

        Returns:
            List of raw image bytes
        """
        try:
            logger.info(
                f"[Gemini] Generating {number_of_images} image(s) "
                f"for prompt: {prompt[:50]}..."
            )

            # SDK call is synchronous — run in a thread to avoid
            # blocking the event loop during image generation.
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.image_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    candidate_count=number_of_images,
                ),
            )

            image_bytes_list: list[bytes] = []

            if not response.candidates:
                logger.warning("[Gemini] No candidates returned from image generation")
                return []

            for candidate in response.candidates:
                logger.debug(
                    f"[Gemini] Candidate: finish_reason={candidate.finish_reason}, safety_ratings={candidate.safety_ratings}"
                )
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        logger.debug(
                            f"[Gemini] Part: has_inline_data={bool(part.inline_data)}, has_text={bool(part.text)}"
                        )
                        if part.inline_data and part.inline_data.data:
                            image_bytes_list.append(part.inline_data.data)
                        elif part.text:
                            logger.debug(
                                f"[Gemini] Part text (not an image): {part.text[:100]}"
                            )

            logger.info(
                f"[Gemini] Successfully generated {len(image_bytes_list)} image(s)"
            )
            return image_bytes_list

        except Exception as e:
            logger.error(f"[Gemini] Error generating image: {e}", exc_info=True)
            raise


# Singleton instance
_gemini_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Get or create Gemini client instance."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client
