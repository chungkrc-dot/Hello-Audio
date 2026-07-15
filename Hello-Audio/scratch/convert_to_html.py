import os
import base64
import re
import markdown

md_path = "docs/technical_manual.md"
html_path = "docs/technical_manual.html"

with open(md_path, "r") as f:
    text = f.readlines()

def get_base64_image(img_path):
    # Resolve path relative to the markdown file's directory (docs/)
    full_path = os.path.join("docs", img_path)
    if os.path.exists(full_path):
        with open(full_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
            ext = os.path.splitext(full_path)[1][1:].lower()
            if ext == 'jpg':
                ext = 'jpeg'
            return f"data:image/{ext};base64,{encoded_string}"
    return img_path

# Replace image paths with base64 data URIs
pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

new_text = []
for line in text:
    matches = pattern.findall(line)
    for alt, path in matches:
        b64_uri = get_base64_image(path)
        line = line.replace(f"({path})", f"({b64_uri})")
    new_text.append(line)

md_content = "".join(new_text)

# Convert to HTML with extensions for tables
html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])

# Add some nice academic CSS styling
css = """
<style>
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        line-height: 1.6;
        color: #333;
        max-width: 850px;
        margin: 0 auto;
        padding: 40px;
    }
    h1, h2, h3, h4 {
        color: #24292e;
        margin-top: 24px;
        margin-bottom: 16px;
        font-weight: 600;
        border-bottom: 1px solid #eaecef;
        padding-bottom: 0.3em;
    }
    h3 { border-bottom: none; }
    h4 { border-bottom: none; font-size: 1.1em; }
    table {
        border-collapse: collapse;
        width: 100%;
        margin-bottom: 20px;
    }
    table, th, td {
        border: 1px solid #dfe2e5;
    }
    th, td {
        padding: 6px 13px;
    }
    th {
        background-color: #f6f8fa;
        font-weight: 600;
    }
    tr:nth-child(even) {
        background-color: #f8f9fa;
    }
    img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 20px auto;
        border: 1px solid #ddd;
        border-radius: 4px;
        padding: 5px;
    }
    code {
        background-color: rgba(27,31,35,.05);
        border-radius: 3px;
        font-size: 85%;
        margin: 0;
        padding: .2em .4em;
        font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
    }
</style>
"""

html_document = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Technical Manual</title>
    {css}
</head>
<body>
    {html_body}
</body>
</html>
"""

with open(html_path, "w") as f:
    f.write(html_document)

print(f"Successfully compiled to {html_path}")
