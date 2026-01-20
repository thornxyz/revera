"""Web Search Agent - Fetches information from the web using Tavily."""

import time
from dataclasses import dataclass

from tavily import TavilyClient, AsyncTavilyClient

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.core.config import get_settings
from app.llm.gemini import get_gemini_client


@dataclass
class WebSource:
    """A web search result."""

    url: str
    title: str
    content: str
    raw_content: str | None = None
    date: str | None = None
    score: float = 0.0


QUERY_REWRITE_PROMPT = """Rewrite this research query into an optimal web search query.
Keep it concise (under 10 words) and focused on finding factual information.

Original query: {query}

Output only the rewritten search query, nothing else."""


class WebSearchAgent(BaseAgent):
    """
    Agent that searches the web using Tavily API.

    Tavily is specifically designed for LLM agents and provides:
    - Clean, LLM-ready content extraction
    - Advanced search depth for research queries
    - Built-in answer generation (optional)
    - Source scoring and ranking
    """

    name = "web_search"

    def __init__(self):
        self.settings = get_settings()
        self.gemini = get_gemini_client()

        # Initialize Tavily client if API key is available
        if self.settings.tavily_api_key:
            self.tavily = AsyncTavilyClient(api_key=self.settings.tavily_api_key)
        else:
            self.tavily = None

    async def run(self, input: AgentInput) -> AgentOutput:
        """Execute web search and return relevant sources."""
        start_time = time.perf_counter()

        # Check if web search is configured
        if not self.tavily:
            return AgentOutput(
                agent_name=self.name,
                result=[],
                metadata={
                    "error": "Web search not configured. Set WEB_SEARCH_API_KEY."
                },
                latency_ms=0,
            )

        # Rewrite query for better search results
        rewritten_query = await self._rewrite_query(input.query)

        # Execute Tavily search
        sources, tavily_answer = await self._search_tavily(
            rewritten_query, input.constraints
        )

        # Deduplicate by URL
        seen_urls = set()
        unique_sources = []
        for source in sources:
            if source.url not in seen_urls:
                seen_urls.add(source.url)
                unique_sources.append(source)

        # Format results
        formatted_results = [
            {
                "url": s.url,
                "title": s.title,
                "content": s.content,
                "raw_content": s.raw_content,
                "date": s.date,
                "score": s.score,
            }
            for s in unique_sources
        ]

        latency = int((time.perf_counter() - start_time) * 1000)

        return AgentOutput(
            agent_name=self.name,
            result=formatted_results,
            metadata={
                "original_query": input.query,
                "rewritten_query": rewritten_query,
                "total_results": len(formatted_results),
                "tavily_answer": tavily_answer,  # Optional quick answer from Tavily
            },
            latency_ms=latency,
        )

    async def _rewrite_query(self, query: str) -> str:
        """Rewrite query for optimal web search."""
        prompt = QUERY_REWRITE_PROMPT.format(query=query)
        rewritten = self.gemini.generate(
            prompt=prompt,
            temperature=0.3,
            max_tokens=50,
        )
        return rewritten.strip()

    async def _search_tavily(
        self,
        query: str,
        constraints: dict,
    ) -> tuple[list[WebSource], str | None]:
        """
        Search using Tavily API with advanced features.

        Returns:
            Tuple of (sources list, optional Tavily-generated answer)
        """
        try:
            # Determine search parameters based on constraints
            max_results = constraints.get("max_web_results", 5)
            include_raw = constraints.get("include_raw_content", False)

            # Use advanced search for research queries
            # This does deeper content extraction
            response = await self.tavily.search(
                query=query,
                search_depth="advanced",  # "basic" or "advanced"
                max_results=max_results,
                include_answer=True,  # Get a quick LLM-generated answer
                include_raw_content=include_raw,  # Full page content if needed
                include_images=False,
                # Optional: filter by domain
                # include_domains=["arxiv.org", "github.com"],
                # exclude_domains=["pinterest.com"],
            )

            sources = []
            for result in response.get("results", []):
                sources.append(
                    WebSource(
                        url=result.get("url", ""),
                        title=result.get("title", ""),
                        content=result.get("content", ""),
                        raw_content=result.get("raw_content"),
                        date=result.get("published_date"),
                        score=result.get("score", 0.0),
                    )
                )

            # Tavily can also provide a quick answer
            tavily_answer = response.get("answer")

            return sources, tavily_answer

        except Exception as e:
            # Log the error but don't crash
            print(f"Tavily search error: {e}")
            return [], None

    async def search_with_context(
        self,
        query: str,
        context: str,
        max_results: int = 5,
    ) -> list[WebSource]:
        """
        Context-aware search using Tavily's context feature.

        This is useful when you want to find sources that relate
        to both the query AND some additional context.
        """
        if not self.tavily:
            return []

        try:
            response = await self.tavily.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_answer=False,
            )

            return [
                WebSource(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    content=r.get("content", ""),
                    score=r.get("score", 0.0),
                )
                for r in response.get("results", [])
            ]
        except Exception:
            return []

    async def get_quick_answer(self, query: str) -> str | None:
        """
        Get a quick answer from Tavily without full source extraction.

        Useful for simple factual queries.
        """
        if not self.tavily:
            return None

        try:
            response = await self.tavily.search(
                query=query,
                search_depth="basic",
                max_results=3,
                include_answer=True,
            )
            return response.get("answer")
        except Exception:
            return None
