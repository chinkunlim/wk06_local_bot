with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'r') as f:
    content = f.read()

# Replace smart quotes with proper escape sequences
content = content.replace('\u2018', "\\'")  # '
content = content.replace('\u2019', "\\'")  # '
content = content.replace('\u201c', '\\"')  # "
content = content.replace('\u201d', '\\"')  # "

with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'w') as f:
    f.write(content)
print('Fixed')