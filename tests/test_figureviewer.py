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
    assert args.mode is None
    assert args.root is None
    assert args.streamlit_args == []

    args = parse_launch_args(["-d", "--server.port", "8502"])
    assert args.desktop is True
    assert args.streamlit_args == ["--server.port", "8502"]

    args = parse_launch_args(["--server.headless", "true"])
    assert args.desktop is False
    assert args.streamlit_args == ["--server.headless", "true"]

    args = parse_launch_args(["--mode", "browse", "/tmp"])
    assert args.desktop is True
    assert args.mode == "browse"
    assert args.root == Path("/tmp")

    args = parse_launch_args(["--desktop", "--root", "/tmp"])
    assert args.desktop is True
    assert args.root == Path("/tmp")

    args = parse_launch_args(["some_streamlit_arg"])
    assert args.desktop is False
    assert args.root is None
    assert args.streamlit_args == ["some_streamlit_arg"]


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

    # Unsynced local keys must use resolved directory paths (desktop slider keys).
    state["sync_mode"] = False
    panels = panels_from_directories([left, right])
    key = f"local_idx_{panels[0].label}_{panels[0].directory.resolve()}"
    state[key] = 1
    snap = get_viewport_snapshot(state)
    assert snap is not None
    assert snap.figure_paths[0].name == "trial_002.png"


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


def test_figure_nav_shortcuts_are_window_scoped(tmp_path: Path) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLineEdit

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.main_window import MainWindow

    left = tmp_path / "left"
    _png(left / "a.png")
    _png(left / "b.png")

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._state["panel_directories"] = [str(left)]
    window._state["sync_mode"] = True
    window._refresh_view()
    assert window._figure_nav_shortcuts
    assert all(
        sc.context() == Qt.ShortcutContext.WindowShortcut for sc in window._figure_nav_shortcuts
    )
    assert all(sc.isEnabled() for sc in window._figure_nav_shortcuts)

    window._state["sync_mode"] = False
    window._sync_figure_nav_shortcuts()
    assert all(not sc.isEnabled() for sc in window._figure_nav_shortcuts)

    window._state["sync_mode"] = True
    window._sync_figure_nav_shortcuts()
    assert all(sc.isEnabled() for sc in window._figure_nav_shortcuts)
    edit = QLineEdit()
    assert MainWindow._is_text_entry(edit)

    window.close()
    del window
    assert app is not None


def test_directory_navigator_toggles_panel(tmp_path: Path) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.directory_navigator import DirectoryNavigator
    from figureviewer.viewer_state import ViewerState

    root = tmp_path / "root"
    child = root / "run_a"
    child.mkdir(parents=True)

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    state = ViewerState(browse_root=str(child), tree_stack=[str(child)])
    nav = DirectoryNavigator(state)
    # Opening on the child lists siblings under root (Gallery nearby pattern).
    nav.open_for(child)
    assert nav._nearby.count() >= 1
    found = False
    for i in range(nav._nearby.count()):
        item = nav._nearby.item(i)
        path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        if path.resolve() == child.resolve():
            nav._nearby.setCurrentRow(i)
            found = True
            break
    assert found
    nav._toggle_current()
    assert str(child.resolve()) in state["panel_directories"]
    nav._toggle_current()
    assert str(child.resolve()) not in state["panel_directories"]
    nav.close_picker(notify=False)
    nav.deleteLater()
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
    cell.set_zoom_level(1.25)
    assert cell._zoom > 1.0
    cell.set_zoom_level(1.0)
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


def test_viewport_zoom_applies_to_all_panels(tmp_path: Path) -> None:
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
    img = QImage(32, 24, QImage.Format.Format_RGB32)
    img.fill(0x445566)
    for path in snap.figure_paths:
        assert path is not None
        vp._cache.put(path, img, pdf_dpi=200, trim=False)
    vp.show_snapshot(snap, sync_mode=True)
    assert len(vp._cells) == 2
    assert vp.focused_figure_path() is not None
    vp._ignore_zoom_until = 0.0
    vp.zoom_by(1.5)
    assert abs(vp._zoom - 1.5) < 1e-3
    assert abs(vp._cells[0]._zoom - 1.5) < 1e-3
    assert abs(vp._cells[1]._zoom - 1.5) < 1e-3
    vp.reset_zoom()
    assert abs(vp._zoom - 1.0) < 1e-3
    assert abs(vp._cells[0]._zoom - 1.0) < 1e-3
    assert abs(vp._cells[1]._zoom - 1.0) < 1e-3
    vp.deleteLater()
    assert app is not None


def test_viewport_restores_keyboard_focus_after_snapshot(tmp_path: Path) -> None:
    """←/→ are viewport-scoped; flipping must re-attach focus after cells are rebuilt."""
    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QApplication

    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.viewport import MultiPanelViewport
    from figureviewer.display_state import ViewportSnapshot
    from figureviewer.figures import panels_from_directories

    left = tmp_path / "left"
    right = tmp_path / "right"
    _png(left / "a.png")
    _png(left / "b.png")
    _png(right / "a.png")
    _png(right / "b.png")
    panels = panels_from_directories([left, right])

    configure_qt_plugins()
    app = QApplication.instance() or QApplication([])
    vp = MultiPanelViewport()
    vp.show()
    vp.resize(640, 480)
    vp.activateWindow()
    app.processEvents()
    img = QImage(32, 24, QImage.Format.Format_RGB32)
    img.fill(0x445566)

    def _snap(index: int, name: str) -> ViewportSnapshot:
        paths = [left / name, right / name]
        for path in paths:
            vp._cache.put(path, img, pdf_dpi=200, trim=False)
        return ViewportSnapshot(
            panels=panels,
            figure_paths=paths,
            current_label=str(index + 1),
            columns_per_row=2,
            index=index,
            total=2,
        )

    vp.show_snapshot(_snap(0, "a.png"), sync_mode=True)
    app.processEvents()
    vp.focus_display()
    app.processEvents()

    vp.show_snapshot(_snap(1, "b.png"), sync_mode=True)
    app.processEvents()
    assert len(vp._cells) == 2
    assert all(abs(cell._zoom - 1.0) < 1e-3 for cell in vp._cells)
    # After nav, main window calls focus_display — same contract here
    vp.focus_display()
    app.processEvents()
    fw = QApplication.focusWidget()
    if fw is not None:
        # When the platform allows focus, it must land inside the viewport again
        assert vp.isAncestorOf(fw)

    vp.deleteLater()
    assert app is not None


def test_viewer_shortcuts_empty_state() -> None:
    from figureviewer.desktop.shortcuts import empty_state_html, empty_state_message, shortcut_entries

    entries = shortcut_entries()
    assert any("directory navigator" in desc.lower() for _, desc in entries)
    html = empty_state_html()
    assert "Keyboard shortcuts" in html
    assert "Directories" in empty_state_message() or "`" in empty_state_message()


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


def test_desktop_mode_prefs_roundtrip(tmp_path: Path, monkeypatch) -> None:
    import figureviewer.settings as settings

    monkeypatch.setattr(settings, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "_CONFIG_FILE", tmp_path / "settings.json")
    assert settings.load_desktop_mode() is None
    settings.save_desktop_mode("browse")
    assert settings.load_desktop_mode() == "browse"
    settings.save_desktop_mode("compare")
    assert settings.load_desktop_mode() == "compare"
    settings.save_desktop_mode("nope")
    assert settings.load_desktop_mode() == "compare"


def test_mode_controller_switches_compare_browse(tmp_path: Path, monkeypatch) -> None:
    import figureviewer.settings as settings
    from figuregallery.platform import configure_qt_plugins
    from figureviewer.desktop.mode_shell import ModeController
    from figureviewer.desktop.modes import AppMode

    # Native macOS menu bar can abort under headless/CI; keep Qt offscreen.
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(settings, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "_CONFIG_FILE", tmp_path / "settings.json")
    configure_qt_plugins()
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    controller = ModeController(app, initial_mode=AppMode.COMPARE)
    assert controller.mode is AppMode.COMPARE
    assert controller.window is not None
    assert "Compare" in controller.window.windowTitle()
    assert settings.load_desktop_mode() == "compare"

    controller.show(AppMode.BROWSE)
    app.processEvents()
    assert controller.mode is AppMode.BROWSE
    assert controller.window is not None
    assert "Browse" in controller.window.windowTitle()
    assert settings.load_desktop_mode() == "browse"

    # Mode menu / toolbar expose a single switch-to-other-mode action.
    mode_menu = next(
        (a.menu() for a in controller.window.menuBar().actions() if a.text() == "Mode"),
        None,
    )
    assert mode_menu is not None
    switch_labels = [a.text() for a in mode_menu.actions()]
    assert switch_labels == ["Compare"]

    controller.window.close()
    controller.window.deleteLater()
    app.processEvents()
