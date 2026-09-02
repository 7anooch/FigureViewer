from __future__ import annotations

from pathlib import Path

from figurecommon.scan import ScanOptions, walk_figures
from figuregallery.grouping import group_refs, remap_selection
from figuregallery.index import build_scan_index
from figuregallery.models import FigureRef, GroupMode
from figuregallery.playlist import build_playlist, filter_by_path_prefix
from figuregallery.models import SortMode, Category


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
    assert not name_groups["plot.pdf"].is_selectable
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
    assert [str(r.relative_path) for r in filtered] == ["run_a/plot.png", "run_a/other.png"]
    assert filter_by_path_prefix(refs, None) == refs


def test_build_scan_index(tmp_path: Path) -> None:
    (tmp_path / "run_a").mkdir()
    (tmp_path / "run_b").mkdir()
    (tmp_path / "run_a" / "fig.png").write_bytes(b"x")
    (tmp_path / "run_b" / "fig.png").write_bytes(b"x")
    (tmp_path / "run_a" / "doc.pdf").write_bytes(b"x")

    index = build_scan_index(tmp_path, options=ScanOptions())
    assert len(index.refs) == 3
    assert sum(1 for r in index.refs if r.is_displayable) == 2
