"""Render a markdown file to a print-ready HTML page, in the app's own look."""
import pathlib, sys
import markdown

SRC, OUT, TITLE = sys.argv[1], sys.argv[2], sys.argv[3]

CSS = """
@page { size: A4; margin: 18mm 16mm 16mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Inter", -apple-system, "Segoe UI", system-ui, sans-serif;
       font-size: 10pt; line-height: 1.6; color: #18181B; margin: 0; }
h1 { font-size: 26pt; font-weight: 800; letter-spacing: -0.035em;
     margin: 0 0 14px; color: #000; }
h2 { font-size: 14.5pt; font-weight: 700; letter-spacing: -0.02em;
     margin: 24px 0 9px; padding-bottom: 6px;
     border-bottom: 2px solid #7B1E22; color: #000; break-after: avoid; }
h3 { font-size: 11pt; font-weight: 700; margin: 16px 0 5px; color: #000;
     break-after: avoid; }
p { margin: 0 0 9px; }
ul, ol { margin: 0 0 10px; padding-left: 18px; }
li { margin-bottom: 3px; }
blockquote { border-left: 3px solid #7B1E22; background: #FAFAFA;
             margin: 12px 0; padding: 10px 14px; border-radius: 0 7px 7px 0;
             font-size: 9.4pt; break-inside: avoid; }
blockquote p:last-child { margin-bottom: 0; }
code { font-family: "Consolas", "SF Mono", monospace; font-size: 8.6pt;
       background: #F4F4F5; padding: 1px 4px; border-radius: 3px; }
pre { background: #FAFAFA; border: 1px solid #E4E4E7; border-radius: 8px;
      padding: 12px 14px; overflow-x: auto; font-size: 8.4pt;
      line-height: 1.45; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.4pt; }
table { width: 100%; border-collapse: collapse; margin: 9px 0 14px;
        font-size: 9pt; break-inside: avoid; }
th { text-align: left; font-size: 7.6pt; font-weight: 700; color: #71717A;
     text-transform: uppercase; letter-spacing: 0.05em;
     padding: 0 9px 6px 0; border-bottom: 1px solid #E4E4E7; }
td { padding: 7px 9px 7px 0; border-bottom: 1px solid #F4F4F5;
     vertical-align: top; }
td:last-child, th:last-child { padding-right: 0; }
a { color: #7B1E22; text-decoration: none; }
hr { border: none; border-top: 1px solid #E4E4E7; margin: 22px 0; }
"""

text = pathlib.Path(SRC).read_text(encoding="utf-8").lstrip("﻿")
html = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])

pathlib.Path(OUT).write_text(
    f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
    f"<title>{TITLE}</title><style>{CSS}</style></head><body>{html}</body></html>",
    encoding="utf-8")
print("wrote", OUT)
