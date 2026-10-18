"""
網頁內文擷取 - 搜尋後讀取前幾筆結果的網頁，摘錄與問題相關的段落給模型
搜尋摘要通常只有一兩句，讀取內文才能完整回答 (例如老師開設的全部課程)
"""
import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
}

# 無法直接讀取內文的網站 (需 JavaScript 轉址或登入)
SKIP_HOSTS = ('news.google.com', 'duckduckgo.com', 'facebook.com', 'instagram.com',
              'youtube.com', 'x.com', 'twitter.com', 'threads.net')
SKIP_EXTENSIONS = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.jpg', '.png')
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
# 命中行之後一併保留的行數 (例如「開設課程」標題後接課程清單)
CONTEXT_LINES = 3


def is_fetchable(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = parsed.netloc.lower()
    if any(host == h or host.endswith('.' + h) for h in SKIP_HOSTS):
        return False
    return not parsed.path.lower().endswith(SKIP_EXTENSIONS)


def html_to_lines(html: bytes | str) -> list[str]:
    """移除腳本、導覽等雜訊，回傳去重後的文字行"""
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside', 'form', 'svg', 'iframe']):
        tag.decompose()
    lines, seen = [], set()
    for line in soup.get_text('\n').split('\n'):
        line = re.sub(r'\s+', ' ', line).strip()
        if line and line not in seen:
            seen.add(line)
            lines.append(line[:300])
    return lines


def query_keywords(query: str) -> list[str]:
    """問題關鍵字：原詞 + 長詞的 2-gram (中文無空白斷詞，例如「陳文盛老師」也能命中「陳文盛」)"""
    words = [w for w in re.split(r'\s+', query) if len(w) >= 2]
    keywords = set(words)
    for w in words:
        if len(w) >= 3:
            keywords.update(w[i:i + 2] for i in range(len(w) - 1))
    return sorted(keywords, key=len, reverse=True)


def extract_relevant_text(lines: list[str], query: str, max_chars: int) -> str:
    """
    依關鍵字命中程度挑選段落：每個命中行連同其後 CONTEXT_LINES 行為一段，
    命中越多 (越長的關鍵字權重越高) 越優先，最後依原文順序組合
    """
    keywords = query_keywords(query)
    if not keywords:
        return '\n'.join(lines)[:max_chars]

    scored = []
    for i, line in enumerate(lines):
        score = sum(len(k) for k in keywords if k in line)
        if score:
            scored.append((score, i))

    if not scored:
        return '\n'.join(lines)[:max_chars]

    chosen: set[int] = set()
    total = 0
    for _, i in sorted(scored, key=lambda x: (-x[0], x[1])):
        for j in range(i, min(i + 1 + CONTEXT_LINES, len(lines))):
            if j in chosen:
                continue
            if total + len(lines[j]) + 1 > max_chars:
                break
            chosen.add(j)
            total += len(lines[j]) + 1
        if total >= max_chars:
            break

    return '\n'.join(lines[j] for j in sorted(chosen))


async def fetch_page_text(client: httpx.AsyncClient, url: str, query: str, max_chars: int) -> str:
    """下載網頁並摘錄相關內文；失敗回傳空字串"""
    try:
        async with client.stream('GET', url) as resp:
            resp.raise_for_status()
            ctype = resp.headers.get('content-type', '')
            if 'html' not in ctype and 'text/plain' not in ctype:
                return ''
            body = b''
            async for chunk in resp.aiter_bytes():
                body += chunk
                if len(body) > MAX_DOWNLOAD_BYTES:
                    break
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        logger.info(f'📄 讀取網頁失敗 {url[:80]}: {e.__class__.__name__}')
        return ''

    # 交給 BeautifulSoup 依 <meta charset> 判斷編碼 (big5 等舊站)
    lines = html_to_lines(body)
    return extract_relevant_text(lines, query, max_chars)


async def enrich_results(
    results: list[dict],
    query: str,
    pages: int | None = None,
    max_chars: int | None = None,
) -> list[dict]:
    """為前 N 筆可讀取的結果加上 'content' (網頁內文摘錄)，就地修改並回傳"""
    pages = settings.SEARCH_FETCH_PAGES if pages is None else pages
    max_chars = settings.SEARCH_PAGE_CHARS if max_chars is None else max_chars
    targets = [r for r in results if is_fetchable(r.get('url', ''))][:pages]
    if not targets:
        return results

    timeout = httpx.Timeout(min(settings.SEARCH_TIMEOUT, 10))
    async with httpx.AsyncClient(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
        texts = await asyncio.gather(
            *(fetch_page_text(client, r['url'], query, max_chars) for r in targets),
            return_exceptions=True,
        )

    for r, text in zip(targets, texts):
        if isinstance(text, str) and text:
            r['content'] = text
    logger.info(f'📄 已讀取 {sum(1 for r in targets if r.get("content"))}/{len(targets)} 個網頁內文')
    return results
