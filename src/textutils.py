"""Small formatting helpers shared by processor.py and stats.py."""


def clean_value(value):
    """Replace None with the literal 'N/A' string; pass everything else through."""
    return value if value is not None else "N/A"


def fmt(value, nd: int = 1) -> str:
    """Format a possibly-None numeric value with `nd` decimals, else 'N/A'.

    FTCScout returns null (not 0) for OPR/rank fields on events with no
    played matches, and a bare f"{value:.1f}" raises TypeError on None.
    """
    if value is None:
        return "N/A"
    return f"{value:.{nd}f}"
