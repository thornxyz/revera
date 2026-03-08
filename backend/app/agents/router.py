"""Router Agent - Classifies query complexity to select the right execution path."""

import json
import logging
import re
import time

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.core.config import ROUTER_DIRECT_MAX_WORDS, ROUTER_RESEARCH_MIN_WORDS
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """Classify a research query into exactly one tier. Reply with ONLY valid JSON.

{"tier": "DIRECT"|"FOCUSED"|"RESEARCH", "focused_tool": "rag"|"web"|null}

DIRECT: Greetings, conversational replies, pure arithmetic, very simple one-word definitions — no retrieval needed.
FOCUSED: Single-domain lookup where one source type clearly suffices.
  focused_tool="rag" when internal documents are available and the query asks about their contents.
  focused_tool="web" when the query needs fresh/current information from the internet.
RESEARCH: Complex, multi-faceted, comparative, causal, or synthesising questions requiring multiple sources."""


class RouterAgent(BaseAgent):
    """
    Classifies query complexity into DIRECT, FOCUSED, or RESEARCH tiers.

    Uses fast regex heuristics first; falls back to a cheap LLM call only
    when the heuristic cannot determine the tier confidently.
    """

    name = "router"

    # Compiled at class level — shared across all instances
    _DIRECT_RE = re.compile(
        r"^(hi|hello|hey|thanks|thank you|ok|okay|sure|great|got it|sounds good"
        r"|continue|go on|tell me more|elaborate|yes|no|yep|nope|alright|cool"
        r"|perfect|awesome|understood|makes sense)\b",
        re.IGNORECASE,
    )
    _WEB_SIGNALS = re.compile(
        r"\b(latest|current|today|right now|news|price|stock|live|real.?time"
        r"|recent|this week|this month|this year|20[2-3]\d)\b",
        re.IGNORECASE,
    )
    _RESEARCH_SIGNALS = re.compile(
        r"\b(compare|contrast|difference between|versus|vs\.?|pros and cons"
        r"|trade.?off|overview|summarize all|summarise all"
        r"|analyz|analys|evaluate|assess|explain how|what caused"
        r"|why did|why does|implications|impact of|relationship between"
        r"|how does .+ affect|what are the effects)\b",
        re.IGNORECASE,
    )
    _DOC_SIGNALS = re.compile(
        r"\b(document|file|uploaded|in the pdf|according to the|from the report"
        r"|in my (document|file|pdf|report|paper)|the attached|this paper"
        r"|the study|the article)\b",
        re.IGNORECASE,
    )

    def __init__(self):
        self.gemini = get_gemini_client()

    def _heuristic_classify(
        self,
        query: str,
        has_documents: bool,
        use_web: bool,
    ) -> tuple[str | None, str | None]:
        """
        Attempt classification via regex heuristics.

        Returns (tier, focused_tool) or (None, None) if ambiguous.
        """
        q = query.strip()
        word_count = len(q.split())

        # --- DIRECT: conversational openers (only if the greeting IS the query) ---
        m = self._DIRECT_RE.match(q)
        if m:
            # Check that the rest of the query (after the greeting) has no
            # substantive content — at most trailing punctuation / filler.
            remainder = q[m.end() :].strip(" ,!.\t")
            if not remainder or word_count <= 5:
                return "DIRECT", None

        # --- DIRECT: very short non-questions ---
        if word_count <= ROUTER_DIRECT_MAX_WORDS and "?" not in q:
            return "DIRECT", None

        # --- RESEARCH: strong multi-faceted signals ---
        if self._RESEARCH_SIGNALS.search(q):
            return "RESEARCH", None
        if word_count >= ROUTER_RESEARCH_MIN_WORDS:
            return "RESEARCH", None
        if q.count("?") > 1:
            return "RESEARCH", None

        # --- FOCUSED: determine which tool ---
        has_web_signal = bool(self._WEB_SIGNALS.search(q))
        has_doc_signal = bool(self._DOC_SIGNALS.search(q))

        # Explicit doc reference always points to RAG
        if has_doc_signal and has_documents:
            return "FOCUSED", "rag"

        # Documents present, no freshness signal → prefer RAG
        if has_documents and not has_web_signal:
            return "FOCUSED", "rag"

        # Freshness signal + web enabled → web search
        if has_web_signal and use_web:
            return "FOCUSED", "web"

        # Competing signals (has docs AND web signal)
        if has_documents and has_web_signal:
            # If web is off, RAG is the only option — no need for LLM
            if not use_web:
                return "FOCUSED", "rag"
            return None, None

        # Short single-sentence question, no competing signals
        if word_count <= 15 and q.endswith("?"):
            if has_documents:
                return "FOCUSED", "rag"
            if use_web:
                return "FOCUSED", "web"

        # Ambiguous
        return None, None

    async def _llm_classify(
        self,
        query: str,
        has_documents: bool,
        use_web: bool,
    ) -> tuple[str, str | None]:
        """
        Cheap LLM call for ambiguous queries.
        Falls back to RESEARCH on any failure (safest default).
        """
        context_hint = (
            f"Context: has_internal_documents={has_documents}, web_enabled={use_web}"
        )
        prompt = f"{context_hint}\nQuery: {query}"
        try:
            raw = await self.gemini.generate_json_async(
                prompt=prompt,
                system_instruction=ROUTER_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=60,
            )
            data = json.loads(raw)
            tier = data.get("tier", "RESEARCH")
            if tier not in ("DIRECT", "FOCUSED", "RESEARCH"):
                tier = "RESEARCH"
            focused_tool = data.get("focused_tool")
            if focused_tool not in ("rag", "web", None):
                focused_tool = None
            return tier, focused_tool
        except Exception as e:
            logger.warning(
                f"[{self.name}] LLM classification failed, defaulting to RESEARCH: {e}"
            )
            return "RESEARCH", None

    async def run(self, input: AgentInput) -> AgentOutput:
        start = time.perf_counter()

        has_documents = bool(input.context.get("has_documents", False))
        use_web = bool(input.constraints.get("use_web", True))

        tier, focused_tool = self._heuristic_classify(
            input.query, has_documents, use_web
        )
        method = "heuristic"

        if tier is None:
            tier, focused_tool = await self._llm_classify(
                input.query, has_documents, use_web
            )
            method = "llm"

        # Apply use_web=False override: can't do web-focused without web
        if not use_web and focused_tool == "web":
            if has_documents:
                focused_tool = "rag"
            else:
                # No retrieval possible — answer from LLM knowledge
                tier = "DIRECT"
                focused_tool = None

        # If FOCUSED but no tool could be determined, fall back to RESEARCH
        if tier == "FOCUSED" and focused_tool is None:
            tier = "RESEARCH"

        latency = int((time.perf_counter() - start) * 1000)
        logger.info(
            f"[{self.name}] tier={tier}, focused_tool={focused_tool}, "
            f"method={method}, latency={latency}ms"
        )

        return AgentOutput(
            agent_name=self.name,
            result={"tier": tier, "focused_tool": focused_tool},
            metadata={"method": method},
            latency_ms=latency,
        )
