with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'r') as f:
    lines = f.readlines()

# Fix line 178 (index 177)
lines[177] = r'        .replace("\u2018", "\'")\n'

# Line 179 (index 178)
lines[178] = "        .replace('&nbsp;', ' ')\n"

# Line 180 (index 179)
lines[179] = "        .replace('&#8230;', '...')\n"

# Line 181 (index 180)
lines[180] = r'        .replace("&#8217;", "\'")\n'

# Line 182 (index 181)
lines[181] = r'        .replace("&#8220;", "\"")\n'

# Line 183 (index 182)
lines[182] = r'        .replace("&#8221;", "\"")\n'

with open('/Users/limchinkun/Desktop/wk06_bot_local/search/google_news.py', 'w') as f:
    f.writelines(lines)
print("Fixed lines")