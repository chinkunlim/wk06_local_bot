#!/usr/bin/env python3
"""
Markdown 解析器測試
"""
import sys
sys.path.insert(0, '/Users/limchinkun/Desktop/wk06_bot_local')

from bot.handler import markdown_to_html


def test_basic():
    """基本測試"""
    print("=== 基本測試 ===")
    cases = [
        ("**粗體**", "<b>粗體</b>"),
        ("*斜體*", "<i>斜體</i>"),
        ("`行內程式碼`", "<code>行內程式碼</code>"),
        ("[連結](https://example.com)", '<a href="https://example.com">連結</a>'),
    ]
    for md, expected in cases:
        result = markdown_to_html(md)
        assert expected in result, f"預期 {expected}，得到 {result}"
        print(f"✅ {md} -> {result}")


def test_code_blocks():
    """程式碼區塊測試"""
    print("\n=== 程式碼區塊測試 ===")
    md = '''```python
print("hello")
```'''
    result = markdown_to_html(md)
    assert '<pre><code>' in result
    assert 'print("hello")' in result
    print(f"✅ 多行程式碼: {result[:100]}")


def test_headers():
    """標題測試"""
    print("\n=== 標題測試 ===")
    cases = [
        ("# 標題", "<b>標題</b>"),
        ("## 二級標題", "<b>二級標題</b>"),
        ("### 三級標題", "<b>三級標題</b>"),
    ]
    for md, expected in cases:
        result = markdown_to_html(md)
        assert expected in result, f"預期 {expected}，得到 {result}"
        print(f"✅ {md} -> {result}")


def test_bullet_points():
    """項目符號測試"""
    print("\n=== 項目符號測試 ===")
    md = "- 項目一\n- 項目二\n* 項目三"
    result = markdown_to_html(md)
    assert result.count('•') == 3
    print(f"✅ 項目符號轉換: {result}")


def test_complex():
    """複雜混合測試"""
    print("\n=== 複雜混合測試 ===")
    md = """**標題**
    
這是*斜體*和**粗體**文字。

- 項目一
- 項目二

`print("code")`

[Google](https://google.com)
"""
    result = markdown_to_html(md)
    print(result)
    assert '<b>標題</b>' in result
    assert '<i>斜體</i>' in result
    assert '<b>粗體</b>' in result
    assert '• 項目一' in result
    assert '<code>print("code")</code>' in result
    assert '<a href="https://google.com">Google</a>' in result
    print("✅ 複雜混合測試通過")


def test_unescaped_bold():
    """未閉合粗體測試"""
    print("\n=== 未閉合粗體測試 ===")
    md = "這是**粗體沒閉合"
    result = markdown_to_html(md)
    print(f"結果: {result}")
    assert '<b>粗體沒閉合</b>' in result
    print("✅ 自動補齊閉合標籤")


def test_html_escaping():
    """HTML 跳脫測試"""
    print("\n=== HTML 跳脫測試 ===")
    md = "5 < 10 & 3 > 2"
    result = markdown_to_html(md)
    assert '<' in result
    assert '>' in result
    assert '&' in result
    print(f"✅ HTML 跳脫: {result}")


def main():
    test_basic()
    test_code_blocks()
    test_headers()
    test_bullet_points()
    test_complex()
    test_unescaped_bold()
    test_html_escaping()
    print("\n🎉 所有 Markdown 測試通過！")


if __name__ == '__main__':
    main()