from __future__ import annotations

import sys


def shortcuts_help_lines() -> list[str]:
    """Human-readable keybinding list for launch banner / empty state."""
    mod = "Cmd" if sys.platform == "darwin" else "Ctrl"
    return [
        f"{mod}+O          Open directory",
        f"{mod}+R          Rescan",
        f"{mod}+E          Reveal in Finder",
        "← / →         Previous / next figure",
        f"{mod}+← / {mod}+→  First / last figure",
        "Space         Next figure",
        "H             This folder only (toggle)",
    ]


def shortcuts_help_text(*, for_console: bool = False) -> str:
    lines = shortcuts_help_lines()
    if for_console:
        header = "Figure Gallery — keyboard shortcuts"
        body = "\n".join(f"  {line}" for line in lines)
        return f"{header}\n{body}"
    return "Keyboard shortcuts:\n" + "\n".join(lines)


def empty_state_message() -> str:
    return (
        "Open a directory to scan for figures.\n\n"
        + shortcuts_help_text(for_console=False)
    )
