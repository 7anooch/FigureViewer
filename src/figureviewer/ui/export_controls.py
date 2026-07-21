from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import streamlit as st

from figureviewer.browsing import (
    folder_dialog_available,
    folder_dialog_hint,
    get_panel_configs,
    pick_directory_dialog,
    resolve_path,
)
from figureviewer.display_state import (
    export_index_labels,
    get_viewport_snapshot,
    iter_viewport_snapshots,
)
from figureviewer.export_figures import (
    export_viewport_snapshot,
    resolve_export_titles,
    suggest_export_output_dir,
)
from figureviewer.figures import PanelConfig


def _apply_pending_export_dir_pick() -> None:
    picked = st.session_state.pop("_pending_export_dir_pick", None)
    if not picked:
        return
    st.session_state.export_output_dir_input = picked
    st.session_state.export_output_dir = picked
    st.session_state.export_output_dir_user_set = True


def _sync_export_dir_default() -> None:
    panels = get_panel_configs()
    if not panels:
        return
    suggested = str(suggest_export_output_dir(panels))
    if not st.session_state.get("export_output_dir_user_set"):
        st.session_state.export_output_dir = suggested
        st.session_state.export_output_dir_input = suggested


def _on_browse_export_dir() -> None:
    initial = st.session_state.get("export_output_dir_input") or st.session_state.get(
        "export_output_dir"
    )
    picked = pick_directory_dialog(initial)
    if picked:
        st.session_state._pending_export_dir_pick = picked


def _resolve_output_dir() -> Optional[Path]:
    output_dir_str = st.session_state.get("export_output_dir_input", "").strip()
    choose_each_time = st.session_state.get("export_choose_dir_on_save", False)
    if choose_each_time or not output_dir_str:
        initial = output_dir_str or st.session_state.get("export_output_dir")
        picked = pick_directory_dialog(initial)
        if not picked:
            st.session_state._export_flash = "Export cancelled (no output folder chosen)."
            return None
        output_dir_str = picked
        st.session_state.export_output_dir_input = picked
        st.session_state.export_output_dir = picked
        st.session_state.export_output_dir_user_set = True

    try:
        output_dir = resolve_path(output_dir_str)
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        st.session_state._export_flash = f"Invalid output directory: {exc}"
        return None
    return output_dir


def _resolve_titles(panels: List[PanelConfig]) -> Optional[List[str]]:
    try:
        return resolve_export_titles(
            panels,
            use_custom=st.session_state.get("export_use_custom_titles", False),
            custom_text=st.session_state.get("export_custom_titles_text", ""),
        )
    except ValueError as exc:
        st.session_state._export_flash = str(exc)
        return None


def _export_min_panel_width() -> int:
    return int(st.session_state.get("export_min_panel_width", 1200))


def _export_pdf_dpi() -> int:
    return int(st.session_state.get("export_pdf_dpi", 300))


def _export_preserve_native() -> bool:
    return bool(st.session_state.get("export_preserve_native", True))


def _on_save_figure() -> None:
    snapshot = get_viewport_snapshot(st.session_state)
    if snapshot is None:
        st.session_state._export_flash = "No figures are available to export."
        return

    output_dir = _resolve_output_dir()
    if output_dir is None:
        return

    titles = _resolve_titles(snapshot.panels)
    if titles is None:
        return

    try:
        result = export_viewport_snapshot(
            snapshot,
            titles=titles,
            output_dir=output_dir,
            pdf_dpi=_export_pdf_dpi(),
            cell_width=_export_min_panel_width(),
            trim_whitespace_margins=st.session_state.get("trim_whitespace", False),
            preserve_native=_export_preserve_native(),
        )
    except Exception as exc:
        st.session_state._export_flash = f"Export failed: {exc}"
        return

    st.session_state.export_output_dir = str(output_dir)
    st.session_state.export_output_dir_user_set = True
    st.session_state._export_flash = (
        f"Saved `{result.path.name}` ({result.panels_exported} panel"
        f"{'s' if result.panels_exported != 1 else ''}) to `{output_dir}`."
    )


def _on_request_batch_save() -> None:
    labels = export_index_labels(st.session_state)
    if not labels:
        st.session_state._export_flash = "No figures are available to export."
        return

    output_dir = _resolve_output_dir()
    if output_dir is None:
        return

    snapshot = get_viewport_snapshot(st.session_state, index=0)
    if snapshot is None:
        st.session_state._export_flash = "No figures are available to export."
        return

    titles = _resolve_titles(snapshot.panels)
    if titles is None:
        return

    st.session_state._pending_batch_export = {
        "output_dir": str(output_dir),
        "titles": titles,
        "pdf_dpi": _export_pdf_dpi(),
        "cell_width": _export_min_panel_width(),
        "trim": st.session_state.get("trim_whitespace", False),
        "preserve_native": _export_preserve_native(),
        "count": len(labels),
    }


def _run_pending_batch_export() -> None:
    pending = st.session_state.pop("_pending_batch_export", None)
    if not pending:
        return

    count = pending["count"]
    progress = st.progress(0, text=f"Exporting 0 / {count}…")
    snapshots = list(iter_viewport_snapshots(st.session_state))
    results = []
    errors: List[str] = []
    first_path = None
    saved = 0
    failed = 0
    output_dir = Path(pending["output_dir"])

    from datetime import datetime
    from figureviewer.export_figures import _safe_filename

    batch_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i, snapshot in enumerate(snapshots):
        progress.progress(
            (i) / max(count, 1),
            text=f"Exporting {i + 1} / {count}: {snapshot.current_label}",
        )
        filename = (
            f"{snapshot.index + 1:04d}_{_safe_filename(snapshot.current_label)}"
            f"_{batch_stamp}.png"
        )
        try:
            result = export_viewport_snapshot(
                snapshot,
                titles=pending["titles"],
                output_dir=output_dir,
                pdf_dpi=pending["pdf_dpi"],
                cell_width=pending["cell_width"],
                trim_whitespace_margins=pending["trim"],
                preserve_native=pending.get("preserve_native", True),
                filename=filename,
            )
        except Exception as exc:
            failed += 1
            errors.append(f"{snapshot.current_label}: {exc}")
            continue
        saved += 1
        if first_path is None:
            first_path = result.path
        results.append(result)

    progress.progress(1.0, text=f"Exported {saved} / {count}")

    st.session_state.export_output_dir = str(output_dir)
    st.session_state.export_output_dir_user_set = True
    if saved and not failed:
        st.session_state._export_flash = (
            f"Saved {saved} figure{'s' if saved != 1 else ''} to `{output_dir}`."
        )
    elif saved and failed:
        st.session_state._export_flash = (
            f"Saved {saved} of {count} figures to `{output_dir}` "
            f"({failed} failed)."
        )
    else:
        detail = "; ".join(errors[:3]) if errors else "unknown error"
        st.session_state._export_flash = f"Batch export failed: {detail}"


def render_export_controls() -> None:
    _apply_pending_export_dir_pick()
    _sync_export_dir_default()
    _run_pending_batch_export()

    flash = st.session_state.pop("_export_flash", None)
    if flash:
        if flash.startswith("Saved"):
            st.success(flash)
        else:
            st.warning(flash)

    st.header("Export")
    st.caption("Save the current multi-panel view as one PNG image.")

    path_col, browse_col = st.columns([5, 1])
    with path_col:
        st.text_input(
            "Output directory",
            key="export_output_dir_input",
            help="Defaults to the common parent of the selected panel folders.",
        )
    with browse_col:
        st.button(
            "Browse…",
            key="export_output_dir_dialog",
            use_container_width=True,
            disabled=not folder_dialog_available(),
            help=folder_dialog_hint(),
            on_click=_on_browse_export_dir,
        )

    st.checkbox(
        "Choose output folder on each save",
        key="export_choose_dir_on_save",
        help="When on, opens a folder picker before saving (first save always prompts if no folder is set).",
    )

    st.checkbox("Use custom titles", key="export_use_custom_titles")
    if st.session_state.get("export_use_custom_titles"):
        panels = get_panel_configs()
        line_hint = f"One title per line ({len(panels)} line{'s' if len(panels) != 1 else ''})."
        st.text_area(
            "Export titles",
            key="export_custom_titles_text",
            height=80,
            help=line_hint,
            placeholder=line_hint,
        )

    st.slider(
        "Export PDF / SVG DPI",
        min_value=150,
        max_value=600,
        value=300,
        step=25,
        key="export_pdf_dpi",
        help="Rasterization density for PDF/SVG sources on export (independent of Display DPI).",
    )
    st.checkbox(
        "Preserve native resolution",
        value=True,
        key="export_preserve_native",
        help=(
            "Never downscale panels. Panel width becomes max(native width, min width below). "
            "Turn off to force a fixed smaller panel width."
        ),
    )
    st.slider(
        "Min panel width (px)",
        min_value=400,
        max_value=4000,
        value=1200,
        step=50,
        key="export_min_panel_width",
        help=(
            "Lower bound for each panel’s width in the exported PNG. "
            "With Preserve native resolution on, wider sources keep their full width."
        ),
    )

    n_available = len(export_index_labels(st.session_state))
    st.button(
        "Save figure",
        key="export_save_figure",
        type="primary",
        use_container_width=True,
        on_click=_on_save_figure,
    )
    st.button(
        f"Save all figures ({n_available})",
        key="export_save_all_figures",
        use_container_width=True,
        disabled=n_available == 0,
        help=(
            "Export every synchronized index (by position or filename stem), "
            "using the same layout, titles, and trim settings as Save figure."
        ),
        on_click=_on_request_batch_save,
    )
