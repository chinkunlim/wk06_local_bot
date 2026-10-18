#!/usr/bin/env python3
"""
搜尋備援測試 (離線)：DuckDuckGo 被機器人驗證擋下時改用 Google News
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import search as search_pkg
from search import duckduckgo, format_results, search


@pytest.fixture
def engines(monkeypatch):
    """以假的搜尋函式取代兩個引擎，記錄呼叫順序"""
    search_pkg._load_engines()
    calls: list[str] = []
    data = {'duckduckgo': [], 'google_news': []}

    def make(name):
        async def fake(query, max_results):
            calls.append(name)
            return [dict(r) for r in data[name]]
        return fake

    for name in data:
        monkeypatch.setitem(search_pkg.SEARCH_ENGINES[name], 'search', make(name))
    monkeypatch.setattr(search_pkg.settings, 'SEARCH_ENGINE', 'duckduckgo')
    monkeypatch.setattr(search_pkg.settings, 'SEARCH_FALLBACK_ENGINE', 'google_news')
    return calls, data


def test_challenge_page_detection():
    assert duckduckgo.is_challenge_page(202, '<html>anomaly-modal</html>')
    assert duckduckgo.is_challenge_page(200, '<div class="anomaly-modal__title">')
    assert not duckduckgo.is_challenge_page(200, '<div class="result__body">x</div>')
    assert not duckduckgo.is_challenge_page(200, '<html>no results</html>')


async def test_no_fallback_when_primary_has_results(engines):
    calls, data = engines
    data['duckduckgo'] = [{'title': 'D', 'url': 'https://d.com', 'snippet': 's'}]
    results = await search('q')
    assert calls == ['duckduckgo']
    assert results[0]['source_engine'] == 'duckduckgo'


async def test_fallback_when_primary_empty(engines):
    calls, data = engines
    data['google_news'] = [{'title': 'G', 'url': 'https://g.com', 'description': 'd', 'pubDate': 'today'}]
    results = await search('q')
    assert calls == ['duckduckgo', 'google_news']
    assert results[0]['source_engine'] == 'google_news'
    # 依來源引擎選擇格式，Google News 結果沒有 snippet 也不會 KeyError
    assert '【即時新聞檢索結果】' in format_results(results)


async def test_fallback_disabled(engines, monkeypatch):
    calls, _ = engines
    monkeypatch.setattr(search_pkg.settings, 'SEARCH_FALLBACK_ENGINE', '')
    assert await search('q') == []
    assert calls == ['duckduckgo']


async def test_blocked_cooldown_skips_request(monkeypatch):
    """冷卻期內不送出請求 (若送出會因 httpx 被替換而失敗)"""
    monkeypatch.setattr(duckduckgo, '_blocked_until', 0.0)
    duckduckgo.mark_blocked(60)
    assert duckduckgo.is_blocked()

    class _NoNetwork:
        def __init__(self, *a, **k):
            raise AssertionError('冷卻期內不應發出請求')

    monkeypatch.setattr(duckduckgo.httpx, 'AsyncClient', _NoNetwork)
    assert await duckduckgo.search_duckduckgo('台灣 天氣') == []


async def test_challenge_response_triggers_cooldown(monkeypatch):
    monkeypatch.setattr(duckduckgo, '_blocked_until', 0.0)

    class _Resp:
        status_code = 202
        text = '<html><div class="anomaly-modal"></div></html>'

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(duckduckgo.httpx, 'AsyncClient', _Client)
    assert await duckduckgo.search_duckduckgo('台灣 天氣') == []
    assert duckduckgo.is_blocked()
