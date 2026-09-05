from __future__ import annotations

from pathlib import Path

from PIL import Image

from figureviewer.cli import parse_launch_args
from figureviewer.display_state import get_viewport_snapshot
from figureviewer.export_figures import resolve_export_titles
from figureviewer.figures import common_stems, list_figures, parse_panels, panels_from_directories
from figureviewer.metadata import load_metadata, save_metadata
from figureviewer.viewer_state import ViewerState


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(path)


def test_parse_launch_args_desktop() -> None:
    args = parse_launch_args(["--desktop"])
    assert args.desktop is True
    assert args.streamlit_args == []

    args = parse_launch_args(["-d", "--server.port", "8502"])
    assert args.desktop is True
    assert args.streamlit_args == ["--server.port", "8502"]

    args = parse_launch_args(["--server.headless", "true"])
    assert args.desktop is False
    assert args.streamlit_args == ["--server.headless", "true"]


def test_parse_panels_and_labels(tmp_path: Path) -> None:
    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    a.mkdir()
    b.mkdir()
    panels = parse_panels(f"old = {a}\n{b}\n")
    assert panels[0].label == "old"
    assert panels[1].label == "run_b"
    from_dirs = panels_from_directories([a, b])
    assert {p.label for p in from_dirs} == {"run_a", "run_b"}


def test_viewport_snapshot_position_and_stem(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _png(left / "trial_001.png")
    _png(left / "trial_002.png")
    _png(right / "trial_001.jpg")
    _png(right / "trial_002.png")

    state = ViewerState(
        panel_directories=[str(left), str(right)],
        sync_mode=True,
        match_by="position",
        current_index=1,
        columns_per_row=2,
    )
    snap = get_viewport_snapshot(state)
    assert snap is not None
    assert snap.current_label == "2"
    assert snap.figure_paths[0].name == "trial_002.png"
    assert snap.figure_paths[1].name == "trial_002.png"

    state["match_by"] = "filename stem"
    state["current_index"] = 0
    snap = get_viewport_snapshot(state)
    assert snap is not None
    stems = common_stems([list_figures(left), list_figures(right)])
    assert snap.current_label in stems
    assert snap.figure_paths[0].stem == snap.figure_paths[1].stem


def test_export_titles_and_metadata(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    panels = panels_from_directories([tmp_path / "a", tmp_path / "b"])
    titles = resolve_export_titles(panels, use_custom=True, custom_text="One\nTwo")
    assert titles == ["One", "Two"]
    path = save_metadata(tmp_path / "a", {"description": "hello"}, fmt="yaml")
    assert path.is_file()
    loaded = load_metadata(tmp_path / "a")
    assert loaded["description"] == "hello"


def test_desktop_main_window_snapshot_matches(tmp_path: Path) -> None:
    from PyQt6.QtWidgets import QApplication

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.main_window import MainWindow

    left = tmp_path / "left"
    right = tmp_path / "right"
    _png(left / "fig.png")
    _png(right / "fig.png")

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._state["panel_directories"] = [str(left), str(right)]
    window._refresh_view()
    snap = get_viewport_snapshot(window._state)
    assert snap is not None
    assert [p.name for p in snap.figure_paths if p] == ["fig.png", "fig.png"]
    window.close()
    del window
    assert app is not None


def test_export_panel_titles_not_shadowed() -> None:
    """Regression: widget named `_titles` shadowed `_titles()` and broke Save."""
    from PyQt6.QtWidgets import QApplication, QTextEdit

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.export_panel import ExportPanel
    from figureviewer.viewer_state import ViewerState

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    panel = ExportPanel(ViewerState())
    assert isinstance(panel._titles_edit, QTextEdit)
    assert callable(panel._resolve_titles)
    panel.deleteLater()
    assert app is not None


def test_unsync_global_nav_is_noop(tmp_path: Path) -> None:
    from PyQt6.QtWidgets import QApplication

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.main_window import MainWindow

    left = tmp_path / "left"
    right = tmp_path / "right"
    _png(left / "a.png")
    _png(left / "b.png")
    _png(right / "a.png")
    _png(right / "b.png")

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._state["panel_directories"] = [str(left), str(right)]
    window._state["sync_mode"] = False
    window._state["current_index"] = 0
    window._refresh_view()
    assert not window._nav.isEnabled()
    window._set_index(1)
    assert window._state["current_index"] == 0
    window.close()
    del window
    assert app is not None


def test_column_browser_keyboard_toggle(tmp_path: Path) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.column_browser import ColumnBrowser
    from figureviewer.viewer_state import ViewerState

    root = tmp_path / "root"
    child = root / "run_a"
    child.mkdir(parents=True)

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    state = ViewerState(browse_root=str(root), tree_stack=[str(root)])
    browser = ColumnBrowser(state)
    assert len(browser._column_lists) == 1
    column = browser._column_lists[0]
    assert column.count() == 1
    column.setCurrentRow(0)
    column.setFocus()

    space = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
    browser.eventFilter(column, space)
    assert str(child.resolve()) in state["panel_directories"]

    # refresh() rebuilds lists — use the live column for the second toggle
    column = browser._column_lists[0]
    column.setCurrentRow(0)
    browser.eventFilter(column, space)
    assert str(child.resolve()) not in state["panel_directories"]
    browser.deleteLater()
    assert app is not None


def test_viewport_cell_keeps_source_for_refit() -> None:
    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QApplication

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.viewport import _PanelCell

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    cell = _PanelCell()
    cell.resize(200, 150)
    image = QImage(40, 30, QImage.Format.Format_RGB32)
    image.fill(0x112233)
    cell.set_image(image, fill=True)
    assert cell._source is not None
    cell.refit()
    assert cell._image_label.pixmap() is not None
    assert not cell._image_label.pixmap().isNull()
    cell._ignore_zoom_until = 0.0
    cell.zoom_by(1.25)
    assert cell._zoom > 1.0
    cell.reset_zoom()
    assert abs(cell._zoom - 1.0) < 1e-3
    cell.deleteLater()
    assert app is not None


def test_viewport_prefetch_queues_uncached_paths(tmp_path: Path) -> None:
    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QApplication

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.viewport import MultiPanelViewport

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    vp = MultiPanelViewport()
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _png(a)
    _png(b)
    img = QImage(8, 8, QImage.Format.Format_RGB32)
    img.fill(0)
    vp._cache.put(a, img, pdf_dpi=200, trim=False)
    vp.prefetch_paths([a, b])
    assert a.resolve() not in {p.resolve() for p in vp._prefetch_queue}
    assert any(p.resolve() == b.resolve() for p in vp._prefetch_queue) or vp._cache.get(
        b, pdf_dpi=200, trim=False
    ) is not None or vp._prefetch_loader.isRunning()
    # DPI change clears cache + queues
    vp.set_display_options(display_mode="Fill panel", custom_width=700, pdf_dpi=300, trim=False)
    assert len(vp._cache) == 0
    assert vp._prefetch_queue == []
    vp.deleteLater()
    assert app is not None


def test_viewport_zoom_targets_focused_cell(tmp_path: Path) -> None:
    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QApplication

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.viewport import MultiPanelViewport
    from figureviewer.display_state import ViewportSnapshot
    from figureviewer.figures import panels_from_directories

    left = tmp_path / "left"
    right = tmp_path / "right"
    _png(left / "a.png")
    _png(right / "a.png")
    panels = panels_from_directories([left, right])

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    vp = MultiPanelViewport()
    vp.resize(640, 480)
    snap = ViewportSnapshot(
        panels=panels,
        figure_paths=[left / "a.png", right / "a.png"],
        current_label="1",
        columns_per_row=2,
        index=0,
        total=1,
    )
    # Seed cache so show_snapshot applies immediately
    img = QImage(32, 24, QImage.Format.Format_RGB32)
    img.fill(0x445566)
    for path in snap.figure_paths:
        assert path is not None
        vp._cache.put(path, img, pdf_dpi=200, trim=False)
    vp.show_snapshot(snap, sync_mode=True)
    assert len(vp._cells) == 2
    assert vp._cells[0]._source is not None
    assert vp._cells[1]._source is not None
    assert vp.focused_figure_path() is not None
    vp._on_cell_focus(vp._cells[1])
    for cell in vp._cells:
        cell._ignore_zoom_until = 0.0
    vp.zoom_by(1.5)
    assert vp._focused is vp._cells[1]
    assert vp._cells[1]._zoom == 1.5
    assert abs(vp._cells[0]._zoom - 1.0) < 1e-3
    vp.reset_zoom()
    assert abs(vp._cells[1]._zoom - 1.0) < 1e-3
    vp.deleteLater()
    assert app is not None


def test_viewer_shortcuts_empty_state() -> None:
    from figureviewer.desktop.shortcuts import empty_state_html, empty_state_message, shortcut_entries

    entries = shortcut_entries()
    assert any("Toggle focus" in desc for _, desc in entries)
    html = empty_state_html()
    assert "Keyboard shortcuts" in html
    assert "Select one or more directories" in empty_state_message()


def test_sticky_prefs_roundtrip(tmp_path: Path, monkeypatch) -> None:
    import figureviewer.settings as settings

    monkeypatch.setattr(settings, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "_CONFIG_FILE", tmp_path / "settings.json")
    out = tmp_path / "exports"
    out.mkdir()
    settings.save_sticky_prefs(
        display_mode="Natural size",
        pdf_dpi=250,
        custom_width=900,
        trim_whitespace=True,
        columns_per_row=3,
        export_output_dir=str(out),
        export_pdf_dpi=350,
    )
    prefs = settings.load_sticky_prefs()
    assert prefs["display_mode"] == "Natural size"
    assert prefs["pdf_dpi"] == 250
    assert prefs["custom_width"] == 900
    assert prefs["trim_whitespace"] is True
    assert prefs["columns_per_row"] == 3
    assert prefs["export_pdf_dpi"] == 350
    assert prefs["export_output_dir_user_set"] is True
    assert Path(prefs["export_output_dir"]) == out.resolve()
