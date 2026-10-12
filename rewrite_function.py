with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'r') as f:
    content = f.read()

# Find the function and replace entirely
import re

# Pattern to match the broken function
pattern = r'def decode_xml_entities\(text: str\) -> str:.*?\n\)\s*\n'

new_function = '''def decode_xml_entities(text: str) -> str:
    """解碼 XML/HTML 實體"""
    if not text:
        return ""
    return (text
        .replace("&", "&")
        .replace("<", "<")
        .replace(">", ">")
        .replace('"', '"')
        .replace("\u2018", "'")
        .replace("&nbsp;", " ")
        .replace("&#8230;", "...")
        .replace("&#8217;", "'")
        .replace("&#8220;", '"')
        .replace("&#8221;", '"')
    )'''

# Use DOTALL to match across lines
new_content = re.sub(r'def decode_xml_entities\(text: str\) -> str:.*?^\s*\)\s*\n', new_function, content, flags=re.DOTALL | re.MULTILINE)

if new_content != content:
    with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'w') as f:
        f.write(new_content)
    print("Replaced function via regex")
else:
    print("Pattern not matched, trying alternative...")
    # Try simpler approach - just replace the whole block
    old_block = '''def decode_xml_entities(text: str) -> str:
    """解碼 XML/HTML 實體"""
    if not text:
        return ''
    return (text
        .replace('&', '&')
        .replace('<', '<')
        .replace('>', '>')
        .replace('"', '"')
        .replace(', "'")
        .replace('&nbsp;', ' ')
        .replace('&#8230;', '...')
        .replace('&#8217;', "'")
        .replace('&#8220;', '"')
        .replace('&#8221;', '"')
        .replace('&#8217;', "'")
        .replace('&#8220;', '"')
        .replace('&#8221;', '"')
    )'''
    
    if old_block in content:
        content = content.replace(old_block, new_function)
        with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'w') as f:
            f.write(content)
        print("Replaced exact block")
    else:
        print("Could not find exact block either")

print("Done")