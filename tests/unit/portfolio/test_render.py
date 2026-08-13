"""The XSS suite for portfolio/render.py -- this is the security boundary
for the bot's first feature that emits HTML. Every payload below is
injected into every schema text field the LLM can populate; render_html
must come out inert in every case.

"Inert" here specifically means: no real `<script>`/`<iframe>`/`<object>`/
`<embed>` tag is ever formed. Escaping does NOT remove (and should not
remove) the literal characters "javascript:" or "onerror=" from *visible
page text* -- a team's own portfolio copy might legitimately mention
either -- so these tests assert the tags never come alive, plus (in
`test_escaped_payload_is_visible_as_literal_text_not_executed`) that the
dangerous characters are demonstrably transformed into entities rather
than merely absent by coincidence.
"""
import re

import pytest

from portfolio.render import PortfolioImage, RenderSecurityError, render_html, render_markdown
from portfolio.schema import (
    Banner,
    Card,
    Columns,
    FigureGrid,
    PortfolioDoc,
    PortfolioPage,
    RubricRow,
    RubricTable,
    Stat,
    StatRow,
)

PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "javascript:alert(1)",
    "<a href=\"javascript:alert(1)\">click</a>",
    "</style><script>alert(1)</script>",
    "<iframe src=\"javascript:alert(1)\"></iframe>",
    "<div onclick=\"alert(1)\">x</div>",
    "&lt;script&gt;alert(1)&lt;/script&gt;",  # already-encoded, must not double-decode into a tag
    "<object data=\"data:text/html,<script>alert(1)</script>\"></object>",
    "'-alert(1)-'",
    "\"><script>alert(1)</script>",
]


def _assert_no_live_tags(html_out: str) -> None:
    """This renderer never intentionally emits script/iframe/object/embed,
    so their absence -- even as case-insensitive substrings -- cannot be a
    false positive against our own trusted markup, only a real escaping
    failure."""
    lowered = html_out.lower()
    assert "<script" not in lowered
    assert "<iframe" not in lowered
    assert "<object" not in lowered
    assert "<embed" not in lowered


def _doc_with_banner(text: str) -> PortfolioDoc:
    return PortfolioDoc(
        team_number=14496,
        team_name=text[:160],
        season_label="Decode (2025)",
        subtitle=text[:160],
        pages=[PortfolioPage(title=text[:160], page_label=text[:40], blocks=[Banner(text=text[:160])])],
    )


@pytest.mark.parametrize("payload", PAYLOADS)
def test_banner_text_payload_is_neutralized(payload):
    html_out = render_html(_doc_with_banner(payload))
    _assert_no_live_tags(html_out)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_card_fields_payload_is_neutralized(payload):
    doc = PortfolioDoc(
        team_number=1,
        season_label="S",
        pages=[
            PortfolioPage(
                title="Design",
                blocks=[Card(heading=payload, body=payload, bullets=[payload])],
            )
        ],
    )
    html_out = render_html(doc)
    _assert_no_live_tags(html_out)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_columns_and_stat_row_payload_is_neutralized(payload):
    doc = PortfolioDoc(
        team_number=1,
        season_label="S",
        pages=[
            PortfolioPage(
                title="T",
                blocks=[
                    Columns(cards=[Card(heading=payload, bullets=[payload])]),
                    StatRow(stats=[Stat(label=payload[:60], value=payload[:60])]),
                ],
            )
        ],
    )
    html_out = render_html(doc)
    _assert_no_live_tags(html_out)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_rubric_table_payload_is_neutralized(payload):
    doc = PortfolioDoc(
        team_number=1,
        season_label="S",
        pages=[
            PortfolioPage(
                title="T",
                blocks=[RubricTable(rows=[RubricRow(category=payload[:40], goal=payload, result=payload, page="7")])],
            )
        ],
    )
    html_out = render_html(doc)
    _assert_no_live_tags(html_out)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_figure_caption_payload_is_neutralized(payload):
    doc = PortfolioDoc(
        team_number=1,
        season_label="S",
        pages=[
            PortfolioPage(
                title="T",
                blocks=[FigureGrid(images=[0], captions=[payload])],
            )
        ],
    )
    images = [PortfolioImage(data_uri="data:image/png;base64,AAAA", alt_text=payload)]
    html_out = render_html(doc, images)
    _assert_no_live_tags(html_out)
    # The only <img> tag present must be ours, with our trusted data URI --
    # never a src= derived from the (attacker-controlled) caption/alt text,
    # since PortfolioImage.data_uri is constructed by our own ingest code,
    # not copied from model output.
    assert html_out.count("<img") == 1
    assert 'src="data:image/png;base64,AAAA"' in html_out
    assert 'src="javascript' not in html_out.lower()


def test_escaped_payload_is_visible_as_literal_text_not_executed():
    """Escaping must transform, not silently drop, dangerous characters --
    proving the payload is neutralized by transformation, not by
    coincidentally not matching a blocklist substring."""
    html_out = render_html(_doc_with_banner("<script>alert(1)</script>"))
    assert "&lt;script&gt;" in html_out


def test_csp_meta_is_present():
    html_out = render_html(_doc_with_banner("hello"))
    assert "Content-Security-Policy" in html_out
    assert "default-src 'none'" in html_out


def test_forbidden_content_scan_raises_if_bypassed(monkeypatch):
    import portfolio.render as render_mod

    monkeypatch.setattr(render_mod, "_inline", lambda text: "<script>alert(1)</script>")
    with pytest.raises(RenderSecurityError):
        render_html(_doc_with_banner("hello"))


def test_out_of_range_image_index_is_dropped_not_rendered():
    doc = PortfolioDoc(
        team_number=1,
        season_label="S",
        pages=[PortfolioPage(title="T", blocks=[FigureGrid(images=[0, 5])])],
    )
    images = [PortfolioImage(data_uri="data:image/png;base64,AAAA")]
    html_out = render_html(doc, images)
    assert html_out.count("<img") == 1


def test_bold_italic_code_formatting_applied_safely():
    doc = _doc_with_banner("hello")
    doc.pages[0].blocks[0] = Card(heading="H", body="**bold** *italic* `code`")
    html_out = render_html(doc)
    assert "<strong>bold</strong>" in html_out
    assert "<em>italic</em>" in html_out
    assert "<code>code</code>" in html_out


def test_markdown_output_strips_literal_html_tags():
    doc = _doc_with_banner("hello")
    doc.pages[0].blocks[0] = Card(heading="<img src=x onerror=alert(1)>", body="plain text")
    md = render_markdown(doc)
    assert "<script" not in md.lower()
    assert "<img" not in md.lower()
    assert "plain text" in md


def test_markdown_output_covers_every_block_type():
    doc = PortfolioDoc(
        team_number=14496,
        team_name="Roboctopi",
        season_label="Decode (2025)",
        pages=[
            PortfolioPage(
                title="Overview",
                blocks=[
                    StatRow(stats=[Stat(label="Sponsors", value="4")]),
                    Card(heading="Goals", body="Grow the team.", bullets=["Recruit 2 members", "Raise $5000"]),
                    Columns(cards=[Card(heading="Design", bullets=["Iterate in CAD"])]),
                    FigureGrid(images=[0], captions=["Intake mechanism"]),
                    RubricTable(rows=[RubricRow(category="Motivate", goal="Recruit", result="Recruited 2", page="2")]),
                ],
            )
        ],
    )
    md = render_markdown(doc)
    assert "**4** Sponsors" in md
    assert "#### Goals" in md
    assert "- Recruit 2 members" in md
    assert "#### Design" in md
    assert "_Image 0_ -- Intake mechanism" in md
    assert "| Motivate | Recruit | Recruited 2 | 2 |" in md


def test_empty_figure_grid_after_dropping_out_of_range_indices_renders_nothing():
    doc = PortfolioDoc(
        team_number=1,
        season_label="S",
        pages=[PortfolioPage(title="T", blocks=[FigureGrid(images=[5])])],
    )
    html_out = render_html(doc, images=[])
    assert '<div class="figure-grid">' not in html_out
    assert "<img" not in html_out


def test_html_is_well_formed_page_break_structure():
    doc = _doc_with_banner("hello")
    html_out = render_html(doc)
    assert html_out.count('<section class="page">') == len(doc.pages)
    assert re.search(r"<!doctype html>", html_out, re.IGNORECASE)
