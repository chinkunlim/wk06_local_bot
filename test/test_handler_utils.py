#!/usr/bin/env python3
"""
Handler 工具函式與錯誤處理測試 (離線，不需 Ollama/網路)
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from bot import handler as handler_mod
from bot.conversation import check_and_consume_quota, get_quota_status, reset_user_quota
from bot.handler import BotHandler, html_to_plain, markdown_to_html, split_message
from config.settings import Settings, _parse_user_ids
from search import get_search_engine
from search.duckduckgo import extract_search_keywords
from search.google_news import clean_html, decode_xml_entities


def test_markdown_keeps_urls_intact():
    assert markdown_to_html('[文件](https://a.com/foo_bar_baz)') == '<a href="https://a.com/foo_bar_baz">文件</a>'
    assert markdown_to_html('見 https://a.com/my_file_name.py') == '見 https://a.com/my_file_name.py'
    assert markdown_to_html('[**粗**](https://a.com)') == '<a href="https://a.com"><b>粗</b></a>'
    assert markdown_to_html('網址 https://a.com?x=1&y=2。') == '網址 https://a.com?x=1&amp;y=2。'
    # 詞內底線不當斜體，獨立 _x_ 仍為斜體
    assert markdown_to_html('snake_case_name') == 'snake_case_name'
    assert markdown_to_html('這是 _斜體_ 字') == '這是 <i>斜體</i> 字'


def test_split_message():
    assert split_message('短訊息') == ['短訊息']
    text = '\n'.join(f'第 {i} 行 ' + 'x' * 50 for i in range(200))
    chunks = split_message(text, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert '\n'.join(chunks) == text
    # 單行超長硬切
    long_line = 'y' * 2500
    chunks = split_message(long_line, limit=1000)
    assert [len(c) for c in chunks] == [1000, 1000, 500]


def test_html_to_plain():
    assert html_to_plain('<b>5 &lt; 10</b> &amp; ok') == '5 < 10 & ok'


def test_keywords_do_not_mangle_words():
    assert extract_search_keywords('和平 協議') == '和平 協議'
    assert extract_search_keywords('請假 規定') == '請假 規定'
    assert extract_search_keywords('C++ 教學') == 'C++ 教學'
    assert extract_search_keywords('C# 入門') == 'C# 入門'
    assert extract_search_keywords('llama3.1 發布。') == 'llama3.1 發布'
    assert extract_search_keywords('台灣今天天氣如何？') == '台灣 天氣'
    assert extract_search_keywords('iPhone 17 好用嗎') == 'iPhone 17 好用'


def test_google_news_entities():
    assert decode_xml_entities('A &amp; B &lt;tag&gt; &#8217;s&nbsp;x') == "A & B <tag> ’s x"
    assert clean_html('&lt;a href="x"&gt;標題&lt;/a&gt;&amp;nbsp;') == '標題'


def test_parse_user_ids():
    assert _parse_user_ids('123, 456,,') == ([123, 456], [])
    assert _parse_user_ids('123,abc') == ([123], ['abc'])


def test_validate_search_engine(monkeypatch):
    monkeypatch.setattr(Settings, 'SEARCH_ENGINE', 'google_news_rss')
    assert any('SEARCH_ENGINE' in e for e in Settings.validate())
    # 即使設定錯誤，搜尋工廠也不會 KeyError
    assert get_search_engine()['name'] == 'DuckDuckGo HTML'


class _FailingOllama:
    def __init__(self, exc):
        self.exc = exc

    async def chat_with_tools(self, **kwargs):
        raise self.exc


def _fake_update(user_id: int):
    return SimpleNamespace(
        update_id=1,
        effective_user=SimpleNamespace(id=user_id, first_name='T', username=None),
        effective_chat=SimpleNamespace(id=user_id),
    )


async def _run_failing_query(monkeypatch, exc) -> list[str]:
    user_id = 424242
    reset_user_quota(user_id)
    errors: list[str] = []

    bh = BotHandler()
    bh.ollama_client = _FailingOllama(exc)

    async def fake_status(update, text, parse_mode=None):
        return None

    async def fake_error(update, text):
        errors.append(text)

    monkeypatch.setattr(bh, 'send_status', fake_status)
    monkeypatch.setattr(bh, 'send_error', fake_error)
    monkeypatch.setattr(handler_mod, 'get_conversation_history', lambda uid: [])

    quota = check_and_consume_quota(user_id)
    assert get_quota_status(user_id)['current'] == 1
    await bh._process_query(_fake_update(user_id), '你好', quota)

    # 失敗時退還額度
    assert get_quota_status(user_id)['current'] == 0
    reset_user_quota(user_id)
    return errors


async def test_process_query_connect_error(monkeypatch):
    errors = await _run_failing_query(monkeypatch, httpx.ConnectError('refused'))
    assert len(errors) == 1 and 'Ollama' in errors[0]


async def test_process_query_timeout(monkeypatch):
    errors = await _run_failing_query(monkeypatch, httpx.ReadTimeout('slow'))
    assert len(errors) == 1 and '逾時' in errors[0]


async def test_process_query_unexpected_error(monkeypatch):
    errors = await _run_failing_query(monkeypatch, ValueError('boom'))
    assert len(errors) == 1 and '不計入額度' in errors[0]
