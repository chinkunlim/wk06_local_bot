"""
搜尋引擎工廠 - 統一介面
"""
from typing import List, Dict, Callable, Awaitable
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

# 搜尋函數類型
SearchFunc = Callable[[str, int], Awaitable[List[Dict]]]
FormatFunc = Callable[[List[Dict]], str]

# 註冊的搜尋引擎
SEARCH_ENGINES = {
    'duckduckgo': {
        'name': 'DuckDuckGo HTML',
        'search': None,  # 將在導入時動態載入
        'format': None,
    },
    'google_news': {
        'name': 'Google News RSS',
        'search': None,
        'format': None,
    },
}


def _load_engines():
    """延遲載入搜尋模組 (避免循環導入)"""
    if SEARCH_ENGINES['duckduckgo']['search'] is None:
        from search.duckduckgo import search_duckduckgo, format_search_results as fmt_ddg
        SEARCH_ENGINES['duckduckgo']['search'] = search_duckduckgo
        SEARCH_ENGINES['duckduckgo']['format'] = fmt_ddg
    
    if SEARCH_ENGINES['google_news']['search'] is None:
        from search.google_news import search_google_news, format_search_results as fmt_gn
        SEARCH_ENGINES['google_news']['search'] = search_google_news
        SEARCH_ENGINES['google_news']['format'] = fmt_gn


def get_search_engine(engine_name: str = None) -> dict:
    """取得搜尋引擎"""
    _load_engines()
    name = engine_name or settings.SEARCH_ENGINE
    if name not in SEARCH_ENGINES:
        logger.warning(f'未知搜尋引擎: {name}, 使用預設: {settings.SEARCH_ENGINE}')
        name = settings.SEARCH_ENGINE
    return SEARCH_ENGINES[name]


async def search(query: str, max_results: int = None, engine: str = None) -> List[Dict]:
    """統一搜尋介面"""
    eng = get_search_engine(engine)
    max_r = max_results or settings.SEARCH_MAX_RESULTS
    logger.info(f'🔍 使用搜尋引擎: {eng["name"]}')
    return await eng['search'](query, max_r)


def format_results(results: List[Dict], engine: str = None) -> str:
    """統一格式化介面"""
    eng = get_search_engine(engine)
    return eng['format'](results)


# 同步版本
def search_sync(query: str, max_results: int = None, engine: str = None) -> List[Dict]:
    import asyncio
    import sys
    if sys.version_info >= (3, 12):
        # Python 3.12+ 使用 asyncio.run
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(search(query, max_results, engine))
        # 已經在 loop 中，建立新 task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, search(query, max_results, engine))
            return future.result()
    else:
        # Python 3.11 及以下
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, search(query, max_results, engine))
                    return future.result()
        except RuntimeError:
            pass
        return asyncio.run(search(query, max_results, engine))