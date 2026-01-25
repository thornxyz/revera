"""Web Search Agent - Fetches information from the web using Tavily."""

import time
import json
import logging
from dataclasses import dataclass

from tavily import AsyncTavilyClient

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.core.config import get_settings
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)


@dataclass
class WebSource:
    """A web search result."""

    url: str
    title: str
    content: str
    raw_content: str | None = None
    date: str | None = None
    score: float = 0.0
    relevance_score: float = 0.0  # Composite relevance score


QUERY_EXPANSION_PROMPT = """Generate 1-3 optimized search queries to comprehensively answer this research question.
For complex queries, create variations that explore different aspects.
For simple queries, return just one optimized version.

Original query: {query}

Output format (JSON):
{{
    "primary_query": "main optimized search query",
    "alternative_queries": ["alternative angle 1", "alternative angle 2"],
    "query_type": "factual|conceptual|comparative|temporal"
}}

Keep each query under 15 words and focused on retrievable facts."""


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
        """Execute web search with multi-query expansion and ranking."""
        start_time = time.perf_counter()

        # Check if web search is configured
        if not self.tavily:
            return AgentOutput(
                agent_name=self.name,
                result=[],
                metadata={"error": "Web search not configured. Set TAVILY_API_KEY."},
                latency_ms=0,
            )

        # Expand query into multiple search variations
        query_expansion = await self._expand_query(input.query)

        # Execute searches for all query variations
        all_sources = []
        search_metadata = []

        # Primary query
        primary_sources, tavily_answer = await self._search_tavily(
            query_expansion["primary_query"], input.constraints
        )
        all_sources.extend(primary_sources)
        search_metadata.append(
            {
                "query": query_expansion["primary_query"],
                "type": "primary",
                "results": len(primary_sources),
            }
        )

        # Alternative queries (if any)
        max_alternatives = input.constraints.get("max_alternative_queries", 2)
        for alt_query in query_expansion.get("alternative_queries", [])[
            :max_alternatives
        ]:
            if alt_query and alt_query != query_expansion["primary_query"]:
                alt_sources, _ = await self._search_tavily(
                    alt_query,
                    {
                        **input.constraints,
                        "max_web_results": 3,
                    },  # Fewer for alternatives
                )
                all_sources.extend(alt_sources)
                search_metadata.append(
                    {
                        "query": alt_query,
                        "type": "alternative",
                        "results": len(alt_sources),
                    }
                )

        # Deduplicate and rank by relevance
        unique_sources = self._deduplicate_and_rank(
            all_sources, input.query, query_expansion["query_type"]
        )

        # Limit to top results
        max_results = input.constraints.get("max_web_results", 5)
        top_sources = unique_sources[:max_results]

        # Format results with quality scores
        formatted_results = [
            {
                "url": s.url,
                "title": s.title,
                "content": s.content,
                "raw_content": s.raw_content,
                "date": s.date,
                "score": s.score,
                "relevance_score": s.relevance_score,
            }
            for s in top_sources
        ]

        latency = int((time.perf_counter() - start_time) * 1000)

        return AgentOutput(
            agent_name=self.name,
            result=formatted_results,
            metadata={
                "original_query": input.query,
                "query_expansion": query_expansion,
                "searches_performed": search_metadata,
                "total_results": len(formatted_results),
                "deduplicated_from": len(all_sources),
                "tavily_answer": tavily_answer,
            },
            latency_ms=latency,
        )

    async def _expand_query(self, query: str) -> dict:
        """Expand query into multiple search variations with robust error handling."""
        prompt = QUERY_EXPANSION_PROMPT.format(query=query)
        try:
            response = self.gemini.generate_json(
                prompt=prompt,
                temperature=0.4,
            )
            expansion = self._parse_json_response(response)

            # Ensure we have valid structure with validation
            if "primary_query" not in expansion or not expansion["primary_query"]:
                logger.warning(f"[{self.name}] Missing primary_query, using original")
                expansion["primary_query"] = query

            if "alternative_queries" not in expansion or not isinstance(
                expansion["alternative_queries"], list
            ):
                expansion["alternative_queries"] = []

            if "query_type" not in expansion or not expansion["query_type"]:
                expansion["query_type"] = "factual"

            return expansion

        except json.JSONDecodeError as e:
            logger.error(
                f"[{self.name}] Failed to parse query expansion: {e}\n"
                "Falling back to original query"
            )
            # Fallback to original query
            return {
                "primary_query": query,
                "alternative_queries": [],
                "query_type": "factual",
            }
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error in query expansion: {e}")
            # Fallback to original query
            return {
                "primary_query": query,
                "alternative_queries": [],
                "query_type": "factual",
            }

    def _deduplicate_and_rank(
        self, sources: list[WebSource], original_query: str, query_type: str
    ) -> list[WebSource]:
        """Deduplicate by URL and rank by relevance + freshness."""
        seen_urls = {}

        for source in sources:
            if source.url not in seen_urls:
                # Calculate composite relevance score
                relevance = source.score

                # Boost recent content for temporal queries
                if query_type == "temporal" and source.date:
                    # Simple recency boost (last 30 days get +0.1)
                    from datetime import datetime, timedelta

                    try:
                        pub_date = datetime.fromisoformat(
                            source.date.replace("Z", "+00:00")
                        )
                        days_old = (datetime.now(pub_date.tzinfo) - pub_date).days
                        if days_old <= 30:
                            relevance += 0.1
                    except:
                        pass

                # Boost longer, more detailed content
                content_length_score = min(len(source.content) / 2000, 0.1)
                relevance += content_length_score

                source.relevance_score = relevance
                seen_urls[source.url] = source

        # Sort by relevance score
        return sorted(seen_urls.values(), key=lambda s: s.relevance_score, reverse=True)

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
        if not self.tavily:
            return [], None

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
