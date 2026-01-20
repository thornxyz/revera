"""Google Gemini client wrapper for embeddings and LLM inference."""

from google import genai
from google.genai import types

from app.core.config import get_settings


class GeminiClient:
    """Wrapper for Google Gemini API."""

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.embedding_model = settings.gemini_embedding_model
        self.reasoning_model = settings.gemini_reasoning_model
        self.fast_model = settings.gemini_fast_model

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        result = self.client.models.embed_content(
            model=self.embedding_model,
            contents=text,
        )
        return result.embeddings[0].values

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        result = self.client.models.embed_content(
            model=self.embedding_model,
            contents=texts,
        )
        return [e.values for e in result.embeddings]

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        use_fast_model: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate text response from LLM."""
        model = self.fast_model if use_fast_model else self.reasoning_model

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        if system_instruction:
            config.system_instruction = system_instruction

        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        return response.text

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        use_fast_model: bool = False,
        temperature: float = 0.3,
    ) -> str:
        """Generate structured JSON response."""
        model = self.fast_model if use_fast_model else self.reasoning_model

        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
        )

        if system_instruction:
            config.system_instruction = system_instruction

        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        return response.text


# Singleton instance
_gemini_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Get or create Gemini client instance."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client
