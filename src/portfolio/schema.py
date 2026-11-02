"""The portfolio document contract -- the security boundary of this feature.

The LLM never emits HTML. It emits one `PortfolioDoc`, validated by
pydantic before `render.py` ever sees it. Every field is a plain text
field, a number, or a list of those -- never a tag, an attribute, or a
URL -- so there is no path by which model output can become markup.
`render.py` HTML-escapes every text field it renders; this module's job is
to make sure there is nothing else for it to render.

`Block` is intentionally a single flat model with a `kind` discriminator
field, NOT a pydantic discriminated union (`Union[..., Field(discriminator=...)]`).
An earlier version used a real union, and every per-page structured-output
call to Gemini failed with `400 INVALID_ARGUMENT`: Gemini's structured-output
schema support does not include `oneOf`/`anyOf`/`discriminator` (only a
constrained OpenAPI subset -- plain objects, arrays, enums, no polymorphic
types). A flat model with one `kind` enum plus every kind's fields present
(unused ones left at their default) is the documented workaround and is
fully within that supported subset. `render.py` and `compose.py`'s prompt
are both written against this flat shape -- see their module docstrings.
See docs/adr/0004-portfolio-generation.md for the fuller writeup.

`images: list[int]` is a list of indices into the caller's ingested-image
inventory, not paths or URLs -- `render.py` resolves each index to an
embedded `data:` URI and silently drops any index outside that inventory.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

_MAX_BLOCKS_PER_PAGE = 12
_MAX_BULLETS = 12
_MAX_IMAGES_PER_GRID = 8
_MAX_ROWS_PER_TABLE = 30
_MAX_STATS_PER_ROW = 6
_MAX_CARDS_PER_COLUMNS = 4
_MAX_PAGES = 16

_SHORT = 160
_MEDIUM = 600
_LONG = 2000

BLOCK_KINDS = ("banner", "stat_row", "card", "columns", "figure_grid", "rubric_table")


class Stat(BaseModel):
    label: str = Field(max_length=60)
    value: str = Field(max_length=60)


class CardItem(BaseModel):
    """A single card's content -- used both as a `Columns` sub-item and as
    the fields a `Block` of `kind="card"` populates directly. Kept as its
    own plain (non-recursive) model so `Block.cards` is a uniform list of
    one concrete type, not a nested `Block`, which would reintroduce a
    recursive schema Gemini's structured output can't take either."""

    heading: str = Field(max_length=_SHORT)
    body: str = Field(default="", max_length=_LONG)
    bullets: list[str] = Field(default_factory=list, max_length=_MAX_BULLETS)

    @field_validator("bullets")
    @classmethod
    def _cap_bullet_length(cls, bullets: list[str]) -> list[str]:
        return [b[:_MEDIUM] for b in bullets]


class RubricRow(BaseModel):
    category: str = Field(max_length=40)
    goal: str = Field(max_length=_MEDIUM)
    result: str = Field(max_length=_MEDIUM)
    page: str = Field(default="", max_length=20)


class Block(BaseModel):
    kind: Literal[BLOCK_KINDS] = Field(
        description=(
            "Which visual element this is. Populate ONLY the field(s) listed for that kind below; "
            "leave every other field at its default (empty string/list). "
            "banner->text. stat_row->stats. card->heading,body,bullets. columns->cards. "
            "figure_grid->images,captions. rubric_table->rows."
        )
    )
    # banner
    text: str = Field(default="", max_length=_SHORT, description="kind=banner only: the banner's text.")
    # stat_row
    stats: list[Stat] = Field(
        default_factory=list, max_length=_MAX_STATS_PER_ROW, description="kind=stat_row only: a row of number tiles."
    )
    # card
    heading: str = Field(default="", max_length=_SHORT, description="kind=card only: the card's heading.")
    body: str = Field(default="", max_length=_LONG, description="kind=card only: the card's paragraph text, if any.")
    bullets: list[str] = Field(
        default_factory=list, max_length=_MAX_BULLETS, description="kind=card only: the card's bullet points, if any."
    )
    # columns
    cards: list[CardItem] = Field(
        default_factory=list, max_length=_MAX_CARDS_PER_COLUMNS, description="kind=columns only: 2-4 cards side by side."
    )
    # figure_grid
    images: list[Annotated[int, Field(ge=0)]] = Field(
        default_factory=list,
        max_length=_MAX_IMAGES_PER_GRID,
        description="kind=figure_grid only: indices into the AVAILABLE IMAGES list provided in the prompt.",
    )
    captions: list[str] = Field(
        default_factory=list,
        max_length=_MAX_IMAGES_PER_GRID,
        description="kind=figure_grid only: one caption per entry in images, same order.",
    )
    # rubric_table
    rows: list[RubricRow] = Field(
        default_factory=list,
        max_length=_MAX_ROWS_PER_TABLE,
        description="kind=rubric_table only: goal/result rows, optionally grouped by category.",
    )

    @field_validator("bullets")
    @classmethod
    def _cap_bullet_length(cls, bullets: list[str]) -> list[str]:
        return [b[:_MEDIUM] for b in bullets]

    @field_validator("captions")
    @classmethod
    def _cap_caption_length(cls, captions: list[str]) -> list[str]:
        return [c[:_SHORT] for c in captions]


def Banner(text: str) -> Block:
    return Block(kind="banner", text=text)


def StatRow(stats: list[Stat]) -> Block:
    return Block(kind="stat_row", stats=stats)


def Card(heading: str, body: str = "", bullets: "list[str] | None" = None) -> Block:
    return Block(kind="card", heading=heading, body=body, bullets=bullets or [])


def Columns(cards: list[CardItem]) -> Block:
    return Block(kind="columns", cards=cards)


def FigureGrid(images: list[int], captions: "list[str] | None" = None) -> Block:
    return Block(kind="figure_grid", images=images, captions=captions or [])


def RubricTable(rows: list[RubricRow]) -> Block:
    return Block(kind="rubric_table", rows=rows)


class PortfolioPage(BaseModel):
    title: str = Field(max_length=_SHORT)
    page_label: str = Field(default="", max_length=40)
    blocks: list[Block] = Field(max_length=_MAX_BLOCKS_PER_PAGE)


class PortfolioDoc(BaseModel):
    team_number: int = Field(ge=1, le=999999)
    team_name: str = Field(default="", max_length=_SHORT)
    season_label: str = Field(max_length=_SHORT)
    subtitle: str = Field(default="", max_length=_SHORT)
    accent: str = Field(default="#A81C1C", pattern=r"^#[0-9A-Fa-f]{6}$")
    pages: list[PortfolioPage] = Field(max_length=_MAX_PAGES)
