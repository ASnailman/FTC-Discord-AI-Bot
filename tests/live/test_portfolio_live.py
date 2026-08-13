"""End-to-end /portfolio generation against the real Gemini model: the
brief call, the per-page structured-output calls, and rendering. Asserts
the HTML is well-formed and stays under the size cap -- this is the one
place that actually exercises `with_structured_output(PortfolioPage)`
against the real API rather than a FakeLLM, since pydantic's discriminated
union schema for `Block` is not something the offline suite can verify
Gemini actually honors.
"""
import pytest

import config
from portfolio.compose import compose
from portfolio.extract import ExtractedText
from portfolio.render import render_html, render_markdown


@pytest.mark.live
def test_portfolio_generation_end_to_end_produces_valid_html():
    texts = [
        ExtractedText(
            filename="notes.md",
            text=(
                "We raised $8000 from 4 sponsors and recruited 2 new members. Our robot uses a "
                "bi-directional arm with sample and specimen capabilities. We implemented "
                "physics-based motor control with sensor fusion between odometry and IMU."
            ),
        )
    ]

    doc, images = compose(
        team_number=14496,
        season_label="Decode (2025)",
        instructions="Keep it concise.",
        texts=texts,
    )

    assert doc.pages
    html_doc = render_html(doc, images)
    assert html_doc.startswith("<!doctype html>")
    assert "Content-Security-Policy" in html_doc
    assert len(html_doc.encode("utf-8")) <= config.PORTFOLIO_MAX_OUTPUT_MB * 1024 * 1024

    markdown_doc = render_markdown(doc)
    assert markdown_doc.strip()


@pytest.mark.live
def test_portfolio_generation_with_no_uploaded_text_still_produces_something():
    doc, images = compose(team_number=1, season_label="Decode (2025)")
    assert doc.pages
    render_html(doc, images)
