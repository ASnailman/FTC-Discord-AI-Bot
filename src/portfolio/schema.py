"""The portfolio document contract -- the security boundary of this feature.

The LLM never emits HTML. It emits one `PortfolioDoc`, a closed union of
block types defined here, validated by pydantic before `render.py` ever
sees it. Every block carries only plain text fields and integer image
indices -- never a tag, an attribute, or a URL -- so there is no path by
which model output can become markup. `render.py` HTML-escapes every text
field it renders; this module's job is to make sure there is nothing else
for it to render.

`images: list[int]` fields are indices into the caller's ingested-image
inventory, not paths or URLs -- `render.py` resolves each index to an
embedded `data:` URI and silently drops any index outside that inventory.
"""
from typing import Annotated, Literal, Union

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


class Banner(BaseModel):
    kind: Literal["banner"] = "banner"
    text: str = Field(max_length=_SHORT)


class Stat(BaseModel):
    label: str = Field(max_length=60)
    value: str = Field(max_length=60)


class StatRow(BaseModel):
    kind: Literal["stat_row"] = "stat_row"
    stats: list[Stat] = Field(max_length=_MAX_STATS_PER_ROW)


class Card(BaseModel):
    kind: Literal["card"] = "card"
    heading: str = Field(max_length=_SHORT)
    body: str = Field(default="", max_length=_LONG)
    bullets: list[str] = Field(default_factory=list, max_length=_MAX_BULLETS)

    @field_validator("bullets")
    @classmethod
    def _cap_bullet_length(cls, bullets: list[str]) -> list[str]:
        return [b[:_MEDIUM] for b in bullets]


class Columns(BaseModel):
    kind: Literal["columns"] = "columns"
    cards: list[Card] = Field(max_length=_MAX_CARDS_PER_COLUMNS)


class FigureGrid(BaseModel):
    kind: Literal["figure_grid"] = "figure_grid"
    images: list[Annotated[int, Field(ge=0)]] = Field(max_length=_MAX_IMAGES_PER_GRID)
    captions: list[str] = Field(default_factory=list, max_length=_MAX_IMAGES_PER_GRID)

    @field_validator("captions")
    @classmethod
    def _cap_caption_length(cls, captions: list[str]) -> list[str]:
        return [c[:_SHORT] for c in captions]


class RubricRow(BaseModel):
    category: str = Field(max_length=40)
    goal: str = Field(max_length=_MEDIUM)
    result: str = Field(max_length=_MEDIUM)
    page: str = Field(default="", max_length=20)


class RubricTable(BaseModel):
    kind: Literal["rubric_table"] = "rubric_table"
    rows: list[RubricRow] = Field(max_length=_MAX_ROWS_PER_TABLE)


Block = Annotated[
    Union[Banner, StatRow, Card, Columns, FigureGrid, RubricTable],
    Field(discriminator="kind"),
]


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
