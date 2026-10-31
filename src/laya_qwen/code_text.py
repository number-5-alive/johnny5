"""Code shelf text conversion: HTML (Stack Overflow bodies, DevDocs pages) and MDN Markdown to plain text.

Code is the point of this shelf, so code blocks survive verbatim: every <pre> (or Markdown fence) becomes its lines
indented by four spaces, set off by blank lines. Inline code keeps backticks. Everything else becomes plain prose:
paragraphs, "- " list items, "> " quotes, "a | b" table rows, link text without URLs.
"""

import html
import re

from selectolax.lexbor import LexborHTMLParser

BLOCK = {"p", "div", "section", "article", "header", "footer", "aside", "main", "figure", "figcaption", "details",
         "summary", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "table", "thead", "tbody", "tfoot",
         "tr", "ul", "ol", "li", "blockquote", "pre", "nav"}
DROP = {"script", "style", "noscript", "svg", "button", "iframe", "img", "picture", "video", "audio", "template"}
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def indent_code(code: str) -> str:
    lines = code.replace("\r\n", "\n").replace("\t", "    ").strip("\n").split("\n")
    return "\n".join(("    " + ln).rstrip() for ln in lines)


def _inline(node) -> str:
    """Text of an inline run; <code> keeps backticks, <br> becomes a newline."""
    out = []
    for child in node.iter(include_text=True):
        tag = child.tag
        if tag == "-text":
            out.append(child.text_content or "")
        elif tag in DROP:
            continue
        elif tag == "br":
            out.append("\n")
        elif tag == "code" or tag == "kbd" or tag == "samp":
            t = child.text(deep=True)
            out.append(f"`{t}`" if t and "\n" not in t else t or "")
        elif tag in BLOCK:
            out.append("\n" + _blocks(child) + "\n")
        else:
            out.append(_inline(child))
    return "".join(out)


def _squash(text: str) -> str:
    return "\n".join(re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.split("\n")).strip()


def _blocks(node, depth: int = 0) -> str:
    """Block-level rendering of a node's children, paragraphs separated by blank lines."""
    parts, run = [], []

    def flush_run():
        t = _squash("".join(run))
        if t:
            parts.append(t)
        run.clear()

    for child in node.iter(include_text=True):
        tag = child.tag
        if tag == "-text":
            run.append(child.text_content or "")
            continue
        if tag in DROP:
            continue
        if tag not in BLOCK and tag != "br":
            run.append(_inline(child))
            continue
        if tag == "br":
            run.append("\n")
            continue
        flush_run()
        if tag == "pre":
            code = child.text(deep=True, separator="")
            if code.strip():
                parts.append(indent_code(html.unescape(code) if "&" in code and "<" not in code else code))
        elif tag in HEADINGS:
            t = _squash(_inline(child))
            if t:
                parts.append(t)
        elif tag in ("ul", "ol"):
            n, items = 0, []
            for li in child.iter(include_text=False):
                if li.tag != "li":
                    continue
                n += 1
                body = _blocks(li, depth + 1)
                if body:
                    mark = f"{n}. " if tag == "ol" else "- "
                    lines = body.split("\n")
                    items.append("\n".join([mark + lines[0]] + ["  " + ln if ln else ln for ln in lines[1:]]))
            if items:
                parts.append("\n".join(items))
        elif tag == "blockquote":
            body = _blocks(child, depth + 1)
            if body:
                parts.append("\n".join("> " + ln if ln else ">" for ln in body.split("\n")))
        elif tag == "table":
            rows = []
            for tr in child.css("tr"):
                cells = [_squash(_inline(td)) for td in tr.iter(include_text=False) if td.tag in ("td", "th")]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                parts.append("\n".join(rows))
        elif tag == "hr":
            continue
        else:
            body = _blocks(child, depth + 1)
            if body:
                parts.append(body)
    flush_run()
    return "\n\n".join(p for p in parts if p)


def html_to_text(fragment: str) -> str:
    tree = LexborHTMLParser(f"<div>{fragment}</div>")
    root = tree.body.child if tree.body and tree.body.child else tree.root
    return re.sub(r"\n{3,}", "\n\n", _blocks(root)).strip("\n").rstrip()  # keep a leading code block's indent


# ---------------------------------------------------------------- MDN Markdown

MACRO = re.compile(r"\{\{\s*([A-Za-z_][\w-]*)\s*(?:\((.*?)\))?\s*\}\}", re.S)
XREF_MACROS = {"jsxref", "domxref", "cssxref", "httpheader", "httpmethod", "httpstatus", "svgelement", "svgattr",
               "mathmlelement", "htmlattrxref", "glossary", "jsxref", "event", "rfc", "specname", "webextapiref",
               "cssxref", "domxref", "jsxref"}


def _macro(m: re.Match) -> str:
    name, args = m.group(1).lower(), m.group(2) or ""
    first = re.match(r'\s*["\']([^"\']*)["\'](?:\s*,\s*["\']([^"\']*)["\'])?', args)
    if name == "htmlelement" and first:
        return f"<{first.group(1)}>"
    if (name in XREF_MACROS or name.endswith("ref")) and first:
        return first.group(2) or first.group(1)
    return ""  # sidebars, compat tables, interactive examples, badges


def mdn_markdown_to_text(md: str) -> str:
    """MDN page body (front matter removed) to plain text; fenced code becomes indented."""
    out, fence, buf = [], None, []
    for line in md.split("\n"):
        stripped = line.strip()
        if fence is None and stripped.startswith("```"):
            fence = stripped[:3]
            buf = []
            continue
        if fence is not None:
            if stripped.startswith(fence):
                if any(b.strip() for b in buf):
                    out.extend(["", indent_code("\n".join(buf)), ""])
                fence = None
            else:
                buf.append(line)
            continue
        line = MACRO.sub(_macro, line)
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)  # images
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)  # links -> text
        line = re.sub(r"</?(?:br|kbd|sup|sub|var|em|strong|b|i|span|abbr|small)\b[^>\n]*>", "", line)  # inline markup
        line = re.sub(r"^\s*>\s*\*\*(Note|Warning|Callout):\*\*", r"\1:", line)
        out.append(line.rstrip())
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n").rstrip()
