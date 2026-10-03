"""
AIR AI Web Search Subsystem.
Provides real-time web search capability for the AIR AI appliance.
Multi-source search aggregator:
 1. Bing Web Search (Real-time live news, articles, and general web results)
 2. DuckDuckGo Instant Answer API (Knowledge cards, definitions)
 3. Wikipedia API (Encyclopedic context, biographies, science)
"""

import json
import logging
import urllib.parse
import urllib.request
import re
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger("hs_ai.web_search")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

class WebSearchEngine:
    """Fast, resilient web search aggregator for local LLM context augmentation."""

    @classmethod
    def search_bing(cls, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Scrape top Bing search results."""
        results = []
        try:
            url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            soup = BeautifulSoup(html, "html.parser")
            for b in soup.select("li.b_algo"):
                h2 = b.select_one("h2 a")
                snippet = b.select_one(".b_caption p, .b_lineclamp2, .b_snippet, .b_algoSlug")
                if h2:
                    title = h2.get_text(strip=True)
                    link = h2.get("href", "")
                    snip_text = snippet.get_text(strip=True) if snippet else ""
                    if title and link.startswith("http"):
                        results.append({
                            "title": title,
                            "url": link,
                            "snippet": snip_text
                        })
                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.debug(f"Bing search error: {e}")
        return results

    @classmethod
    def search_duckduckgo(cls, query: str) -> Optional[Dict[str, str]]:
        """Fetch DuckDuckGo Instant Answer card if available."""
        try:
            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            abstract = data.get("AbstractText", "")
            heading = data.get("Heading", "")
            source_url = data.get("AbstractURL", "")
            if abstract:
                return {
                    "title": heading or query,
                    "url": source_url or "https://duckduckgo.com",
                    "snippet": abstract
                }
        except Exception as e:
            logger.debug(f"DDG Instant Answer error: {e}")
        return None

    @classmethod
    def search_wikipedia(cls, query: str, max_results: int = 2) -> List[Dict[str, str]]:
        """Fetch Wikipedia search summaries."""
        results = []
        try:
            url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json"
            req = urllib.request.Request(url, headers={"User-Agent": "AIR-AI-Appliance/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("query", {}).get("search", [])
            for item in items[:max_results]:
                title = item.get("title", "")
                snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                link = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                results.append({
                    "title": title + " (Wikipedia)",
                    "url": link,
                    "snippet": snippet
                })
        except Exception as e:
            logger.debug(f"Wikipedia search error: {e}")
        return results

    @classmethod
    def search(cls, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Aggregate search from Bing, DuckDuckGo, and Wikipedia.
        Returns a dict with query, success status, and list of result items.
        """
        clean_query = query.strip()
        if not clean_query:
            return {"query": "", "success": False, "results": [], "source": "none"}

        logger.info(f"[WEB SEARCH] Searching web for: '{clean_query}'")
        combined_results: List[Dict[str, str]] = []
        seen_urls = set()

        # 1. Primary: Bing web search
        bing_res = cls.search_bing(clean_query, max_results=max_results)
        for r in bing_res:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                combined_results.append(r)

        # 2. Secondary: DuckDuckGo Instant Answer
        if len(combined_results) < max_results:
            ddg_card = cls.search_duckduckgo(clean_query)
            if ddg_card and ddg_card["url"] not in seen_urls:
                seen_urls.add(ddg_card["url"])
                combined_results.insert(0, ddg_card)

        # 3. Tertiary: Wikipedia fallback if results are sparse
        if len(combined_results) < 3:
            wiki_res = cls.search_wikipedia(clean_query, max_results=2)
            for r in wiki_res:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    combined_results.append(r)

        success = len(combined_results) > 0
        logger.info(f"[WEB SEARCH] Found {len(combined_results)} results for '{clean_query}'")
        return {
            "query": clean_query,
            "success": success,
            "results": combined_results[:max_results],
            "total": len(combined_results[:max_results])
        }

    @classmethod
    def format_search_context(cls, search_data: Dict[str, Any]) -> str:
        """Format web search results into a concise LLM context block."""
        results = search_data.get("results", [])
        if not results:
            return ""

        context_lines = [
            "\n[REAL-TIME WEB SEARCH RESULTS]",
            f"User Query: {search_data.get('query', '')}",
            "Below is current information retrieved from the web:"
        ]
        for i, item in enumerate(results, 1):
            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("snippet", "").replace("\n", " ").strip()
            context_lines.append(f"{i}. {title}")
            if snippet:
                context_lines.append(f"   Summary: {snippet}")
            if url:
                context_lines.append(f"   Source URL: {url}")

        context_lines.append(
            "\nInstructions: Answer the user's question using the real-time web search results above. "
            "Cite sources where relevant. If the search results do not cover the question, answer with your general knowledge."
        )
        return "\n".join(context_lines)
