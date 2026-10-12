with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'r') as f:
    content = f.read()

# Replace the broken decode_xml_entities function entirely
old_function = '''def decode_xml_entities(text):
    """解碼常見 XML / HTML 實體符號"""
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
    )'''

new_function = '''def decode_xml_entities(text):
    """解碼常見 XML / HTML 實體符號"""
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

if old_function in content:
    content = content.replace(old_function, new_function)
    print("Replaced old function")
else:
    print("Old function not found, checking for variants...")
    # Try to find and replace any decode_xml_entities function
    import re
    pattern = r'def decode_xml_entities\(text\):.*?\)\n'
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, new_function, content, flags=re.DOTALL)
        print("Replaced via regex")
    else:
        print("Could not find function")

with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'w') as f:
    f.write(content)
print("Done")