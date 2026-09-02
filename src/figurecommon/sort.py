from __future__ import annotations

import re


def natural_key(s: str):
    """Sort file names in human order: fig2 before fig10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
