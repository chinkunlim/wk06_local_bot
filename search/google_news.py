"""
Google News RSS 搜尋模組
穩定、免費、支援繁體中文、適合新聞類即時資訊
"""
import html
import logging
import re

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

# Google News RSS 搜尋 URL
GOOGLE_NEWS_RSS_URL = 'https://news.google.com/rss/search'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; LocalBot-NewsFetcher/1.0)',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
}


def extract_search_keywords(query: str) -> str:
    """提取搜尋關鍵字 (共用邏輯)"""
    from search.duckduckgo import extract_search_keywords as _extract
    return _extract(query)


def filter_relevant_articles(articles: list[dict], keyword: str) -> list[dict]:
    """
    智慧相關性過濾：支援中文子詞素與 2-gram 柔性比對
    防範複合名詞過度誤殺，同時杜絕無關雜訊
    """
    if not articles:
        return []
    if not keyword:
        return articles

    # 通用停用詞
    stop_words = ['最新', '新聞', '評價', '如何', '什麼', '請問', '查詢', '台灣', '今天', '今年']
    raw_tokens = keyword.split()
    sub_tokens = []

    for raw in raw_tokens:
        raw = raw.strip()
        if not raw or raw.lower() in stop_words:
            continue

        # 去除常見地域前綴
        if len(raw) > 2:
            stripped = re.sub(r'^(台灣|全台|中華)', '', raw)
            if len(stripped) >= 2 and stripped not in stop_words and stripped not in sub_tokens:
                sub_tokens.append(stripped)

        if len(raw) >= 2 and raw not in stop_words and raw not in sub_tokens:
            sub_tokens.append(raw)

        # 長度 >= 3 自動提煉 2-gram
        if len(raw) >= 3:
            for j in range(len(raw) - 1):
                bi = raw[j:j+2]
                if bi not in stop_words and len(bi) == 2 and bi not in sub_tokens:
                    sub_tokens.append(bi)

    if not sub_tokens:
        return articles

    relevant = []
    for art in articles:
        content = (art.get('title', '') + ' ' + art.get('description', '')).lower()
        if any(token.lower() in content for token in sub_tokens):
            relevant.append(art)

    logger.info(f'🎯 [GoogleNews] 相關性校驗: 原始 {len(articles)} 則 ➔ 命中 {len(relevant)} 則 (詞素: {sub_tokens})')
    return relevant


async def search_google_news(query: str, max_results: int = 4) -> list[dict]:
    """
    使用 Google News RSS 搜尋
    回傳格式: [{title, url, snippet, pubDate}, ...]
    """
    keyword = extract_search_keywords(query)
    if not keyword:
        keyword = query

    logger.info(f'🔍 [GoogleNews] 搜尋關鍵字: "{keyword}"')

    params = {
        'q': keyword,
        'hl': 'zh-TW',
        'gl': 'TW',
        'ceid': 'TW:zh-Hant',
    }

    async with httpx.AsyncClient(
        timeout=settings.SEARCH_TIMEOUT,
        headers=HEADERS
    ) as client:
        try:
            response = await client.get(GOOGLE_NEWS_RSS_URL, params=params)
            response.raise_for_status()

            xml_text = response.text
            return parse_news_rss(xml_text, max_results, keyword)

        except httpx.TimeoutException:
            logger.error(f'❌ [GoogleNews] 搜尋逾時 ({settings.SEARCH_TIMEOUT}秒)')
            return []
        except Exception as e:
            logger.error(f'❌ [GoogleNews] 搜尋失敗: {e}')
            return []


def parse_news_rss(xml_text: str, max_results: int, keyword: str) -> list[dict]:
    """解析 Google News RSS XML"""
    articles = []

    # 使用正則提取 <item> 區塊
    item_pattern = re.compile(r'<item>([\s\S]*?)</item>', re.IGNORECASE)
    matches = item_pattern.findall(xml_text)

    for item_content in matches[:8]:  # 多抓一些再過濾
        title_match = re.search(r'<title>([\s\S]*?)</title>', item_content, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ''

        link_match = re.search(r'<link>([\s\S]*?)</link>', item_content, re.IGNORECASE)
        link = link_match.group(1).strip() if link_match else ''

        pub_date_match = re.search(r'<pubDate>([\s\S]*?)</pubDate>', item_content, re.IGNORECASE)
        pub_date = pub_date_match.group(1).strip() if pub_date_match else ''

        desc_match = re.search(r'<description>([\s\S]*?)</description>', item_content, re.IGNORECASE)
        description = desc_match.group(1).strip() if desc_match else ''

        # 清理 HTML 標籤與實體
        description = clean_html(description)

        if title:
            if len(description) > 200:
                description = description[:200] + '...'
            articles.append({
                'title': decode_xml_entities(title),
                'url': link,
                'pubDate': pub_date,
                'description': description,
            })

    # 相關性過濾
    relevant = filter_relevant_articles(articles, keyword)

    if not relevant:
        logger.warning(f'⚠️ [GoogleNews] 無相關新聞: "{keyword}"')
        return []

    return relevant[:max_results]


def clean_html(raw: str) -> str:
    """移除 HTML 標籤 (RSS description 為實體編碼的 HTML，需先解碼再移除標籤)"""
    if not raw:
        return ''
    # 先解碼實體 (&lt;a&gt; -> <a>)，才能正確移除標籤
    text = decode_xml_entities(raw)
    # 移除標籤
    text = re.sub(r'<[^>]+>', ' ', text)
    # 正規化空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def decode_xml_entities(text: str) -> str:
    """解碼 XML/HTML 實體 (含 &amp; &lt; &#8217; &nbsp; 等所有具名/數字實體)"""
    if not text:
        return ''
    return html.unescape(text).replace('\xa0', ' ')


def format_search_results(results: list[dict]) -> str:
    """格式化搜尋結果給 LLM"""
    if not results:
        return '（無搜尋結果）'

    lines = ['【即時新聞檢索結果】']
    for i, r in enumerate(results, 1):
        lines.append(f'\n【新聞 {i}】')
        lines.append(f'標題：{r["title"]}')
        lines.append(f'時間：{r.get("pubDate", "未知")}')
        lines.append(f'網址：{r["url"]}')
        if r.get('description'):
            lines.append(f'摘要：{r["description"]}')

    return '\n'.join(lines)


# 同步版本
def search_google_news_sync(query: str, max_results: int = 4) -> list[dict]:
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(search_google_news(query, max_results))
