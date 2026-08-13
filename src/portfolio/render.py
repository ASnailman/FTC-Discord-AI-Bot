"""Renders a validated `schema.PortfolioDoc` to HTML and to Markdown.

This module is the only place that produces markup, and it is the last
line of defense against the LLM's text ending up as executable content in
a browser. Three layers, in order:

1. Every text field is HTML-escaped (`html.escape`) before anything else
   touches it -- `<`, `>`, `&`, `"`, `'` become entities. This alone makes
   `<script>...</script>` inert.
2. A tiny, fixed inline formatter (`**bold**`, `*italic*`, `` `code` ``)
   runs *after* escaping and only ever wraps already-escaped text in a
   literal `<strong>`/`<em>`/`<code>` tag -- there is no way for input text
   to introduce a tag, attribute, or URL scheme, because the only markup
   this function ever emits is these three hardcoded tags.
3. `render_html` runs a final regex scan for a literal, unescaped
   `<script`, `<iframe`, `<object`, or `<embed` tag and raises
   `RenderSecurityError` if one is found. This module never intentionally
   emits any of those four tag names, so the only way one can appear in
   the assembled document is if step (1) was skipped for some field --
   i.e. a bug in this module, not attacker input. (The scan deliberately
   does *not* blocklist bare substrings like "javascript:" or "onerror=":
   escaping does not, and should not, remove those characters from
   legitimate visible text -- e.g. a team's own copy describing their
   control code -- and since `<`/`>` are always escaped first, such text
   can never become a real attribute or tag regardless of its content.)
   Given (1) and (2), this should never fire; it exists as defense in
   depth against a bug in this module, not as the primary control -- see
   docs/security.md.

Image references are `int` indices into the caller's `images` inventory
(never a path/URL from the model), resolved here to an embedded `data:`
URI. An out-of-range index is dropped, not an error -- a model
hallucinating "image 7" when only 3 were uploaded shouldn't fail the whole
run.
"""
import html
import re
from dataclasses import dataclass

from .schema import Banner, Card, Columns, FigureGrid, PortfolioDoc, RubricTable, StatRow
from .theme import build_css, watermark_svg

_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"\*([^*]+)\*")

_FORBIDDEN_RE = re.compile(r"<script|<iframe|<object|<embed", re.IGNORECASE)


class RenderSecurityError(Exception):
    """Raised if the final assembled HTML matches the forbidden-content
    scan. Should never happen given the escaping this module does; treat
    any real occurrence as a bug in render.py, not a user-fixable error."""


@dataclass(frozen=True)
class PortfolioImage:
    data_uri: str
    alt_text: str = ""


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _inline(text: str) -> str:
    """Escape, then apply the fixed bold/italic/code formatter. Safe
    because the formatter only wraps already-escaped text in a hardcoded
    tag -- it never emits an attribute or reads one from `text`."""
    escaped = _esc(text)
    escaped = _CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", escaped)
    escaped = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", escaped)
    escaped = _ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", escaped)
    return escaped


def _resolve_image(index: int, images: list[PortfolioImage]) -> "PortfolioImage | None":
    if 0 <= index < len(images):
        return images[index]
    return None


def _render_banner(block: Banner) -> str:
    return f'<div class="banner">{_inline(block.text)}</div>'


def _render_stat_row(block: StatRow) -> str:
    stats = "".join(
        f'<div class="stat"><div class="value">{_esc(s.value)}</div>'
        f'<div class="label">{_esc(s.label)}</div></div>'
        for s in block.stats
    )
    return f'<div class="stat-row">{stats}</div>'


def _render_card_inner(card: Card) -> str:
    bullets = "".join(f"<li>{_inline(b)}</li>" for b in card.bullets)
    bullets_html = f"<ul>{bullets}</ul>" if bullets else ""
    body_html = f"<p>{_inline(card.body)}</p>" if card.body else ""
    return f"<h3>{_inline(card.heading)}</h3>{body_html}{bullets_html}"


def _render_card(block: Card) -> str:
    return f'<div class="card">{_render_card_inner(block)}</div>'


def _render_columns(block: Columns) -> str:
    cards = "".join(f'<div class="card">{_render_card_inner(c)}</div>' for c in block.cards)
    return f'<div class="columns">{cards}</div>'


def _render_figure_grid(block: FigureGrid, images: list[PortfolioImage]) -> str:
    figures = []
    for i, idx in enumerate(block.images):
        img = _resolve_image(idx, images)
        if img is None:
            continue
        caption = block.captions[i] if i < len(block.captions) else ""
        alt = _esc(img.alt_text or caption or "portfolio image")
        cap_html = f'<div class="caption">{_inline(caption)}</div>' if caption else ""
        figures.append(f'<div class="figure"><img src="{img.data_uri}" alt="{alt}">{cap_html}</div>')
    if not figures:
        return ""
    return f'<div class="figure-grid">{"".join(figures)}</div>'


def _render_rubric_table(block: RubricTable) -> str:
    rows = []
    for row in block.rows:
        rows.append(
            f'<tr class="category"><td colspan="4">{_esc(row.category)}</td></tr>'
            if not row.goal and not row.result
            else (
                f"<tr><td>{_esc(row.category)}</td><td>{_inline(row.goal)}</td>"
                f"<td>{_inline(row.result)}</td><td>{_esc(row.page)}</td></tr>"
            )
        )
    return (
        '<table class="rubric"><thead><tr>'
        "<th>Category</th><th>Goal</th><th>Result</th><th>Page</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


_RENDERERS = {
    "banner": lambda b, images: _render_banner(b),
    "stat_row": lambda b, images: _render_stat_row(b),
    "card": lambda b, images: _render_card(b),
    "columns": lambda b, images: _render_columns(b),
    "figure_grid": _render_figure_grid,
    "rubric_table": lambda b, images: _render_rubric_table(b),
}


def _render_page(page, images: list[PortfolioImage], watermark: str) -> str:
    blocks_html = "".join(_RENDERERS[block.kind](block, images) for block in page.blocks)
    label = _esc(page.page_label) if page.page_label else ""
    return (
        f'<section class="page">'
        f'<div class="watermark">{watermark}</div>'
        f'<div class="page-body">'
        f'<div class="page-header"><h1>{_inline(page.title)}</h1><div class="rule"></div>'
        f'<div class="page-label">{label}</div></div>'
        f"{blocks_html}"
        f"</div></section>"
    )


def _render_cover(doc: PortfolioDoc) -> str:
    return (
        '<section class="cover">'
        '<div class="band-a"></div><div class="band-b"></div>'
        '<div class="content">'
        f'<div class="team-number">{_esc(str(doc.team_number))}</div>'
        f'<div class="team-name">{_esc(doc.team_name)}</div>'
        f'<div class="subtitle">{_inline(doc.subtitle)}</div>'
        f'<div class="season">{_esc(doc.season_label)}</div>'
        "</div><div class=\"footer-bar\"></div>"
        "</section>"
    )


def render_html(doc: PortfolioDoc, images: "list[PortfolioImage] | None" = None) -> str:
    images = images or []
    watermark = watermark_svg(doc.team_number)
    css = build_css(doc.accent)

    pages_html = _render_cover(doc)
    for page in doc.pages:
        pages_html += _render_page(page, images, watermark)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(doc.team_name or str(doc.team_number))} -- Engineering Portfolio</title>
<style>{css}</style>
</head>
<body>
{pages_html}
</body>
</html>"""

    if _FORBIDDEN_RE.search(html_doc):
        raise RenderSecurityError("generated HTML matched the forbidden-content scan")
    return html_doc


# --- Markdown companion ---

_TAG_RE = re.compile(r"<[^>]*>")


def _md_text(text: str) -> str:
    """Strip any literal HTML tags (defense in depth against the .md file
    being opened by a viewer that renders embedded HTML) without altering
    the already-safe **bold**/*italic*/`code` markdown syntax."""
    return _TAG_RE.sub("", text or "")


def _render_block_md(block) -> list[str]:
    lines: list[str] = []
    if isinstance(block, Banner):
        lines.append(f"> **{_md_text(block.text)}**")
    elif isinstance(block, StatRow):
        lines.append(" | ".join(f"**{_md_text(s.value)}** {_md_text(s.label)}" for s in block.stats))
    elif isinstance(block, Card):
        lines.append(f"#### {_md_text(block.heading)}")
        if block.body:
            lines.append(_md_text(block.body))
        for b in block.bullets:
            lines.append(f"- {_md_text(b)}")
    elif isinstance(block, Columns):
        for card in block.cards:
            lines.extend(_render_block_md(card))
            lines.append("")
    elif isinstance(block, FigureGrid):
        for i, idx in enumerate(block.images):
            caption = block.captions[i] if i < len(block.captions) else ""
            lines.append(f"- _Image {idx}_ -- {_md_text(caption)}" if caption else f"- _Image {idx}_")
    elif isinstance(block, RubricTable):
        lines.append("| Category | Goal | Result | Page |")
        lines.append("|---|---|---|---|")
        for row in block.rows:
            lines.append(
                f"| {_md_text(row.category)} | {_md_text(row.goal)} | "
                f"{_md_text(row.result)} | {_md_text(row.page)} |"
            )
    return lines


def render_markdown(doc: PortfolioDoc) -> str:
    lines = [
        f"# {_md_text(doc.team_name) or doc.team_number} -- Engineering Portfolio",
        f"**Team {doc.team_number}** -- {_md_text(doc.season_label)}",
    ]
    if doc.subtitle:
        lines.append(f"_{_md_text(doc.subtitle)}_")
    lines.append("")

    for page in doc.pages:
        lines.append(f"## {_md_text(page.title)}")
        lines.append("")
        for block in page.blocks:
            lines.extend(_render_block_md(block))
            lines.append("")

    return "\n".join(lines).strip() + "\n"
