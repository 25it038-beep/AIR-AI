"""
AIR AI Real-Time Web Search & Temporal Context Subsystem.
Provides live web search, current news aggregation, and live temporal anchoring for the AIR AI appliance.

Sources:
 1. Google News Live RSS (Instant breaking news, current events, sports, tech, politics)
 2. DuckDuckGo Instant Answers & Knowledge Graph (Definitions, entity facts, direct answers)
 3. Wikipedia REST API (Direct encyclopedic extracts and biographies)
 4. Bing Web Search (General live web pages and articles)
"""

import json
import logging
import urllib.parse
import urllib.request
import re
import html as html_lib
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Any, Optional

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

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

# Keywords indicating the user is asking about current, live, or time-sensitive topics
LIVE_INTENT_KEYWORDS = {
    "today", "yesterday", "tomorrow", "tonight", "current", "currently", "latest",
    "now", "recent", "recently", "news", "weather", "price", "score", "match",
    "schedule", "who is", "who won", "election", "president", "prime minister",
    "stock", "crypto", "bitcoin", "time", "date", "year", "2024", "2025", "2026",
    "2027", "update", "live", "standing", "championship", "released", "release date"
}


class WebSearchEngine:
    """Fast, resilient web search & live data aggregator for local LLM context augmentation."""

    @classmethod
    def get_temporal_header(cls) -> str:
        """Return clear, unambiguous real-time temporal anchor."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        return (
            f"CRITICAL REAL-TIME TEMPORAL CONTEXT:\n"
            f"- Current Date: {date_str}\n"
            f"- Current Time: {time_str}\n"
            f"- Current Year: {now.year}\n"
            f"- System Timezone: Local System Clock\n"
        )

    @classmethod
    def is_live_query(cls, query: str) -> bool:
        """Detect whether a user prompt is asking for live, current, or time-dependent information."""
        if not query:
            return False
        q_lower = query.lower()
        # Direct word match
        words = set(re.findall(r"\b[a-z0-9]+\b", q_lower))
        if words & LIVE_INTENT_KEYWORDS:
            return True
        # Phrase match
        for phrase in ("who is the", "what is the current", "what is today", "what is the latest", "who won the"):
            if phrase in q_lower:
                return True
        return False

    @classmethod
    def search_live_news(cls, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Fetch fresh, real-time news articles from Google News RSS feed."""
        results = []
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for item in root.findall("./channel/item")[:max_results]:
                title = item.findtext("title", "").strip()
                pub_date = item.findtext("pubDate", "").strip()
                link = item.findtext("link", "").strip()
                if title:
                    snippet = f"Published: {pub_date}" if pub_date else "Recent news report"
                    results.append({
                        "title": title,
                        "url": link,
                        "snippet": snippet
                    })
        except Exception as e:
            logger.debug(f"[WEB SEARCH] Google News RSS error: {e}")
        return results

    @classmethod
    def search_duckduckgo(cls, query: str) -> List[Dict[str, str]]:
        """Fetch DuckDuckGo Instant Answer cards and related topic text."""
        results = []
        try:
            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            abstract = data.get("AbstractText", "").strip()
            heading = data.get("Heading", "").strip()
            source_url = data.get("AbstractURL", "").strip()
            if abstract:
                results.append({
                    "title": heading or query,
                    "url": source_url or "https://duckduckgo.com",
                    "snippet": abstract
                })

            for topic in data.get("RelatedTopics", [])[:3]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " ") or query,
                        "url": topic.get("FirstURL", "https://duckduckgo.com"),
                        "snippet": topic["Text"]
                    })
        except Exception as e:
            logger.debug(f"[WEB SEARCH] DDG error: {e}")
        return results

    @classmethod
    def search_wikipedia_rest(cls, query: str) -> Optional[Dict[str, str]]:
        """Fetch summary extract from Wikipedia REST API."""
        try:
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json"
            req = urllib.request.Request(search_url, headers={"User-Agent": "AIR-AI-Appliance/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            hits = data.get("query", {}).get("search", [])
            if not hits:
                return None
            top_title = hits[0].get("title", "")
            if not top_title:
                return None

            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(top_title.replace(' ', '_'))}"
            req_sum = urllib.request.Request(summary_url, headers={"User-Agent": "AIR-AI-Appliance/1.0"})
            with urllib.request.urlopen(req_sum, timeout=3.0) as resp_sum:
                sum_data = json.loads(resp_sum.read().decode("utf-8"))
            extract = sum_data.get("extract", "")
            if extract:
                return {
                    "title": f"{top_title} (Wikipedia)",
                    "url": sum_data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(top_title)}"),
                    "snippet": extract
                }
        except Exception as e:
            logger.debug(f"[WEB SEARCH] Wikipedia REST error: {e}")
        return None

    @classmethod
    def search_bing(cls, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Scrape Bing search results with HTML/regex parsing."""
        results = []
        try:
            url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                raw_html = resp.read().decode("utf-8", errors="ignore")

            if BeautifulSoup is not None:
                soup = BeautifulSoup(raw_html, "html.parser")
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
            else:
                items = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', raw_html, re.DOTALL)
                for item in items:
                    m_link = re.search(r'<h2><a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a></h2>', item, re.DOTALL)
                    if m_link:
                        link = m_link.group(1)
                        raw_title = m_link.group(2)
                        title = html_lib.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()
                        m_snip = re.search(r'<p[^>]*>(.*?)</p>', item, re.DOTALL)
                        snip_text = ""
                        if m_snip:
                            snip_text = html_lib.unescape(re.sub(r'<[^>]+>', '', m_snip.group(1))).strip()
                        if title and link.startswith("http"):
                            results.append({
                                "title": title,
                                "url": link,
                                "snippet": snip_text
                            })
                    if len(results) >= max_results:
                        break
        except Exception as e:
            logger.debug(f"[WEB SEARCH] Bing search error: {e}")
        return results

    @classmethod
    def search(cls, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Multi-source search aggregator combining:
         1. Live Google News RSS (for fresh current events, articles, dates)
         2. DuckDuckGo Instant Answers & Topics
         3. Wikipedia REST summary
         4. Bing Web Search
        """
        clean_query = query.strip()
        if not clean_query:
            return {"query": "", "success": False, "results": [], "total": 0}

        logger.info(f"[WEB SEARCH] Aggregating live web search for: '{clean_query}'")
        combined_results: List[Dict[str, str]] = []
        seen_titles = set()

        def add_unique(r_list):
            for item in r_list:
                t_key = re.sub(r"\W+", "", item.get("title", "").lower()[:35])
                if t_key and t_key not in seen_titles:
                    seen_titles.add(t_key)
                    combined_results.append(item)

        # 1. Check for live news / current event articles
        news_items = cls.search_live_news(clean_query, max_results=3)
        if news_items:
            add_unique(news_items)

        # 2. Bing Web search
        bing_items = cls.search_bing(clean_query, max_results=4)
        if bing_items:
            add_unique(bing_items)

        # 3. DuckDuckGo Instant Answer / Topics
        ddg_items = cls.search_duckduckgo(clean_query)
        if ddg_items:
            add_unique(ddg_items)

        # 4. Wikipedia REST summary for named entities
        if len(combined_results) < 3:
            wiki_item = cls.search_wikipedia_rest(clean_query)
            if wiki_item:
                add_unique([wiki_item])

        final_results = combined_results[:max_results]
        success = len(final_results) > 0
        logger.info(f"[WEB SEARCH] Successfully found {len(final_results)} live results for '{clean_query}'")

        return {
            "query": clean_query,
            "success": success,
            "results": final_results,
            "total": len(final_results)
        }

    @classmethod
    def format_search_context(cls, search_data: Dict[str, Any]) -> str:
        """Format live search results into a high-authority LLM context prompt."""
        temporal = cls.get_temporal_header()
        results = search_data.get("results", [])

        if not results:
            return (
                f"{temporal}\n"
                "INSTRUCTION: Answer using current temporal facts for today's date and year.\n"
            )

        lines = [
            temporal,
            "[LIVE REAL-TIME WEB DATA & SEARCH RESULTS]",
            f"Query: {search_data.get('query', '')}",
            "The following live information was just retrieved from the web:"
        ]

        for i, item in enumerate(results, 1):
            title = item.get("title", "").strip()
            snippet = item.get("snippet", "").replace("\n", " ").strip()
            url = item.get("url", "").strip()
            lines.append(f"{i}. {title}")
            if snippet:
                lines.append(f"   Details: {snippet}")
            if url:
                lines.append(f"   Source: {url}")

        lines.extend([
            "\nCRITICAL INSTRUCTIONS FOR AI RESPONSE:",
            "1. You MUST use the live real-time web results and current temporal context above to answer.",
            "2. NEVER state that your knowledge cutoff prevents you from answering when live results are provided.",
            "3. Answer directly, clearly, and concisely, citing the relevant news headlines, events, or facts retrieved above."
        ])

        return "\n".join(lines)
