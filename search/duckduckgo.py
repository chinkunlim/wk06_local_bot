"""
DuckDuckGo HTML 搜尋模組
免費、無需 API Key、支援中文搜尋
"""
import logging
import re
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)

# DuckDuckGo 搜尋 URL
DDG_HTML_URL = 'https://html.duckduckgo.com/html/'
DDG_LITE_URL = 'https://duckduckgo.com/html/'

# 被機器人驗證擋下後，暫停使用 DuckDuckGo 的秒數 (避免持續請求延長封鎖)
BLOCK_COOLDOWN_SECONDS = 600
_blocked_until = 0.0


def is_blocked() -> bool:
    """是否處於封鎖冷卻期"""
    return time.monotonic() < _blocked_until


def mark_blocked(seconds: float = BLOCK_COOLDOWN_SECONDS):
    global _blocked_until
    _blocked_until = time.monotonic() + seconds


def is_challenge_page(status_code: int, text: str) -> bool:
    """
    判斷是否為機器人驗證頁
    DuckDuckGo 限流時回傳 HTTP 202 + anomaly 頁面，而非搜尋結果
    """
    if 'result__body' in text:
        return False
    return status_code == 202 or 'anomaly' in text.lower()


# 模擬瀏覽器的 User-Agent
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate',  # 移除 br (Brotli) 避免解壓失敗
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


def extract_search_keywords(query: str) -> str:
    """
    從使用者提問中提取核心搜尋關鍵字
    移除常見提問詞彙、標點符號
    """
    if not query:
        return ''

    # 移除指令前綴
    query = re.sub(r'^(/search|/news)\s*', '', query, flags=re.IGNORECASE).strip()

    # 將標點符號替換為空格 (保留 C++、C#、llama3.1 這類詞內符號)
    query = re.sub(r'[。，！？!?,\n/；;:：、～~—_()（）「」『』《》@=*&^%$]+', ' ', query)
    query = re.sub(r'(?<!\w)\.|\.(?!\w)', ' ', query)
    query = re.sub(r'(?<![\w+])\++', ' ', query)
    query = re.sub(r'(?<!\w)#(?!\w)', ' ', query)

    # 移除常見提問贅詞
    stop_phrases = [
        '請問', '請告訴我', '我想知道', '你知道', '有沒有', '可以跟我說',
        '幫我查', '幫我搜尋', '搜尋', '查詢', '一下', '什麼是', '是誰',
        '是多少', '多少個', '多少面', '數量', '結果', '如何', '怎麼樣',
        '評價是什麼', '評價如何', '推薦嗎', '好不好', '可以選嗎',
        '開什麼課', '有哪些課', '相關的', '有關的', '表現如何',
        '今天的', '今天', '今日', '明天的', '明天', '昨天的', '昨天',
        '今年的', '今年', '最近的', '最近', '最新的', '最新', '目前的', '目前', '現在',
        '新聞', '即時', '即時新聞',
    ]

    for phrase in stop_phrases:
        query = re.sub(re.escape(phrase), ' ', query, flags=re.IGNORECASE)

    # 清理助詞：只移除獨立的助詞與句尾疑問詞，不從詞內剝字 (避免「和平」→「平」)
    particles = ['的', '了', '和', '與', '在', '之', '個', '嗎', '呢', '啊', '吧', '請']
    words = [w.rstrip('嗎呢') for w in query.split()]
    words = [w for w in words if w and w not in particles]

    # 去重並取前 5 個關鍵字
    unique_words = []
    seen = set()
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower())
            unique_words.append(w)

    return ' '.join(unique_words[:5])


async def search_duckduckgo(query: str, max_results: int = 4) -> list[dict]:
    """
    使用 DuckDuckGo HTML 版搜尋
    回傳格式: [{title, url, snippet}, ...]
    """
    keywords = extract_search_keywords(query)
    if not keywords:
        keywords = query

    if is_blocked():
        remaining = int(_blocked_until - time.monotonic())
        logger.info(f'⏸️ [DuckDuckGo] 封鎖冷卻中 (剩 {remaining} 秒)，略過')
        return []

    logger.info(f'🔍 [DuckDuckGo] 搜尋關鍵字: "{keywords}"')

    async with httpx.AsyncClient(
        timeout=settings.SEARCH_TIMEOUT,
        headers=HEADERS,
        follow_redirects=True
    ) as client:
        try:
            # DuckDuckGo HTML 版：直接 POST 取得結果
            response = await client.post(
                DDG_HTML_URL,
                data={'q': keywords, 'kl': 'tw-tw'},
            )

            response.raise_for_status()

            if is_challenge_page(response.status_code, response.text):
                mark_blocked()
                logger.warning(
                    f'🚫 [DuckDuckGo] 被機器人驗證擋下 (HTTP {response.status_code})，'
                    f'{BLOCK_COOLDOWN_SECONDS // 60} 分鐘內暫停使用'
                )
                return []

            soup = BeautifulSoup(response.text, 'html.parser')

            results = []

            # 解析結果 - DuckDuckGo HTML 版的結構
            # 只使用 .result__body 避免重複選擇
            for result_div in soup.select('.result__body'):
                # 標題與連結
                title_elem = result_div.select_one('.result__title a, .result__url a, h2 a, .title a')
                snippet_elem = result_div.select_one('.result__snippet, .snippet, .result__excerpt')

                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                url = title_elem.get('href', '')

                # 處理相對連結
                if url and not url.startswith('http'):
                    url = urljoin('https://duckduckgo.com', url)

                snippet = ''
                if snippet_elem:
                    snippet = snippet_elem.get_text(strip=True)
                    if len(snippet) > 300:
                        snippet = snippet[:300] + '...'

                if title and url:
                    results.append({
                        'title': title,
                        'url': url,
                        'snippet': snippet
                    })

                if len(results) >= max_results:
                    break

            logger.info(f'✅ [DuckDuckGo] 取得 {len(results)} 筆結果')
            return results

        except httpx.TimeoutException:
            logger.error(f'❌ [DuckDuckGo] 搜尋逾時 ({settings.SEARCH_TIMEOUT}秒)')
            return []
        except Exception as e:
            logger.error(f'❌ [DuckDuckGo] 搜尋失敗: {e}')
            return []


def format_search_results(results: list[dict]) -> str:
    """將搜尋結果格式化為給 LLM 參考的文字"""
    if not results:
        return '（無搜尋結果）'

    lines = ['【即時搜尋結果】']
    for i, r in enumerate(results, 1):
        lines.append(f'\n【結果 {i}】')
        lines.append(f'標題：{r["title"]}')
        lines.append(f'網址：{r["url"]}')
        if r['snippet']:
            lines.append(f'摘要：{r["snippet"]}')

    return '\n'.join(lines)


# 同步版本 (供非 async 環境使用)
def search_duckduckgo_sync(query: str, max_results: int = 4) -> list[dict]:
    """同步版本的搜尋"""
    from search import run_sync
    return run_sync(search_duckduckgo(query, max_results))
