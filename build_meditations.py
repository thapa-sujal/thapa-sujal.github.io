#!/usr/bin/env python3
"""
build_meditations.py — compiles Markdown files in meditations/ into meditations-data.js.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  HOW TO ADD A NEW MEDITATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. Create a file in meditations/ named:
         YYYY-MM-DD-your-slug.md
     e.g. 2026-06-15-on-convergence.md

  2. Start the file with frontmatter between --- markers:

         ---
         title: Your Title Here
         date: June 2026
         tag: Philosophy
         ---

         First paragraph of your essay.

         Second paragraph. Blank lines separate paragraphs.

     Supported inline formatting:
         **bold**    →  <strong>bold</strong>
         *italic*    →  <em>italic</em>
         `code`      →  <code>code</code>

  3. Run:
         python3 build_meditations.py

  4. Refresh the browser. Done.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Files are sorted newest-first by filename (YYYY-MM-DD prefix).
"""

import os
import re
import json
import glob

MEDITATIONS_DIR = "meditations"
OUTPUT_FILE     = "meditations-data.js"


def parse_frontmatter(content):
    """Split YAML-ish frontmatter (between --- markers) from body."""
    content = content.strip()
    if not content.startswith("---"):
        return {}, content

    end_idx = content.find("---", 3)
    if end_idx == -1:
        return {}, content

    front_block = content[3:end_idx].strip()
    body        = content[end_idx + 3:].strip()

    meta = {}
    for line in front_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    return meta, body


def render_inline(text):
    """Inline formatting. Math spans ($...$ and $$...$$) are protected from
    formatting and left verbatim so MathJax can typeset them in the browser.
    Raw HTML (e.g. <i>...</i>) passes through untouched."""
    # 1. Stash math so the formatters below never touch its contents.
    math_spans = []

    def _stash(m):
        math_spans.append(m.group(0))
        return f"\x00MATH{len(math_spans) - 1}\x00"

    text = re.sub(r"\$\$.+?\$\$", _stash, text, flags=re.S)  # display first
    text = re.sub(r"\$.+?\$",     _stash, text)               # then inline

    # 2. Links: [text](url)  → opens in a new tab
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        text,
    )

    # 3. Emphasis / code
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         text)
    text = re.sub(r"`(.+?)`",       r"<code>\1</code>",     text)

    # 4. Restore math verbatim
    for i, span in enumerate(math_spans):
        text = text.replace(f"\x00MATH{i}\x00", span)

    return text


def opening_preview(text):
    """Use the article's opening prose paragraph as its listing subtext."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue

        first = lines[0]
        if (first.startswith((">", "#"))
                or re.match(r"\d+\.\s", first)
                or re.match(r"!\[[^\]]*\]\([^)]+\)", first)):
            continue

        return render_inline(" ".join(lines))

    return ""


def md_to_html(text):
    """Convert the Markdown body to HTML. Supports paragraphs, blockquotes,
    ordered lists (with an optional bold lead line + indented body), images
    (rendered as <figure> with caption), links, inline emphasis, and LaTeX
    math (passed through verbatim for MathJax)."""
    lines = text.strip("\n").split("\n")
    blocks = []
    i, n = 0, len(lines)

    img_re  = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    item_re = re.compile(r"\d+\.\s")

    while i < n:
        stripped = lines[i].strip()

        # blank line → block separator
        if not stripped:
            i += 1
            continue

        # image → figure with caption
        m = img_re.match(stripped)
        if m:
            alt, src = m.group(1), m.group(2)
            # Paths are written relative to the .md (in meditations/); the pages
            # that consume this HTML live at the project root, so prefix local
            # paths with the meditations dir.
            if not re.match(r"(https?:)?//|/", src):
                src = f"{MEDITATIONS_DIR}/{src}"
            fig = f'<figure class="med-figure"><img src="{src}" alt="{alt}" loading="lazy">'
            if alt:
                fig += f"<figcaption>{render_inline(alt)}</figcaption>"
            fig += "</figure>"
            blocks.append(fig)
            i += 1
            continue

        # blockquote → collect consecutive '>' lines
        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append(f"<blockquote>{render_inline(' '.join(quote))}</blockquote>")
            continue

        # ordered list → each item: first line is a bold lead, indented
        # continuation lines form the body
        if item_re.match(stripped):
            items = []
            while i < n and item_re.match(lines[i].strip()):
                lead = re.match(r"\d+\.\s+(.*)", lines[i].strip()).group(1)
                i += 1
                body = []
                while (i < n and lines[i].strip()
                       and lines[i][:1] in (" ", "\t")
                       and not item_re.match(lines[i].strip())):
                    body.append(lines[i].strip())
                    i += 1
                lead_html = render_inline(lead)
                if body:
                    items.append(
                        f"<li><strong>{lead_html}</strong> "
                        f"{render_inline(' '.join(body))}</li>"
                    )
                else:
                    items.append(f"<li>{lead_html}</li>")
            blocks.append("<ol>" + "".join(items) + "</ol>")
            continue

        # paragraph → collect consecutive plain lines
        para = []
        while (i < n and lines[i].strip()
               and not lines[i].strip().startswith(">")
               and not item_re.match(lines[i].strip())
               and not img_re.match(lines[i].strip())):
            para.append(lines[i].strip())
            i += 1
        blocks.append(f"<p>{render_inline(' '.join(para))}</p>")

    return "\n          ".join(blocks)


def build():
    pattern  = os.path.join(MEDITATIONS_DIR, "*.md")
    md_files = sorted(glob.glob(pattern), reverse=True)  # newest filename first

    if not md_files:
        print(f"No .md files found in {MEDITATIONS_DIR}/")
        return

    meditations = []
    print(f"Building from {MEDITATIONS_DIR}/:\n")

    for filepath in md_files:
        with open(filepath, encoding="utf-8") as f:
            raw = f.read()

        meta, body = parse_frontmatter(raw)

        if not meta.get("title"):
            print(f"  ⚠  Skipped  {os.path.basename(filepath)} — missing 'title' in frontmatter")
            continue

        meditations.append({
            "title":   meta.get("title",   "Untitled"),
            "date":    meta.get("date",    ""),
            "tag":     meta.get("tag",     "Essay"),
            "preview": opening_preview(body),
            "body":    md_to_html(body),
        })
        print(f"  ✓  {os.path.basename(filepath)}")

    js_entries = json.dumps(meditations, indent=2, ensure_ascii=False)

    output = f"""// Auto-generated by build_meditations.py — do not edit this file directly.
// To publish a new meditation: add a .md file to meditations/ and run:
//   python3 build_meditations.py

const MEDITATIONS = {js_entries};
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n✓  Wrote {len(meditations)} meditation(s) → {OUTPUT_FILE}")


if __name__ == "__main__":
    build()
