"""Design tokens and CSS for the generated portfolio.

Modeled on the reference world-championship portfolio (Team 14496,
"Roboctopi", 1st Place Think Award): a near-black cover with diagonal
accent bands, print-paginated content pages with an oversized flush-left
title and a hairline rule, full-bleed accent banners as section dividers,
dark cards for body content, and a faint tiled watermark. See
docs/portfolio.md for the page-type-by-page-type mapping back to the
reference.

This is a print document (the whole point is a judge-readable, Ctrl+P-able
page), so it deliberately commits to one light "paper" look rather than
being reactive to the viewer's OS theme.
"""
import re

ACCENT_CHOICES = {
    "red": "#A81C1C",
    "blue": "#1C4FA8",
    "green": "#1C7A3E",
    "purple": "#5B2C9E",
    "orange": "#C25A0E",
    "teal": "#127A76",
}
DEFAULT_ACCENT = ACCENT_CHOICES["red"]

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def resolve_accent(value: "str | None") -> str:
    """Never accepts free text -- a Discord command choice value (a key in
    ACCENT_CHOICES) or an already-validated `#rrggbb` string, else the
    default. This is the only place a color reaches the page; there is no
    path from arbitrary user text into CSS."""
    if not value:
        return DEFAULT_ACCENT
    if value in ACCENT_CHOICES:
        return ACCENT_CHOICES[value]
    if _HEX_RE.match(value):
        return value
    return DEFAULT_ACCENT


def build_css(accent: str) -> str:
    accent = accent if _HEX_RE.match(accent or "") else DEFAULT_ACCENT
    return f"""
:root {{
  --accent: {accent};
  --ink: #1a1a1a;
  --card: #4d4d4d;
  --card-ink: #ffffff;
  --page-bg: #ffffff;
  --rule: #c9c9c9;
  --cover-bg: #111111;
}}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0;
  padding: 0;
  background: var(--page-bg);
  color: var(--ink);
  font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
}}
img {{ max-width: 100%; display: block; }}
.page {{
  position: relative;
  width: 8.5in;
  min-height: 11in;
  margin: 0 auto;
  padding: 0.5in 0.6in;
  background: var(--page-bg);
  overflow: hidden;
  page-break-after: always;
}}
@media print {{
  @page {{ size: 8.5in 11in; margin: 0; }}
  .page {{ margin: 0; }}
}}
.watermark {{
  position: absolute;
  inset: 0;
  z-index: 0;
  opacity: 0.05;
  overflow: hidden;
  pointer-events: none;
}}
.page-body {{ position: relative; z-index: 1; }}
.page-header {{
  display: flex;
  align-items: baseline;
  gap: 0.4in;
  margin-bottom: 0.25in;
}}
.page-header h1 {{
  font-size: 2.4rem;
  font-weight: 900;
  margin: 0;
  white-space: nowrap;
  color: var(--ink);
}}
.page-header .rule {{
  flex: 1;
  border-top: 2px solid var(--rule);
}}
.page-header .page-label {{
  font-weight: 700;
  font-size: 0.85rem;
  letter-spacing: 0.05em;
  white-space: nowrap;
}}
.banner {{
  background: var(--accent);
  color: #fff;
  font-weight: 700;
  text-align: center;
  padding: 0.18in 0.2in;
  margin: 0.2in 0;
  border-radius: 4px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.25);
}}
.card {{
  background: var(--card);
  color: var(--card-ink);
  border-radius: 6px;
  padding: 0.22in;
  margin: 0.15in 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}}
.card h3 {{ margin: 0 0 0.1in 0; font-weight: 800; }}
.card ul {{ margin: 0.1in 0 0 0.2in; padding: 0; }}
.card li {{ margin-bottom: 0.06in; }}
.columns {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(2.4in, 1fr));
  gap: 0.15in;
  margin: 0.15in 0;
}}
.stat-row {{
  display: flex;
  gap: 0.2in;
  flex-wrap: wrap;
  margin: 0.15in 0;
}}
.stat {{
  flex: 1;
  min-width: 1.4in;
  text-align: center;
  background: #efefef;
  border-radius: 6px;
  padding: 0.15in;
}}
.stat .value {{ font-size: 1.4rem; font-weight: 900; color: var(--accent); }}
.stat .label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }}
.figure-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(2in, 1fr));
  gap: 0.15in;
  margin: 0.15in 0;
}}
.figure {{ text-align: center; }}
.figure .caption {{
  background: #333;
  color: #fff;
  font-size: 0.75rem;
  padding: 0.05in 0.08in;
  border-radius: 0 0 4px 4px;
}}
.figure img {{ border-radius: 4px 4px 0 0; }}
table.rubric {{
  width: 100%;
  border-collapse: collapse;
  margin: 0.15in 0;
  font-size: 0.85rem;
}}
table.rubric th, table.rubric td {{
  border: 1px solid var(--rule);
  padding: 0.08in;
  text-align: left;
  vertical-align: top;
}}
table.rubric th {{ background: var(--accent); color: #fff; }}
table.rubric tr.category td {{
  background: #eee;
  font-weight: 800;
}}
.cover {{
  width: 8.5in;
  min-height: 11in;
  margin: 0 auto;
  background: var(--cover-bg);
  color: #fff;
  position: relative;
  overflow: hidden;
  page-break-after: always;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 0.6in;
}}
.cover .band-a, .cover .band-b {{
  position: absolute;
  inset: -10% -10%;
  z-index: 0;
}}
.cover .band-a {{ background: var(--accent); opacity: 0.35; clip-path: polygon(0 20%, 100% 0, 100% 35%, 0 55%); }}
.cover .band-b {{ background: #333; clip-path: polygon(0 60%, 100% 45%, 100% 100%, 0 100%); }}
.cover .content {{ position: relative; z-index: 1; }}
.cover .team-number {{ font-size: 3.2rem; font-weight: 900; letter-spacing: 0.05em; }}
.cover .team-name {{ font-size: 1.6rem; font-weight: 700; margin-top: 0.1in; }}
.cover .subtitle {{ font-size: 1.1rem; margin-top: 0.3in; opacity: 0.85; }}
.cover .season {{
  margin-top: 0.5in;
  font-size: 0.85rem;
  padding: 0.08in 0.2in;
  border: 1px solid rgba(255,255,255,0.4);
  border-radius: 999px;
}}
.footer-bar {{
  position: absolute;
  left: 0; right: 0; bottom: 0;
  height: 0.18in;
  background: var(--accent);
}}
""".strip()


def watermark_svg(team_number: int) -> str:
    """A tiled inline SVG pattern -- no external asset, no network fetch,
    and `team_number` is already validated as an int by schema.py before it
    ever reaches here, so there is no injection surface in this string."""
    label = str(int(team_number))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">'
        f'<defs><pattern id="wm" width="160" height="120" patternTransform="rotate(-20)" '
        f'patternUnits="userSpaceOnUse">'
        f'<text x="0" y="60" font-size="28" font-weight="900" fill="#000">{label}</text>'
        f"</pattern></defs>"
        f'<rect width="100%" height="100%" fill="url(#wm)" /></svg>'
    )
