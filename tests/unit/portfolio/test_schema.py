import pytest
from pydantic import ValidationError

from portfolio.schema import (
    Banner,
    Card,
    FigureGrid,
    PortfolioDoc,
    PortfolioPage,
    RubricRow,
    RubricTable,
)


def _doc(**overrides):
    base = dict(team_number=14496, team_name="Roboctopi", season_label="Decode (2025)", pages=[])
    base.update(overrides)
    return PortfolioDoc(**base)


def test_minimal_doc_is_valid():
    doc = _doc(pages=[PortfolioPage(title="Motivate", blocks=[Banner(text="Hello")])])
    assert doc.pages[0].blocks[0].kind == "banner"


def test_unknown_block_kind_is_rejected():
    with pytest.raises(ValidationError):
        PortfolioPage(title="X", blocks=[{"kind": "raw_html", "text": "<script>x</script>"}])


def test_over_long_banner_text_is_rejected():
    with pytest.raises(ValidationError):
        Banner(text="x" * 10_000)


def test_too_many_blocks_on_a_page_is_rejected():
    with pytest.raises(ValidationError):
        PortfolioPage(title="X", blocks=[Banner(text="hi") for _ in range(50)])


def test_too_many_pages_is_rejected():
    with pytest.raises(ValidationError):
        _doc(pages=[PortfolioPage(title="X", blocks=[]) for _ in range(100)])


def test_negative_image_index_is_rejected():
    with pytest.raises(ValidationError):
        FigureGrid(images=[-1])


def test_too_many_images_in_one_grid_is_rejected():
    with pytest.raises(ValidationError):
        FigureGrid(images=list(range(50)))


def test_invalid_accent_hex_is_rejected():
    with pytest.raises(ValidationError):
        _doc(accent="not-a-color")


def test_accent_hex_is_accepted():
    doc = _doc(accent="#112233")
    assert doc.accent == "#112233"


def test_card_bullets_are_length_capped_not_rejected():
    card = Card(heading="H", bullets=["x" * 5000])
    assert len(card.bullets[0]) <= 600


def test_rubric_row_requires_string_fields():
    row = RubricRow(category="Design", goal="Iterate", result="Done", page="7")
    table = RubricTable(rows=[row])
    assert table.rows[0].category == "Design"


def test_too_many_rubric_rows_is_rejected():
    row = RubricRow(category="c", goal="g", result="r")
    with pytest.raises(ValidationError):
        RubricTable(rows=[row] * 100)
