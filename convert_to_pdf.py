"""Convert paper.md to paper.pdf using markdown + weasyprint."""
import markdown
from weasyprint import HTML

# Read markdown
with open("paper.md", "r", encoding="utf-8") as f:
    md_text = f.read()

# Convert to HTML
html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])

# Wrap in styled HTML
html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: letter;
        margin: 1in;
    }}
    body {{
        font-family: 'Georgia', 'Times New Roman', serif;
        font-size: 11pt;
        line-height: 1.5;
        color: #1a1a1a;
        max-width: 100%;
    }}
    h1 {{
        font-size: 18pt;
        text-align: center;
        margin-bottom: 0.3em;
        line-height: 1.2;
    }}
    h2 {{
        font-size: 14pt;
        margin-top: 1.5em;
        border-bottom: 1px solid #ccc;
        padding-bottom: 0.2em;
    }}
    h3 {{
        font-size: 12pt;
        margin-top: 1.2em;
    }}
    p {{
        margin-bottom: 0.8em;
        text-align: justify;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin: 1em 0;
        font-size: 10pt;
    }}
    th, td {{
        border: 1px solid #999;
        padding: 4px 8px;
        text-align: left;
    }}
    th {{
        background-color: #f0f0f0;
        font-weight: bold;
    }}
    code {{
        font-family: 'Courier New', monospace;
        font-size: 10pt;
        background-color: #f5f5f5;
        padding: 1px 4px;
    }}
    blockquote {{
        border-left: 3px solid #ccc;
        margin-left: 0;
        padding-left: 1em;
        color: #555;
    }}
    hr {{
        border: none;
        border-top: 1px solid #ccc;
        margin: 2em 0;
    }}
    strong {{
        font-weight: bold;
    }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

# Convert to PDF
HTML(string=html_doc).write_pdf("paper.pdf")
print("Generated paper.pdf")
