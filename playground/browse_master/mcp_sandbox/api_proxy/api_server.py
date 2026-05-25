import asyncio
import time
from fastapi import FastAPI, HTTPException, Request
import json
import uvicorn
from typing import Dict, List
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import aiohttp
from fastapi.responses import JSONResponse
from models import (
    SearchRequest, ReadPdfInfo, FetchWebContent, 
    WebParseRequest, BatchSearchRequest, GenerateKeywordsRequest, CheckConditionRequest
)
from api_utils.web_search_api import serper_google_search
from api_utils.pdf_read_api import read_pdf_from_url
from api_utils.fetch_web_page_api import fetch_web_content
import requests
import os
import re


app = FastAPI()

# Initialize in-memory rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# --- LLM helper -----------------------------------------------------------

# Try to load optional OpenAI client for web_parse LLM extraction
try:
    import openai
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


def _load_web_agent_config():
    """Load web_agent.json config if present."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "configs", "web_agent.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _get_llm_config():
    """Return (api_key, base_url, model) from env or config files."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("WEB_PARSE_LLM_MODEL", "gpt-4o")

    # Try to read from llm_call.json for model-specific overrides
    current_dir = os.path.dirname(os.path.abspath(__file__))
    llm_call_path = os.path.join(current_dir, "configs", "llm_call.json")
    if os.path.exists(llm_call_path):
        try:
            with open(llm_call_path, "r", encoding="utf-8") as f:
                llm_cfg = json.load(f)
            if model in llm_cfg:
                cfg = llm_cfg[model]
                if cfg.get("url"):
                    base_url = cfg["url"]
                if cfg.get("authorization") and cfg["authorization"] != "EMPTY":
                    api_key = cfg["authorization"]
        except Exception:
            pass

    return api_key, base_url, model


def _call_llm_sync(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> str:
    """Synchronous LLM call for extraction tasks. Returns empty string on failure."""
    if not _OPENAI_AVAILABLE:
        return ""

    api_key, base_url, model = _get_llm_config()
    if not api_key:
        return ""

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    try:
        client = openai.OpenAI(**client_kwargs)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""
    except Exception:
        return ""


# --- Existing endpoints (unchanged) ---------------------------------------

@app.post("/search")
@limiter.limit("200/second")
async def search(request: Request, search_request: SearchRequest):
    try:
        result = await serper_google_search(
            search_request.query, 
            search_request.serper_api_key, 
            search_request.top_k, 
            search_request.region, 
            search_request.lang, 
            depth=search_request.depth
        )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    


@app.post("/read_pdf")
@limiter.limit("200/second")
async def read_pdf(request: Request, read_pdf_request: ReadPdfInfo):
    try:
        result = await read_pdf_from_url(read_pdf_request.url)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@app.post("/fetch_web")
@limiter.limit("200/second")
async def fetch_web(request: Request, fetch_web_request: FetchWebContent):
    try:
        result = await fetch_web_content(fetch_web_request.url)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


# --- Enhanced web_parse ---------------------------------------------------

def _extract_plain_text(html: str, max_len: int = 12000) -> str:
    """Strip HTML tags/scripts and return clean text."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        text = text[:max_len] + "\n...[content truncated]"
    return text


def _llm_extract_web_content(link: str, user_prompt: str, raw_text: str) -> dict:
    """Use LLM to extract structured info from raw web text.
    
    Falls back to plain text if LLM is unavailable or fails.
    """
    system_prompt = (
        "You are a helpful research assistant. Extract the information most "
        "relevant to the user's question from the provided web page text. "
        "Be concise, factual, and do not fabricate information. "
        "Return your answer in plain text (not JSON)."
    )
    truncated_text = raw_text[:6000] if len(raw_text) > 6000 else raw_text
    full_prompt = (
        f"User's question: {user_prompt}\n\n"
        f"Web page text:\n{truncated_text}\n\n"
        f"Please provide a structured extraction of the relevant information."
    )

    llm_response = _call_llm_sync(system_prompt, full_prompt, max_tokens=2000)

    if llm_response:
        return {
            "content": llm_response,
            "urls": [{"url": link, "description": "Source page"}],
            "score": 0.85,
        }
    else:
        # LLM unavailable — return clean plain text (much better than raw HTML)
        return {
            "content": f"Extracted web content:\n{raw_text}\n\n"
                       f"(Note: LLM extraction unavailable. Above is the cleaned text from the page. "
                       f"User's original request: {user_prompt})",
            "urls": [{"url": link, "description": "Source page"}],
            "score": 0.7,
        }


@app.post("/web_parse")
@limiter.limit("200/second")
async def web_parse(request: Request, parse_request: WebParseRequest):
    try:
        is_ok, content = await fetch_web_content(parse_request.link)
        if not is_ok:
            return {"content": "Failed to fetch web page", "urls": [], "score": 0.0}

        raw_text = _extract_plain_text(content)
        result = _llm_extract_web_content(
            parse_request.link, parse_request.user_prompt, raw_text
        )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


# --- Enhanced batch_search_and_filter -------------------------------------

async def _generate_search_variations(keyword: str) -> List[str]:
    """Generate keyword variations for broader coverage."""
    variations = [keyword]
    # Add common academic modifiers
    modifiers = [
        f"{keyword} review",
        f"{keyword} mechanism",
        f"{keyword} pathway",
        f"{keyword} recent advances",
    ]
    # Use LLM if available for smarter variations
    if _OPENAI_AVAILABLE:
        system = "You are a research assistant. Given a seed keyword, generate 3-5 diverse academic search queries (in English) that would help find relevant papers. Return one per line, no numbering, no extra text."
        llm_out = _call_llm_sync(system, f"Seed keyword: {keyword}", max_tokens=300)
        if llm_out:
            for line in llm_out.strip().split("\n"):
                line = line.strip().strip('"').strip("'")
                if line and line not in variations:
                    variations.append(line)
    variations.extend(modifiers)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for v in variations:
        v_lower = v.lower()
        if v_lower not in seen:
            seen.add(v_lower)
            unique.append(v)
    return unique[:8]  # cap at 8 queries


@app.post("/batch_search_and_filter")
@limiter.limit("200/second")
async def batch_search_and_filter(request: Request, search_request: BatchSearchRequest):
    try:
        # Load config
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "configs", "web_agent.json")
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

        serper_key = config.get("serper_api_key", "")
        region = config.get("search_region", "us")
        lang = config.get("search_lang", "en")

        # Generate search variations
        queries = await _generate_search_variations(search_request.keyword)

        # Execute searches concurrently (limit to first 5 to respect rate limits)
        search_tasks = []
        for q in queries[:5]:
            search_tasks.append(
                serper_google_search(q, serper_key, 10, region, lang, depth=0)
            )

        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Merge and deduplicate
        seen_links = set()
        yes_results = []
        unknown_results = []

        for res in results:
            if isinstance(res, Exception):
                continue
            organic = res.get("organic", []) if isinstance(res, dict) else []
            for item in organic:
                link = item.get("link", "")
                if link and link not in seen_links:
                    seen_links.add(link)
                    yes_results.append(item)

        return {
            "yes": yes_results,
            "unknown": unknown_results,
            "queries_used": queries[:5],
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


# --- Enhanced generate_keywords -------------------------------------------

@app.post("/generate_keywords")
@limiter.limit("200/second")
async def generate_keywords(request: Request, kw_request: GenerateKeywordsRequest):
    try:
        seed = kw_request.seed_keyword.strip()
        if not seed:
            return {"keywords": []}

        # Try LLM for high-quality keyword generation
        if _OPENAI_AVAILABLE:
            system = (
                "You are a research librarian. Given a seed keyword, generate 6-10 "
                "diverse, specific search keywords/phrases (in English) that would help "
                "find academic papers on this topic. Include variations with different "
                "angles (review, mechanism, clinical, signaling, etc.). Return one per line, no numbering."
            )
            llm_out = _call_llm_sync(system, f"Seed keyword: {seed}", max_tokens=400)
            if llm_out:
                keywords = []
                for line in llm_out.strip().split("\n"):
                    line = line.strip().strip('"').strip("'")
                    if line and line.lower() not in [k.lower() for k in keywords]:
                        keywords.append(line)
                if len(keywords) >= 4:
                    return {"keywords": keywords}

        # Fallback: heuristic expansion
        keywords = [
            seed,
            f"{seed} review",
            f"{seed} mechanism",
            f"{seed} signaling pathway",
            f"{seed} recent advances",
            f"{seed} clinical implications",
        ]
        return {"keywords": keywords}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


# --- Enhanced check_condition ---------------------------------------------

@app.post("/check_condition")
@limiter.limit("200/second")
async def check_condition(request: Request, check_request: CheckConditionRequest):
    try:
        content = check_request.content.strip()
        condition = check_request.condition.strip()
        if not content or not condition:
            return {"is_relevant": "unknown"}

        # Try LLM for accurate relevance assessment
        if _OPENAI_AVAILABLE and len(content) > 50:
            system = (
                "You are a relevance assessor. Given a piece of content and a condition/query, "
                "determine if the content is relevant. Answer with exactly one word: 'yes', 'no', or 'unknown'."
            )
            user_msg = f"Condition: {condition}\n\nContent:\n{content[:4000]}\n\nIs this content relevant to the condition?"
            llm_out = _call_llm_sync(system, user_msg, max_tokens=10)
            if llm_out:
                answer = llm_out.strip().lower()
                if "yes" in answer:
                    return {"is_relevant": "yes"}
                elif "no" in answer:
                    return {"is_relevant": "no"}
                return {"is_relevant": "unknown"}

        # Fallback: improved keyword matching
        content_lower = content.lower()
        condition_lower = condition.lower()

        # Extract meaningful words (length > 3, not stopwords)
        stopwords = {"the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her", "was", "one", "our", "out", "day", "get", "has", "him", "his", "how", "its", "may", "new", "now", "old", "see", "two", "who", "boy", "did", "she", "use", "her", "way", "many", "oil", "sit", "set", "run", "eat", "far", "sea", "eye", "ago", "off", "too", "any", "say", "man", "try", "ask", "end", "why", "let", "put", "say", "she", "try", "way", "own", "say", "too", "old", "tell", "very", "when", "much", "would", "there", "their", "what", "said", "have", "each", "which", "will", "about", "could", "other", "after", "first", "never", "these", "think", "where", "being", "every", "great", "might", "shall", "still", "those", "under", "while", "this", "that", "with", "from", "they", "been", "were", "said", "time", "than", "them", "into", "just", "like", "over", "also", "back", "only", "know", "take", "year", "good", "some", "come", "make", "well", "work", "life", "even", "more", "want", "here", "look", "down", "most", "long", "last", "find", "give", "does", "made", "part", "such", "keep", "call", "came", "need", "feel", "seem", "turn", "hand", "high", "sure", "upon", "head", "help", "home", "side", "move", "both", "five", "once", "same", "must", "name", "left", "each", "done", "open", "case", "show", "live", "play", "went", "told", "seen", "hear", "talk", "soon", "read", "stop", "face", "fact", "land", "line", "kind", "next", "word", "came", "went", "told", "seen", "hear", "talk", "soon", "read", "stop", "face", "fact", "land", "line", "kind", "next", "word"}

        cond_words = [
            w for w in re.findall(r'\b[a-z]{4,}\b', condition_lower)
            if w not in stopwords
        ]
        if not cond_words:
            return {"is_relevant": "unknown"}

        match_count = sum(1 for w in cond_words if w in content_lower)
        ratio = match_count / len(cond_words)

        if ratio >= 0.5:
            return {"is_relevant": "yes"}
        elif ratio >= 0.25:
            return {"is_relevant": "unknown"}
        else:
            return {"is_relevant": "no"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


# --- Error handlers -------------------------------------------------------

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Limit is 200 requests per second."},
        headers={"Retry-After": "1"}
    )


# --- Main -----------------------------------------------------------------

if __name__ == "__main__":
    PORT = os.getenv('PORT', 1234)

    uvicorn.run(
        "api_server:app", 
        host="0.0.0.0", 
        port=int(PORT),
        lifespan="on",
        workers=1
    )
