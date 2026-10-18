#!/usr/bin/env python3
"""
網頁內文擷取與 ddgs 多引擎搜尋測試 (離線)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ddgs.exceptions import DDGSException

from search import duckduckgo, format_results, multi_engine, page_fetch
from search.page_fetch import extract_relevant_text, html_to_lines, is_fetchable, query_keywords

TEACHER_PAGE = """
<html><head><title>陳文盛助理教授</title><script>var x = 1;</script></head>
<body>
<nav><a>首頁</a><a>通識課程查詢</a></nav>
<div>跳到主要內容區</div>
<h2>陳文盛助理教授</h2>
<p>研究室：理工二館C306</p>
<h3>學歷</h3><p>國立東華大學 資訊工程學系 博士</p>
<h3>經歷</h3><p>台灣東部地震中心專案研究員</p>
""" + ''.join(f'<p>無關段落 {i} ' + '填充文字' * 20 + '</p>' for i in range(30)) + """
<h3>開設課程</h3>
<p>初級程式設計-Python，中級程式設計-Python 資訊科技與應用</p>
<h3>個人著作</h3><p>Multiple Object Tracking using YOLO-based Detector</p>
<footer>版權所有</footer>
</body></html>
"""


def test_is_fetchable():
    assert is_fetchable('https://genedu.ndhu.edu.tw/p/412-1076-18517.php?Lang=zh-tw')
    assert not is_fetchable('https://news.google.com/rss/articles/abc')
    assert not is_fetchable('https://www.youtube.com/watch?v=1')
    assert not is_fetchable('https://example.com/file.pdf')
    assert not is_fetchable('javascript:void(0)')


def test_html_to_lines_drops_noise():
    lines = html_to_lines(TEACHER_PAGE)
    text = '\n'.join(lines)
    assert 'var x' not in text  # script
    assert '通識課程查詢' not in text  # nav
    assert '版權所有' not in text  # footer
    assert '開設課程' in text


def test_query_keywords_include_bigrams():
    kws = query_keywords('東華大學 陳文盛老師 課程')
    assert '陳文盛老師' in kws and '陳文' in kws and '課程' in kws


def test_extract_keeps_course_section_within_budget():
    lines = html_to_lines(TEACHER_PAGE)
    # 全文遠超上限，仍要保留「開設課程」標題與其後的課程清單
    assert len('\n'.join(lines)) > 1500
    excerpt = extract_relevant_text(lines, '東華大學 陳文盛 課程', max_chars=400)
    assert len(excerpt) <= 400
    assert '開設課程' in excerpt
    assert '中級程式設計-Python' in excerpt


def test_extract_without_matches_returns_beginning():
    excerpt = extract_relevant_text(['第一行', '第二行'], '完全不相關', max_chars=100)
    assert excerpt.startswith('第一行')


async def test_enrich_results_only_top_fetchable(monkeypatch):
    fetched: list[str] = []

    async def fake_fetch(client, url, query, max_chars):
        fetched.append(url)
        return f'內文 {url}'

    monkeypatch.setattr(page_fetch, 'fetch_page_text', fake_fetch)
    results = [
        {'title': 'G', 'url': 'https://news.google.com/rss/articles/x'},
        {'title': 'A', 'url': 'https://a.com/'},
        {'title': 'B', 'url': 'https://b.com/'},
        {'title': 'C', 'url': 'https://c.com/'},
    ]
    await page_fetch.enrich_results(results, 'q', pages=2, max_chars=100)
    assert fetched == ['https://a.com/', 'https://b.com/']
    assert 'content' not in results[0] and 'content' not in results[3]
    assert results[1]['content'] == '內文 https://a.com/'


def test_format_includes_content():
    text = duckduckgo.format_search_results(
        [{'title': 'T', 'url': 'https://t.com', 'snippet': 's', 'content': '開設課程：Python'}]
    )
    assert '內文摘錄：\n開設課程：Python' in text


async def test_ddgs_failure_returns_empty(monkeypatch):
    def boom(keywords, max_results):
        raise DDGSException('No results found.')

    monkeypatch.setattr(multi_engine, '_search_blocking', boom)
    assert await multi_engine.search_ddgs('東華大學 陳文盛') == []


async def test_ddgs_results_tagged_and_formatted(monkeypatch):
    import search as search_pkg

    def fake(keywords, max_results):
        return [{'title': 'T', 'url': 'https://t.com', 'snippet': 'S'}]

    monkeypatch.setattr(multi_engine, '_search_blocking', fake)
    search_pkg._load_engines()
    monkeypatch.setitem(search_pkg.SEARCH_ENGINES['ddgs'], 'search', multi_engine.search_ddgs)
    results = await search_pkg.search('q', engine='ddgs')
    assert results[0]['source_engine'] == 'ddgs'
    assert '【結果 1】' in format_results(results)
