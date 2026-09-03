from __future__ import annotations

import html
import sys

_fixed_font_family_cache: str | None = None


def fixed_font_family() -> str:
    """System fixed-pitch font for RichText (Qt has no CSS generic families)."""
    global _fixed_font_family_cache
    if _fixed_font_family_cache is None:
        from PyQt6.QtGui import QFontDatabase

        _fixed_font_family_cache = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        ).family()
    return _fixed_font_family_cache


def _modifier_label() -> str:
    return "Cmd" if sys.platform == "darwin" else "Ctrl"


def shortcut_entries() -> list[tuple[str, str]]:
    """Keybinding list as (key, description) pairs."""
    mod = _modifier_label()
    return [
        (f"{mod}+O", "Open directory"),
        (f"{mod}+R", "Rescan"),
        (f"{mod}+E", "Open enclosing folder"),
        (f"{mod}+S", "Export PDF"),
        ("← / →", "Previous / next figure"),
        (f"{mod}+← / {mod}+→", "First / last figure"),
        ("Space", "Next figure"),
        ("H", "This folder only (toggle)"),
    ]


def shortcuts_help_lines() -> list[str]:
    """Plain-text lines for console / status bar (fixed-width key column)."""
    width = max(len(key) for key, _ in shortcut_entries())
    return [f"{key.ljust(width)}  {desc}" for key, desc in shortcut_entries()]


def shortcuts_help_text(*, for_console: bool = False) -> str:
    lines = shortcuts_help_lines()
    if for_console:
        header = "Figure Gallery — keyboard shortcuts"
        body = "\n".join(f"  {line}" for line in lines)
        return f"{header}\n{body}"
    return "Keyboard shortcuts:\n" + "\n".join(lines)


def shortcuts_help_html() -> str:
    family = html.escape(fixed_font_family())
    rows = []
    for key, desc in shortcut_entries():
        key_html = html.escape(key)
        desc_html = html.escape(desc)
        rows.append(
            "<tr>"
            f'<td align="right" style="padding-right: 16px; font-family: &quot;{family}&quot;;">'
            f"{key_html}</td>"
            f'<td align="left">{desc_html}</td>'
            "</tr>"
        )
    table = (
        '<table cellspacing="0" cellpadding="2" '
        'style="margin-left: auto; margin-right: auto;">'
        + "".join(rows)
        + "</table>"
    )
    return table


def empty_state_html() -> str:
    return (
        '<div align="center">'
        "<p>Open a directory to scan for figures.</p>"
        "<p><b>Keyboard shortcuts</b></p>"
        f"{shortcuts_help_html()}"
        "</div>"
    )


def empty_state_message() -> str:
    """Plain-text fallback (console / tests)."""
    return (
        "Open a directory to scan for figures.\n\n"
        + shortcuts_help_text(for_console=False)
    )
