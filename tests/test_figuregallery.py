from __future__ import annotations

from pathlib import Path

from figurecommon.scan import ScanOptions, walk_figures
from figuregallery.directory_tree import (
    FilterNodeKind,
    build_directory_tree,
    build_filter_display_tree,
    collect_exclusions,
    filter_by_directory_exclusions,
    maximal_exclusions,
)
from figuregallery.grouping import group_refs, remap_selection
from figuregallery.index import build_scan_index
from figuregallery.models import Category, FigureRef, GroupMode, SortMode
from figuregallery.playlist import build_playlist, filter_by_path_prefix


def _ref(root: Path, rel: str) -> FigureRef:
    path = root / rel
    p = Path(rel)
    return FigureRef(
        absolute_path=path,
        relative_path=p,
        filename=p.name,
        stem=p.stem,
    )


def test_walk_figures_skips_hidden_and_pycache(tmp_path: Path) -> None:
    (tmp_path / "visible.png").write_bytes(b"x")
    (tmp_path / ".hidden.png").write_bytes(b"x")
    hidden_dir = tmp_path / ".git"
    hidden_dir.mkdir()
    (hidden_dir / "skip.png").write_bytes(b"x")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "skip.png").write_bytes(b"x")

    found = list(walk_figures(tmp_path))
    assert len(found) == 1
    assert found[0].name == "visible.png"


def test_group_by_stem_and_filename(tmp_path: Path) -> None:
    refs = [
        _ref(tmp_path, "run_a/plot.png"),
        _ref(tmp_path, "run_b/plot.png"),
        _ref(tmp_path, "run_a/plot.pdf"),
    ]
    stem_groups = group_refs(refs, GroupMode.STEM)
    assert set(stem_groups) == {"plot"}
    assert len(stem_groups["plot"].refs) == 3
    assert stem_groups["plot"].pdf_count == 1
    assert stem_groups["plot"].is_selectable

    name_groups = group_refs(refs, GroupMode.FILENAME)
    assert set(name_groups) == {"plot.png", "plot.pdf"}
    assert name_groups["plot.pdf"].is_selectable
    assert name_groups["plot.png"].is_selectable


def test_remap_selection_stem_to_filename(tmp_path: Path) -> None:
    refs = [
        _ref(tmp_path, "a/plot.png"),
        _ref(tmp_path, "b/plot.pdf"),
    ]
    from figuregallery.models import ScanIndex
    import time

    index = ScanIndex(root=tmp_path, refs=refs, scanned_at=time.time())
    out = remap_selection({"plot"}, GroupMode.STEM, GroupMode.FILENAME, index)
    assert out == {"plot.png", "plot.pdf"}


def test_playlist_sort_modes(tmp_path: Path) -> None:
    refs = [
        _ref(tmp_path, "run_b/a.png"),
        _ref(tmp_path, "run_a/a.png"),
        _ref(tmp_path, "run_a/b.png"),
    ]
    categories = {
        "a": Category(key="a", refs=[refs[0], refs[1]]),
        "b": Category(key="b", refs=[refs[2]]),
    }
    by_cat = build_playlist(
        categories,
        {"a", "b"},
        SortMode.CATEGORY_THEN_PATH,
        group_mode=GroupMode.STEM,
    )
    assert [str(r.relative_path) for r in by_cat] == [
        "run_a/a.png",
        "run_b/a.png",
        "run_a/b.png",
    ]

    by_path = build_playlist(
        categories,
        {"a", "b"},
        SortMode.PATH_THEN_CATEGORY,
        group_mode=GroupMode.STEM,
    )
    assert [str(r.relative_path) for r in by_path] == [
        "run_a/a.png",
        "run_a/b.png",
        "run_b/a.png",
    ]


def test_filter_by_path_prefix(tmp_path: Path) -> None:
    refs = [
        _ref(tmp_path, "run_a/plot.png"),
        _ref(tmp_path, "run_b/plot.png"),
        _ref(tmp_path, "run_a/other.png"),
    ]
    filtered = filter_by_path_prefix(refs, Path("run_a"))
    assert [str(r.relative_path) for r in filtered] == [
        "run_a/plot.png",
        "run_a/other.png",
    ]
    assert filter_by_path_prefix(refs, None) == refs


def test_build_scan_index(tmp_path: Path) -> None:
    (tmp_path / "run_a").mkdir()
    (tmp_path / "run_b").mkdir()
    (tmp_path / "run_a" / "fig.png").write_bytes(b"x")
    (tmp_path / "run_b" / "fig.png").write_bytes(b"x")
    (tmp_path / "run_a" / "doc.pdf").write_bytes(b"x")

    index = build_scan_index(tmp_path, options=ScanOptions())
    assert len(index.refs) == 3
    assert sum(1 for r in index.refs if r.is_displayable) == 3


def test_directory_exclusions(tmp_path: Path) -> None:
    refs = [
        _ref(tmp_path, "run_a/cond1/plot.png"),
        _ref(tmp_path, "run_a/cond2/plot.png"),
        _ref(tmp_path, "run_b/cond1/plot.png"),
    ]
    tree = build_directory_tree(refs)
    assert "run_a" in tree.children
    assert "cond1" in tree.children["run_a"].children

    filtered = filter_by_directory_exclusions(refs, {Path("run_a/cond2")})
    assert [str(r.relative_path) for r in filtered] == [
        "run_a/cond1/plot.png",
        "run_b/cond1/plot.png",
    ]

    checked = {
        Path(): True,
        Path("run_a"): True,
        Path("run_a/cond1"): True,
        Path("run_a/cond2"): False,
        Path("run_b"): True,
        Path("run_b/cond1"): True,
    }
    assert maximal_exclusions(checked) == {Path("run_a/cond2")}


def test_prune_directory_exclusions_after_rescan(tmp_path: Path) -> None:
    from figuregallery.directory_tree import prune_directory_exclusions

    old_excluded = {Path("run_a/cond2"), Path("gone"), Path("run_b")}
    refs = [
        _ref(tmp_path, "run_a/cond1/plot.png"),
        _ref(tmp_path, "run_a/cond2/plot.png"),
        _ref(tmp_path, "run_b/cond1/plot.png"),
    ]
    pruned = prune_directory_exclusions(old_excluded, refs)
    assert pruned == {Path("run_a/cond2"), Path("run_b")}
    assert prune_directory_exclusions(old_excluded, []) == set()


def test_directory_filter_tree_follows_scan_not_category_subset(tmp_path: Path) -> None:
    """Directories… must use the full current scan tree, not a category-shrunk leftover."""
    from figuregallery.directory_tree import build_filter_display_tree
    from figuregallery.index import build_scan_index
    from PIL import Image

    root_a = tmp_path / "exp_a"
    root_b = tmp_path / "exp_b"
    for root, folders in (
        (root_a, ["old_branch/cond1", "old_branch/cond2"]),
        (root_b, ["new_branch/x", "other_top/y"]),
    ):
        for folder in folders:
            dest = root / folder
            dest.mkdir(parents=True)
            Image.new("RGB", (4, 4)).save(dest / "plot.png")

    index_a = build_scan_index(root_a)
    index_b = build_scan_index(root_b)

    def collect(nodes):
        found: set[str] = set()
        for node in nodes:
            if node.name:
                found.add(node.name)
            found.update(v.name for v in node.fan_variants if v.name)
            found |= collect(node.children)
        return found

    # Category-only subset (old behavior) can look like the previous root when stems match.
    selected_only_b = [
        ref for ref in index_b.refs if ref.is_displayable and ref.stem == "plot"
    ]
    # Full scan tree (new behavior) must not include the previous root's folders.
    full_b = [ref for ref in index_b.refs if ref.is_displayable]
    assert collect(build_filter_display_tree(full_b)) == collect(
        build_filter_display_tree(selected_only_b)
    )  # same files here, but names must be from root_b
    names_b = collect(build_filter_display_tree(full_b))
    names_a = collect(build_filter_display_tree([r for r in index_a.refs if r.is_displayable]))
    assert "old_branch" in names_a
    assert "old_branch" not in names_b
    assert "new_branch" in names_b and "other_top" in names_b


def test_list_figures_in_directory(tmp_path: Path) -> None:
    refs = [
        _ref(tmp_path, "run/a/plot.png"),
        _ref(tmp_path, "run/a/other.png"),
        _ref(tmp_path, "run/b/plot.png"),
    ]
    from figuregallery.playlist import list_figures_in_directory

    in_a = list_figures_in_directory(refs, Path("run/a"))
    assert [r.filename for r in in_a] == ["other.png", "plot.png"]


def test_playlist_includes_pdf(tmp_path: Path) -> None:
    refs = [
        _ref(tmp_path, "run/plot.png"),
        _ref(tmp_path, "run/plot.pdf"),
    ]
    categories = {"plot": Category(key="plot", refs=refs)}
    playlist = build_playlist(
        categories,
        {"plot"},
        SortMode.CATEGORY_THEN_PATH,
        group_mode=GroupMode.STEM,
    )
    assert [r.filename for r in playlist] == ["plot.pdf", "plot.png"]
    pdf_only = Category(key="plot.pdf", refs=[refs[1]])
    assert pdf_only.is_selectable
    assert pdf_only.pdf_count == 1


def test_first_index_for_category(tmp_path: Path) -> None:
    from figuregallery.playlist import first_index_for_category

    refs = [
        _ref(tmp_path, "run_a/a.png"),
        _ref(tmp_path, "run_b/a.png"),
        _ref(tmp_path, "run_a/b.png"),
    ]
    categories = {
        "a": Category(key="a", refs=[refs[0], refs[1]]),
        "b": Category(key="b", refs=[refs[2]]),
    }
    playlist = build_playlist(
        categories,
        {"a", "b"},
        SortMode.CATEGORY_THEN_PATH,
        group_mode=GroupMode.STEM,
    )
    assert [r.filename for r in playlist] == ["a.png", "a.png", "b.png"]
    assert first_index_for_category(playlist, "a", group_mode=GroupMode.STEM) == 0
    assert first_index_for_category(playlist, "b", group_mode=GroupMode.STEM) == 2
    assert first_index_for_category(playlist, "missing", group_mode=GroupMode.STEM) is None


def test_scan_and_playlist_include_mp4(tmp_path: Path) -> None:
    from figurecommon.exts import is_video_path

    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "clip.mp4").write_bytes(b"not-a-real-video")
    (tmp_path / "run" / "plot.png").write_bytes(b"x")
    assert is_video_path(tmp_path / "run" / "clip.mp4")

    found = list(walk_figures(tmp_path, ScanOptions()))
    assert {p.name for p in found} == {"clip.mp4", "plot.png"}

    # Optional include_video=False still skips mp4 (e.g. still-only scans).
    no_video = list(walk_figures(tmp_path, ScanOptions(include_video=False)))
    assert {p.name for p in no_video} == {"plot.png"}

    index = build_scan_index(tmp_path, options=ScanOptions())
    categories = group_refs(index.refs, GroupMode.STEM)
    assert "clip" in categories
    assert categories["clip"].is_selectable
    playlist = build_playlist(
        categories,
        {"clip", "plot"},
        SortMode.CATEGORY_THEN_PATH,
        group_mode=GroupMode.STEM,
    )
    assert [r.filename for r in playlist] == ["clip.mp4", "plot.png"]


def test_export_pdf_skips_videos(tmp_path: Path) -> None:
    from figuregallery.export import export_playlist_pdf
    from PIL import Image
    import pytest

    (tmp_path / "run").mkdir()
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(tmp_path / "run" / "plot.png")
    (tmp_path / "run" / "clip.mp4").write_bytes(b"x")
    refs = [
        _ref(tmp_path, "run/clip.mp4"),
        _ref(tmp_path, "run/plot.png"),
    ]
    out = tmp_path / "gallery.pdf"
    result = export_playlist_pdf(refs, out)
    assert result.pages == 1
    assert out.is_file()

    video_only = [_ref(tmp_path, "run/clip.mp4")]
    with pytest.raises(ValueError, match="video-only"):
        export_playlist_pdf(video_only, tmp_path / "empty.pdf")


def test_video_scrub_bar_only_while_playing(monkeypatch) -> None:
    from figuregallery.platform import configure_qt_plugins
    from figuregallery.ui.viewport import FigureViewport, _format_ms

    assert _format_ms(0) == "0:00"
    assert _format_ms(65_000) == "1:05"
    assert _format_ms(3_661_000) == "1:01:01"

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    configure_qt_plugins()
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    vp = FigureViewport()
    vp.show()
    app.processEvents()
    # Scrub lives on the video panel, which stays hidden for stills / empty state.
    assert not vp._video_panel.isVisible()
    assert vp._scrub.parentWidget() is vp._video_panel

    vp._video_panel.show()
    app.processEvents()
    assert vp._scrub.isVisible()

    vp._video_panel.hide()
    app.processEvents()
    assert not vp._scrub.isVisible()

    vp.close()
    vp.deleteLater()
    app.processEvents()


def test_symmetric_directory_fold(tmp_path: Path) -> None:
    refs = [
        _ref(tmp_path, "A/a/z1/plot.png"),
        _ref(tmp_path, "A/a/y1/plot.png"),
        _ref(tmp_path, "A/b/z1/plot.png"),
        _ref(tmp_path, "B/a/z1/plot.png"),
        _ref(tmp_path, "B/a/y1/plot.png"),
        _ref(tmp_path, "B/b/z1/plot.png"),
    ]
    display = build_filter_display_tree(refs)
    assert len(display) == 1
    fan = display[0]
    assert len(fan.fan_variants) == 2
    assert {v.name for v in fan.fan_variants} == {"A", "B"}
    shared_names = {child.name for child in fan.children}
    assert shared_names == {"a", "b"}

    checked = {id(fan.fan_variants[0]): True, id(fan.fan_variants[1]): True}
    for child in fan.children:
        checked[id(child)] = child.name != "b"
        for grandchild in child.children:
            checked[id(grandchild)] = True

    excluded = collect_exclusions(display, checked)
    assert Path("A/b") in excluded
    assert Path("B/b") in excluded
    filtered = filter_by_directory_exclusions(refs, excluded)
    assert all("/b/" not in str(r.relative_path) for r in filtered)
    assert len(filtered) == 4


def test_export_filename_and_path_title(tmp_path: Path) -> None:
    from figuregallery.export import export_playlist_pdf, path_title, suggest_export_filename

    refs = [
        _ref(tmp_path, "run_a/plot.png"),
        _ref(tmp_path, "run_b/plot.png"),
    ]
    assert path_title(Path("run_a/cond1/plot.png")) == "run_a / cond1 / plot.png"
    assert suggest_export_filename(refs, GroupMode.STEM) == "plot_gallery.pdf"
    mixed = refs + [_ref(tmp_path, "run_a/other.png")]
    assert suggest_export_filename(mixed, GroupMode.STEM) == "figure_gallery_3_figures.pdf"

    # Tiny PNG for PDF write
    from PIL import Image

    for ref in refs:
        ref.absolute_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), color=(200, 100, 50)).save(ref.absolute_path)

    out = tmp_path / "out" / "gallery.pdf"
    result = export_playlist_pdf(refs, out)
    assert result.pages == 2
    assert result.path.is_file()
    assert result.path.stat().st_size > 0

    import fitz

    with fitz.open(out) as doc:
        assert len(doc) == 2
        # Pages are sized to the figure pixels (8×8 PNG → 8×8 pt), not US Letter.
        assert abs(doc[0].rect.width - 8.0) < 0.1
        assert abs(doc[0].rect.height - 8.0) < 0.1


def test_browse_pacing_expands_on_fast_nav_and_decays_when_idle(monkeypatch) -> None:
    from figuregallery.browse_pacing import BrowsePacing

    pacing = BrowsePacing()
    clock = {"t": 100.0}
    monkeypatch.setattr("figuregallery.browse_pacing.time.monotonic", lambda: clock["t"])

    assert pacing.budget.cache_size == BrowsePacing.BASE_CACHE
    assert pacing.budget.prefetch_radius == BrowsePacing.BASE_PREFETCH

    for _ in range(BrowsePacing.FAST_STREAK):
        clock["t"] += 0.1
        pacing.note_navigate()

    assert pacing.budget.cache_size > BrowsePacing.BASE_CACHE
    assert pacing.budget.prefetch_radius > BrowsePacing.BASE_PREFETCH
    expanded = pacing.budget

    assert pacing.decay_if_idle() is None  # not idle yet
    clock["t"] += BrowsePacing.IDLE_S + 0.1
    decayed = pacing.decay_if_idle()
    assert decayed is not None
    assert decayed.cache_size < expanded.cache_size
    assert decayed.cache_size >= BrowsePacing.MIN_CACHE


def test_image_cache_set_max_items_trims_lru() -> None:
    from PyQt6.QtGui import QImage

    from figuregallery.cache import ImageCache

    cache = ImageCache(max_items=3)
    paths = [Path(f"/tmp/fig_{i}.png") for i in range(3)]
    for p in paths:
        cache.put(p, QImage(1, 1, QImage.Format.Format_RGB32))
    assert len(cache) == 3

    cache.set_max_items(2)
    assert cache.max_items == 2
    assert len(cache) == 2
    # Oldest (paths[0]) should be evicted
    assert cache.get(paths[0]) is None
    assert cache.get(paths[1]) is not None
    assert cache.get(paths[2]) is not None


def test_settings_recent_roots_mru_dedupe_and_cap(tmp_path: Path, monkeypatch) -> None:
    import figuregallery.settings as settings

    config_dir = tmp_path / "config"
    monkeypatch.setattr(settings, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(settings, "_CONFIG_FILE", config_dir / "settings.json")

    roots = []
    for i in range(10):
        d = tmp_path / f"root_{i}"
        d.mkdir()
        roots.append(d)

    for d in roots:
        settings.save_last_root(d)

    assert settings.load_last_root() == roots[9].resolve()
    recent = settings.load_recent_roots()
    assert len(recent) == 8
    assert recent[0] == roots[9].resolve()
    assert recent[-1] == roots[2].resolve()

    settings.save_last_root(roots[5])
    recent = settings.load_recent_roots()
    assert recent[0] == roots[5].resolve()
    assert recent.count(roots[5].resolve()) == 1


def test_gallery_settings_save_survives_permission_error(tmp_path: Path, monkeypatch) -> None:
    import figuregallery.settings as settings

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(settings, "_CONFIG_DIR", blocked)
    monkeypatch.setattr(settings, "_CONFIG_FILE", blocked / "settings.json")
    monkeypatch.setattr(settings, "_fallback_config_dirs", lambda: [fallback])
    monkeypatch.setattr(settings, "_SAVE_WARNED", False)

    root = tmp_path / "data"
    root.mkdir()
    settings.save_last_root(root)
    assert (fallback / "settings.json").is_file()
    assert settings.load_last_root() == root.resolve()
    blocked.chmod(0o700)


def test_root_picker_listing_and_navigation(tmp_path: Path) -> None:
    from figuregallery.ui.root_picker import (
        child_directories,
        drill_into,
        initial_list_parent,
        navigate_up,
    )

    parent = tmp_path / "experiments"
    a = parent / "run_a"
    b = parent / "run_b"
    nested = a / "cond1"
    for d in (a, b, nested):
        d.mkdir(parents=True)

    assert initial_list_parent(a) == parent.resolve()
    kids = child_directories(parent)
    assert [p.name for p in kids] == ["run_a", "run_b"]

    list_parent, selected = drill_into(a)
    assert list_parent == a.resolve()
    assert selected == nested.resolve()

    empty = b / "empty"
    empty.mkdir()
    list_parent, selected = drill_into(empty)
    assert list_parent == empty.resolve()
    assert selected == empty.resolve()

    up_parent, up_sel = navigate_up(list_parent=a.resolve(), selected=nested.resolve())
    assert up_parent == parent.resolve()
    assert up_sel == a.resolve()


def test_category_label_reflects_directory_exclusions() -> None:
    """Category counts show visible/total when Directories… exclusions are active."""
    from figuregallery.ui.category_panel import category_is_available, category_list_label

    root = Path("/tmp/gallery_label_test")
    refs = [
        _ref(root, "keep/a.png"),
        _ref(root, "drop/a.png"),
        _ref(root, "keep/b.png"),
        _ref(root, "drop/c.png"),
    ]
    cat_a = Category(key="a", refs=[refs[0], refs[1]])
    cat_b = Category(key="b", refs=[refs[2]])
    cat_c = Category(key="c", refs=[refs[3]])

    assert category_list_label(cat_a, set()) == "a (2)"
    assert category_list_label(cat_a, {Path("drop")}) == "a (1/2)"
    assert category_list_label(cat_b, {Path("drop")}) == "b (1)"
    assert category_list_label(cat_c, {Path("drop")}) == "c (0/1)"
    assert category_is_available(cat_a, {Path("drop")})
    assert category_is_available(cat_b, {Path("drop")})
    assert not category_is_available(cat_c, {Path("drop")})


def test_category_panel_grays_or_hides_unavailable(monkeypatch) -> None:
    from figuregallery.platform import configure_qt_plugins
    from figuregallery.ui.category_panel import CategoryPanel

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    configure_qt_plugins()
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    root = Path("/tmp/gallery_unavailable_test")
    refs = [
        _ref(root, "keep/a.png"),
        _ref(root, "drop/c.png"),
    ]
    categories = {
        "a": Category(key="a", refs=[refs[0]]),
        "c": Category(key="c", refs=[refs[1]]),
    }

    panel = CategoryPanel()
    panel.show()
    panel.set_categories(categories, preserve_selection={"a", "c"})
    assert panel.selected_keys() == {"a", "c"}

    panel.set_excluded_directories({Path("drop")})
    app.processEvents()
    # Empty category is deselected and shown grayed (not checkable).
    assert panel.selected_keys() == {"a"}
    labels = [panel._list.item(i).text() for i in range(panel._list.count())]
    assert labels == ["a (1)", "c (0/1)"]
    empty_item = panel._list.item(1)
    assert not (empty_item.flags() & Qt.ItemFlag.ItemIsUserCheckable)

    panel.set_hide_unavailable(True)
    app.processEvents()
    labels = [panel._list.item(i).text() for i in range(panel._list.count())]
    assert labels == ["a (1)"]

    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_figure_file_mime_data_uses_source_url(tmp_path: Path) -> None:
    from figuregallery.ui.figure_transfer import figure_file_mime_data

    path = tmp_path / "fig.pdf"
    path.write_bytes(b"%PDF-1.4 test")

    mime = figure_file_mime_data(path)
    assert mime is not None
    assert mime.hasUrls()
    assert mime.urls()[0].toLocalFile() == str(path.resolve())
    assert not mime.hasImage()
    assert not mime.hasFormat("image/png")

    assert figure_file_mime_data(tmp_path / "missing.png") is None
