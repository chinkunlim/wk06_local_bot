"""
多引擎網頁搜尋模組 (ddgs 套件)
免 API Key，自動在 Bing、Brave、DuckDuckGo、Google、Mojeek 等引擎間切換，
單一引擎被限流時仍可取得結果；作為 DuckDuckGo HTML 的備援
"""
import asyncio
import logging

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from config.settings import settings
from search.duckduckgo import extract_search_keywords

logger = logging.getLogger(__name__)


def _search_blocking(keywords: str, max_results: int) -> list[dict]:
    raw = DDGS(timeout=settings.SEARCH_TIMEOUT).text(
        keywords,
        region='tw-tzh',
        safesearch='off',
        max_results=max_results,
        backend='auto',
    )
    results = []
    for r in raw:
        title = (r.get('title') or '').strip()
        url = (r.get('href') or '').strip()
        snippet = (r.get('body') or '').strip()
        if len(snippet) > 300:
            snippet = snippet[:300] + '...'
        if title and url:
            results.append({'title': title, 'url': url, 'snippet': snippet})
    return results[:max_results]


async def search_ddgs(query: str, max_results: int = 4) -> list[dict]:
    """
    多引擎搜尋
    回傳格式: [{title, url, snippet}, ...]
    """
    keywords = extract_search_keywords(query) or query
    logger.info(f'🔍 [ddgs] 搜尋關鍵字: "{keywords}"')
    try:
        # ddgs 為同步 API，放到執行緒避免阻塞 event loop
        results = await asyncio.to_thread(_search_blocking, keywords, max_results)
    except DDGSException as e:
        logger.warning(f'⚠️ [ddgs] 無結果或所有引擎失敗: {e}')
        return []
    except Exception as e:
        logger.error(f'❌ [ddgs] 搜尋失敗: {e}')
        return []
    logger.info(f'✅ [ddgs] 取得 {len(results)} 筆結果')
    return results


def format_search_results(results: list[dict]) -> str:
    """格式化搜尋結果給 LLM (與 DuckDuckGo 相同格式)"""
    from search.duckduckgo import format_search_results as _fmt
    return _fmt(results)
