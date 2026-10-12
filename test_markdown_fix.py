def markdown_to_html(text: str) -> str:
    """將 Markdown 轉換為 Telegram 支援的 HTML"""
    if not text:
        return ''
    
    import re
    
    # ===== 階段 0: 保護所有特殊標記 =====
    protected = {}
    prot_id = 0
    
    def protect(match):
        nonlocal prot_id
        key = f'__PROTECTED_{prot_id}__'
        prot_id += 1
        protected[key] = match.group(0)
        return key
    
    # 保護程式碼區塊
    text = re.sub(r'```[\s\S]*?```', protect, text)
    # 保護行內程式碼
    text = re.sub(r'`[^`\n]+`', protect, text)
    # 保護已有的 HTML 標籤
    text = re.sub(r'<[^>]+>', protect, text)
    
    # ===== 階段 1: HTML 跳脫 =====
    text = text.replace('&', '&').replace('<', '<').replace('>', '>')
    
    # ===== 階段 2: 處理 Markdown =====
    # 粗體 **text** (處理未閉合)
    bold_count = text.count('**')
    if bold_count % 2 != 0:
        text += '**'
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # 斜體 *text* 或 _text_
    text = re.sub(r'(^|[^\*])\*([^\*\n]+)\*([^\*]|$)', r'\1<i>\2</i>\3', text)
    text = re.sub(r'(^|[^_])_([^_\n]+)_([^_]|$)', r'\1<i>\2</i>\3', text)
    
    # 標題 # text -> <b>text</b>
    text = re.sub(r'^#{1,6}\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    
    # 項目符號 - 或 * 開頭
    text = re.sub(r'^[\*\-\+]\s+(.+)$', r'• \1', text, flags=re.MULTILINE)
    
    # 分割線
    text = re.sub(r'^---+$', '──────────────', text, flags=re.MULTILINE)
    
    # 超連結 [text](url)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2">\1</a>', text)
    
    # ===== 階段 2: 還原受保護內容 =====
    # 先處理程式碼區塊和行內程式碼 (它們包含在 protected 中)
    def restore_protected(match):
        key = match.group(0)
        if key in protected:
            content = protected[key]
            # 程式碼區塊
            if content.startswith('```') and content.endswith('```'):
                code = content[3:-3]
                escaped = code.replace('&', '&').replace('<', '<').replace('>', '>')
                return f'<pre><code>{escaped.strip()}</code></pre>'
            # 行內程式碼
            if content.startswith('`') and content.endswith('`'):
                code = content[1:-1]
                escaped = code.replace('&', '&').replace('<', '<').replace('>', '>')
                return f'<code>{escaped}</code>'
            # HTML 標籤直接還原
            return content
        return key
    
    text = re.sub(r'__PROTECTED_\d+__', restore_protected, text)
    
    return text


# 測試
if __name__ == '__main__':
    test_cases = [
        ("**粗體**", "<b>粗體</b>"),
        ("*斜體*", "<i>斜體</i>"),
        ("`行內程式碼`", "<code>行內程式碼</code>"),
        ("[連結](https://example.com)", '<a href="https://example.com">連結</a>'),
        ("```python\nprint('hello')\n```", "<pre><code>print('hello')</code></pre>"),
        ("**粗體** 和 *斜體*", "<b>粗體</b> 和 <i>斜體</i>"),
    ]
    
    for md, expected in test_cases:
        result = markdown_to_html(md)
        status = "✅" if expected in result else "❌"
        print(f"{status} {md}")
        print(f"   預期: {expected}")
        print(f"   實際: {result}")
        print()