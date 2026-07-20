import re
with open('d:/Ftel/otdr/backend/app_trace.py', encoding='utf-8') as f:
    content = f.read()
match = re.search(r'HTML_PAGE\s*=\s*\"\"\"(.*?)\"\"\"', content, re.DOTALL)
if match:
    with open('d:/Ftel/otdr/backend/reference.html', 'w', encoding='utf-8') as out:
        out.write(match.group(1))
    print("Extracted successfully")
else:
    print("Not found")
