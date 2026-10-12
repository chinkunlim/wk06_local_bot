#!/usr/bin/env python3
"""
搜尋功能測試
"""
import asyncio
import sys
sys.path.insert(0, '/Users/limchinkun/Desktop/wk06_bot_local')

from search import search, format_results, search_sync


async def test_search_duckduckgo():
    """測試 DuckDuckGo 搜尋"""
    print("=== 測試 DuckDuckGo 搜尋 ===")
    result = await search('台灣 天氣', max_results=4)
    assert len(result) > 0, "應該有搜尋結果"
    print(f"✅ 搜尋成功: {len(result)} 筆結果")
    for r in result:
        print(f"  - {r['title'][:60]}")
        print(f"    {r['url']}")
    return result


async def test_search_google_news():
    """測試 Google News 搜尋"""
    print("\n=== 測試 Google News 搜尋 ===")
    from search import SEARCH_ENGINES
    SEARCH_ENGINES['google_news']['search'] = None  # 強制重新載入
    from search.google_news import search_google_news
    result = await search_google_news('台灣 天氣', max_results=4)
    if result:
        print(f"✅ Google News 搜尋成功: {len(result)} 筆結果")
        for r in result:
            print(f"  - {r['title'][:60]}")
    else:
        print("⚠️ Google News 無結果 (可能無相關新聞)")
    return result


def test_format_results():
    """測試結果格式化"""
    print("\n=== 測試格式化 ===")
    sample = [{
        'title': '測試標題',
        'url': 'https://example.com',
        'snippet': '測試摘要內容...'
    }]
    formatted = format_results(sample)
    assert '測試標題' in formatted
    assert 'https://example.com' in formatted
    assert '測試摘要' in formatted
    print("✅ 格式化正常")
    print(formatted[:200])


async def test_search_sync():
    """測試同步版本"""
    print("\n=== 測試同步搜尋 ===")
    result = search_sync('台灣 天氣', max_results=2)
    assert len(result) > 0
    print(f"✅ 同步搜尋成功: {len(result)} 筆")


async def main():
    await test_search_duckduckgo()
    await test_search_google_news()
    test_format_results()
    await test_search_sync()
    print("\n🎉 所有搜尋測試通過！")


if __name__ == '__main__':
    asyncio.run(main())