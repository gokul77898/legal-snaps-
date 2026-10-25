import re
import urllib.parse
import logging
from typing import List, Tuple, Optional
import httpx
from bs4 import BeautifulSoup
from app.config import settings
from app.schemas import SourceCandidate

logger = logging.getLogger(__name__)

PRIMARY_LEGAL_DOMAINS = [
    "supremecourt.gov", "sci.gov.in", "curia.europa.eu", "supremecourt.uk",
    "oyez.org", "justia.com", "law.cornell.edu", "casemine.com",
    "indiankanoon.org", "bailii.org", "austlii.edu.au", "canlii.org",
    "supremecourtofindia.nic.in", "judic.nic.in", "courtlistener.com"
]

REPUTABLE_LEGAL_JOURNALISM = [
    "livelaw.in", "barandbench.com", "scconline.com", "reuters.com",
    "bloomberglaw.com", "law360.com", "jurist.org", "lawfaremedia.org",
    "scotusblog.com", "theleaflet.in"
]

EXCLUDED_DOMAINS = [
    "facebook.com", "twitter.com", "x.com", "instagram.com", "tiktok.com",
    "pinterest.com", "reddit.com", "youtube.com"
]

def calculate_credibility(url: str, title: str) -> Tuple[float, bool]:
    domain = ""
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
    except Exception:
        domain = ""

    # Primary official court / legal database
    for p_dom in PRIMARY_LEGAL_DOMAINS:
        if p_dom in domain:
            return 0.95, True
    
    # Official government domains
    if domain.endswith(".gov") or ".gov." in domain or domain.endswith(".nic.in"):
        return 0.92, True

    # University / Law school domains
    if domain.endswith(".edu") or ".edu." in domain or ".ac.uk" in domain:
        return 0.85, True

    # Reputable legal news & reporting
    for r_dom in REPUTABLE_LEGAL_JOURNALISM:
        if r_dom in domain:
            return 0.82, False

    # Legal keywords in title or domain
    legal_keywords = ["judgment", "court", "ruling", "v.", "versus", "case", "statute", "order", "bench"]
    if any(k in title.lower() or k in domain for k in legal_keywords):
        return 0.70, False

    return 0.50, False

async def search_duckduckgo(query: str, limit: int = 8) -> List[SourceCandidate]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    encoded_query = urllib.parse.quote_plus(f"{query} legal court judgment ruling")
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    candidates: List[SourceCandidate] = []
    
    async with httpx.AsyncClient(timeout=settings.api_timeout_seconds, follow_redirects=True) as client:
        try:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": f"{query} legal case judgment"},
                headers=headers
            )
            if resp.status_code != 200:
                logger.warning("DuckDuckGo returned status %d, falling back to GET", resp.status_code)
                resp = await client.get(url, headers=headers)
                
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                results = soup.select(".result")
                for r in results:
                    title_elem = r.select_one(".result__title .result__a")
                    snippet_elem = r.select_one(".result__snippet")
                    url_elem = r.select_one(".result__url")
                    
                    if not title_elem:
                        continue
                    
                    raw_url = title_elem.get("href", "")
                    # Extract target URL from DuckDuckGo redirect wrapper if needed
                    actual_url = raw_url
                    if "uddg=" in raw_url:
                        match = re.search(r"uddg=([^&]+)", raw_url)
                        if match:
                            actual_url = urllib.parse.unquote(match.group(1))
                    
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    if not actual_url.startswith("http"):
                        continue
                    
                    # Filter excluded domains
                    if any(ex in actual_url.lower() for ex in EXCLUDED_DOMAINS):
                        continue
                        
                    credibility, is_primary = calculate_credibility(actual_url, title)
                    domain = urllib.parse.urlparse(actual_url).netloc
                    
                    candidates.append(SourceCandidate(
                        title=title,
                        url=actual_url,
                        snippet=snippet,
                        publisher=domain,
                        credibility_score=credibility,
                        is_primary_source=is_primary
                    ))
                    if len(candidates) >= limit:
                        break
        except Exception as e:
            logger.error("DuckDuckGo search error: %s", e)
            
    return candidates

async def search_tavily(query: str, limit: int = 6) -> List[SourceCandidate]:
    if not settings.search_api_key:
        return []
    candidates = []
    try:
        async with httpx.AsyncClient(timeout=settings.api_timeout_seconds) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.search_api_key,
                    "query": f"{query} legal court judgment holding case law",
                    "search_depth": "advanced",
                    "max_results": limit
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                for r in data.get("results", []):
                    u = r.get("url", "")
                    t = r.get("title", "")
                    s = r.get("content", "")
                    credibility, is_primary = calculate_credibility(u, t)
                    domain = urllib.parse.urlparse(u).netloc
                    candidates.append(SourceCandidate(
                        title=t,
                        url=u,
                        snippet=s,
                        publisher=domain,
                        credibility_score=credibility,
                        is_primary_source=is_primary
                    ))
    except Exception as e:
        logger.error("Tavily search error: %s", e)
    return candidates

async def search_indian_kanoon(query: str, limit: int = 8) -> List[SourceCandidate]:
    """
    Search IndianKanoon's public search page. No API key is required, and results are
    primary court documents, which makes this the reliable fallback when the general
    web-search endpoint is rate-limiting (DuckDuckGo answers 202 to challenged IPs).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    candidates: List[SourceCandidate] = []
    try:
        async with httpx.AsyncClient(timeout=settings.api_timeout_seconds, follow_redirects=True) as client:
            resp = await client.get(
                "https://indiankanoon.org/search/",
                params={"formInput": query},
                headers=headers,
            )
        if resp.status_code != 200:
            logger.warning("IndianKanoon search returned HTTP %d", resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for article in soup.select("article.result"):
            title_el = article.select_one(".result_title a")
            if not title_el:
                continue
            title = title_el.get_text(" ", strip=True)
            href = title_el.get("href", "")

            doc_id_match = re.search(r"/(?:doc|docfragment)/(\d+)/", href)
            doc_link = article.find("a", href=re.compile(r"^/doc/\d+/$"))
            if doc_link:
                url = urllib.parse.urljoin("https://indiankanoon.org", doc_link["href"])
            elif doc_id_match:
                url = f"https://indiankanoon.org/doc/{doc_id_match.group(1)}/"
            else:
                continue

            snippet_el = article.select_one(".headline")
            court_el = article.select_one(".docsource")
            snippet = " ".join(snippet_el.get_text(" ", strip=True).split()) if snippet_el else ""
            court = court_el.get_text(" ", strip=True) if court_el else "IndianKanoon"
            date_match = re.search(r"\bon\s+(\d{1,2}\s+\w+,\s+\d{4})", title)

            candidates.append(SourceCandidate(
                title=title,
                url=url,
                snippet=snippet,
                publisher=court,
                publication_date=date_match.group(1) if date_match else None,
                credibility_score=0.95,
                is_primary_source=True,
            ))
            if len(candidates) >= limit:
                break
    except Exception as e:
        logger.error("IndianKanoon search error: %s", e)
    return candidates


# Words that appear in almost every Indian legal title and therefore carry no
# discriminating power when deciding whether a candidate is the requested matter.
RELEVANCE_STOPWORDS = {
    "vs", "versus", "and", "ors", "the", "for", "with", "from", "under", "that", "this",
    "india", "indian", "union", "state", "states", "court", "supreme", "high", "bench",
    "judgment", "judgement", "case", "law", "legal", "article", "right", "rights", "writ",
    "petition", "appeal", "civil", "criminal", "original", "jurisdiction", "order",
    "dated", "decided", "reported", "rule", "rules", "act", "section",
}


def distinctive_tokens(text: str) -> set:
    tokens = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z\.]+", text.lower()):
        token = raw.strip(".")
        if len(token) > 3 and token not in RELEVANCE_STOPWORDS:
            tokens.add(token)
    return tokens


def build_query_variants(query: str) -> List[str]:
    """
    Search formulations to try in order.

    Full-text search engines rank judgments that merely *cite* a landmark case above the
    landmark itself, so a tight caption query ("Puttaswamy Union of India 2017") is needed
    alongside the user's natural-language request.
    """
    variants = [query.strip()]
    separator = re.search(r"\s+(?:v\.?|vs\.?|versus)\s+", query, re.IGNORECASE)
    if separator:
        left = query[:separator.start()].strip()
        right = query[separator.end():].strip()
        year = re.search(r"\b(?:19|20)\d{2}\b", right)
        right = right[:year.end()] if year else " ".join(right.split()[:6])
        variants.append(f"{left} vs {right}")

    return list(dict.fromkeys(v for v in variants if v))


def is_case_query(query: str) -> bool:
    return bool(re.search(r"\bv\.?\s|\bvs\.?\s|\bversus\b", query, re.IGNORECASE))


def has_title_match(query: str, candidate: SourceCandidate) -> bool:
    return bool(distinctive_tokens(query) & distinctive_tokens(candidate.title or ""))


def relevance_score(query: str, candidate: SourceCandidate) -> float:
    """
    How strongly this candidate looks like the matter the user asked for.

    Title matches dominate; snippet matches are weak evidence because any judgment citing
    the requested case mentions it. This prevents a case that merely *cites* Puttaswamy
    from being selected over Puttaswamy itself.
    """
    wanted = distinctive_tokens(query)
    if not wanted:
        return 0.0
    title_tokens = distinctive_tokens(candidate.title or "")
    snippet_tokens = distinctive_tokens(candidate.snippet or "")

    title_hits = len(wanted & title_tokens)
    snippet_hits = len(wanted & snippet_tokens)
    score = (title_hits / len(wanted)) + 0.3 * (snippet_hits / len(wanted))
    return round(min(score, 1.0), 3)


async def discover_sources(query: str) -> Tuple[Optional[SourceCandidate], List[SourceCandidate]]:
    """
    Search for article candidates, rank by relevance to the requested matter and by
    source credibility, and select the best source using explicit legal source rules.

    Providers are tried in order and every failure is logged with its own reason so a
    blocked or unconfigured provider cannot masquerade as "no results exist".
    """
    candidates: List[SourceCandidate] = []
    variants = build_query_variants(query)

    if settings.search_provider == "tavily" and settings.search_api_key:
        candidates = await search_tavily(query)

    if not candidates:
        candidates = await search_duckduckgo(query)
        if not candidates:
            logger.warning("DuckDuckGo returned no usable results (HTTP 202 indicates rate limiting).")

    if not candidates:
        logger.info("Falling back to IndianKanoon search for legal primary sources.")
        for variant in variants[:3]:
            found = await search_indian_kanoon(variant)
            candidates.extend(found)
            if any(has_title_match(variant, c) for c in found):
                logger.info("IndianKanoon matched the requested matter with variant: %s", variant)
                break

    if not candidates:
        logger.warning("No search candidates found for query: %s", query)
        return None, []

    # Deduplicate candidates by URL domain/path
    seen_urls = set()
    unique_candidates = []
    for c in candidates:
        norm_url = c.url.split("?")[0].rstrip("/")
        if norm_url not in seen_urls:
            seen_urls.add(norm_url)
            unique_candidates.append(c)

    for c in unique_candidates:
        c.relevance_score = max(relevance_score(v, c) for v in variants)

    # A candidate must share at least one distinctive term with the request. Ranking by
    # credibility alone would happily return whichever landmark case happens to cite the
    # one the user asked for. For case-caption queries the match must be in the title,
    # because citing cases mention the target in their body text.
    if is_case_query(query):
        relevant = [
            c for c in unique_candidates
            if c.relevance_score > 0 and any(has_title_match(v, c) for v in variants)
        ]
    else:
        relevant = [c for c in unique_candidates if c.relevance_score > 0]

    if not relevant:
        logger.warning(
            "None of the %d search candidates matched the requested matter '%s'",
            len(unique_candidates), query
        )
        return None, []

    relevant.sort(
        key=lambda c: (c.relevance_score, c.is_primary_source, c.credibility_score),
        reverse=True,
    )
    logger.info(
        "Selected source (relevance %.2f): %s -> %s",
        relevant[0].relevance_score, relevant[0].title[:80], relevant[0].url
    )
    return relevant[0], relevant
