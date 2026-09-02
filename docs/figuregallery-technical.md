# Figure Gallery — Technical Specification

**Status:** Draft for approval  
**Last updated:** 2026-09-01  
**Design doc:** [`figuregallery-design.md`](figuregallery-design.md)

---

## 1. Overview

This document specifies how to implement **Figure Gallery** as a new package in the existing FigureViewer monorepo, alongside a shared **`figurecommon`** library extracted from FigureViewer utilities. GUI toolkit: **PyQt6**.

### Implementation principles

1. **Extract, don't rewrite** — move extension lists, natural sort, and render helpers from `figureviewer` into `figurecommon`; update FigureViewer imports minimally.
2. **Qt UI is isolated** — no PyQt imports outside `figuregallery/ui/`.
3. **Pure Python core** — scan, index, grouping, and playlist logic are testable without Qt.
4. **Incremental delivery** — land `figurecommon` first, then `figuregallery` MVP.

---

## 2. Repository layout (target)

```text
FigureViewer/
├── pyproject.toml                 # add figuregallery entry point + PyQt5 extra
├── environment.yaml               # add pyqt
├── docs/
│   ├── figuregallery-design.md
│   └── figuregallery-technical.md
└── src/
    ├── figurecommon/
    │   ├── __init__.py
    │   ├── exts.py                # FIGURE_EXTS, IMAGE_EXTS, etc.
    │   ├── sort.py                # natural_key
    │   ├── scan.py                # walk_tree, ignore rules
    │   ├── paths.py               # resolve_path, pick_directory_dialog
    │   └── render.py              # PIL/PyMuPDF → PNG bytes (no Streamlit)
    ├── figureviewer/              # existing; imports from figurecommon
    └── figuregallery/
        ├── __init__.py
        ├── __main__.py
        ├── cli.py
        ├── models.py              # FigureRef, ScanIndex, GroupMode, SortMode
        ├── index.py               # build_scan_index
        ├── grouping.py            # group_by_stem / group_by_filename
        ├── playlist.py            # build_playlist, reorder
        ├── cache.py               # ImageCache (LRU)
        ├── platform.py            # reveal_in_file_manager
        ├── settings.py            # v1.1 persistence (stub in v1)
        └── ui/
            ├── __init__.py
            ├── app.py             # QApplication bootstrap
            ├── main_window.py
            ├── category_panel.py
            ├── path_bar.py
            ├── viewport.py
            ├── nav_controls.py
            └── loader.py          # QThread image loader
```

---

## 3. Dependencies

### `pyproject.toml` changes

```toml
[project]
name = "figureviewer"  # repo/package distribution name unchanged for now
# existing figureviewer deps remain

[project.optional-dependencies]
gallery = ["PyQt6>=6.4"]  # optional; conda users get pyqt6 from environment.yaml
dev = ["build", "ruff", "pytest"]

[project.scripts]
figureviewer = "figureviewer.cli:main"
figuregallery = "figuregallery.cli:main"
```

### `environment.yaml` addition

```yaml
dependencies:
  - pyqt6>=6.4   # conda-forge; also available as `pyqt` on some channels
```

### Runtime dependency graph

```text
figuregallery
  ├── PyQt6
  ├── pillow
  ├── figurecommon
  │     ├── pillow
  │     └── pymupdf (optional for SVG; required v2 for PDF)

figureviewer (unchanged)
  ├── streamlit
  ├── figurecommon  # after extraction
  └── ...
```

**Note:** `figurecommon.render` must not import `streamlit`. Extract render logic from `figureviewer/render.py`, dropping `@st.cache_data` and `show_image` / `render_figure` (those stay Streamlit-specific in figureviewer).

---

## 4. `figurecommon` extraction plan

### 4.1 `figurecommon/exts.py`

```python
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VECTOR_EXTS = {".svg"}
PDF_EXTS = {".pdf"}
FIGURE_EXTS = IMAGE_EXTS | VECTOR_EXTS | PDF_EXTS

def is_figure_path(path: Path) -> bool: ...
```

Move from `figureviewer/figures.py`. FigureViewer updates: `from figurecommon.exts import FIGURE_EXTS`.

### 4.2 `figurecommon/sort.py`

Move `natural_key` from `figureviewer/figures.py`.

### 4.3 `figurecommon/paths.py`

Move from `figureviewer/browsing.py` (no Streamlit):
- `resolve_path`
- `pick_directory_dialog`
- `folder_dialog_available`
- `folder_dialog_hint`

### 4.4 `figurecommon/scan.py`

New module (logic currently inline in `list_figures`):

```python
@dataclass(frozen=True)
class ScanOptions:
    follow_gitignore: bool = True
    include_pdf: bool = True  # index PDFs; gallery grays out PDF-only categories until display lands

DEFAULT_SKIP_DIR_NAMES = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".eggs",
})

def should_skip_dir(path: Path, options: ScanOptions) -> bool: ...

def walk_figures(root: Path, options: ScanOptions) -> Iterator[Path]:
    """Yield absolute paths to figure files under root."""
```

**Ignore rules:**
1. Skip hidden components (`part.startswith(".")`).
2. Skip `DEFAULT_SKIP_DIR_NAMES`.
3. If `follow_gitignore` and `root/.gitignore` exists, load patterns and skip matching relative paths (implement minimal parser: blank lines and `#` comments ignored; `dir/` patterns; simple `*` globs via `fnmatch`).

### 4.5 `figurecommon/render.py`

Extract from `figureviewer/render.py`:

| Function | Notes |
|---|---|
| `load_raster_image(path) -> bytes` | Raw file bytes |
| `render_pdf_page(path, dpi) -> bytes` | PNG bytes |
| `trim_whitespace(image) -> Image` | Unchanged |
| `load_figure_bytes(path, *, pdf_dpi, trim) -> bytes` | No `@st.cache_data` |

FigureViewer `render.py` becomes a thin Streamlit wrapper importing `load_figure_bytes` from `figurecommon.render`.

### 4.6 FigureViewer migration (minimal)

| File | Change |
|---|---|
| `figures.py` | Import `FIGURE_EXTS`, `natural_key` from figurecommon; re-export for compatibility if needed |
| `browsing.py` | Import path helpers from `figurecommon.paths` |
| `render.py` | Import `load_figure_bytes`, `trim_whitespace` from `figurecommon.render`; keep `show_image`, `render_figure` |

Run existing manual smoke test on FigureViewer after extraction.

---

## 5. Core data models (`figuregallery/models.py`)

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

class GroupMode(Enum):
    STEM = "stem"
    FILENAME = "filename"

class SortMode(Enum):
    CATEGORY_THEN_PATH = "category_then_path"
    PATH_THEN_CATEGORY = "path_then_category"

@dataclass(frozen=True)
class FigureRef:
  """One figure file discovered during scan."""
    absolute_path: Path
    relative_path: Path   # relative to scan root
    filename: str       # relative_path.name
    stem: str             # relative_path.stem

    @property
    def parent_relative(self) -> Path:
        return self.relative_path.parent

    @property
    def category_key(self, mode: GroupMode) -> str:
        return self.stem if mode == GroupMode.STEM else self.filename

@dataclass
class Category:
    key: str
    refs: list[FigureRef] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.refs)

@dataclass
class ScanIndex:
    root: Path
    refs: list[FigureRef]
    scanned_at: float  # time.monotonic() or datetime

    def categories(self, mode: GroupMode) -> dict[str, Category]:
        ...
```

---

## 6. Indexing and grouping

### 6.1 `index.py`

```python
def build_scan_index(root: Path, *, options: ScanOptions) -> ScanIndex:
    root = root.expanduser().resolve()
    refs: list[FigureRef] = []
    for abs_path in walk_figures(root, options):
        rel = abs_path.relative_to(root)
        refs.append(FigureRef(
            absolute_path=abs_path,
            relative_path=rel,
            filename=rel.name,
            stem=rel.stem,
        ))
  refs.sort(key=lambda r: natural_key(str(r.relative_path)))
    return ScanIndex(root=root, refs=refs, scanned_at=time.time())
```

### 6.2 `grouping.py`

```python
def group_refs(refs: list[FigureRef], mode: GroupMode) -> dict[str, Category]:
    ...

def remap_selection(
    selected: set[str],
    old_mode: GroupMode,
    new_mode: GroupMode,
    index: ScanIndex,
) -> set[str]:
    """Stem → filename: expand to all filename keys sharing stem.
    Filename → stem: map each filename to its stem (dedupe).
    """
    ...
```

---

## 7. Playlist (`playlist.py`)

```python
def build_playlist(
    categories: dict[str, Category],
    selected_keys: set[str],
    sort_mode: SortMode,
) -> list[FigureRef]:
    ...

def index_of_ref(playlist: list[FigureRef], ref: FigureRef) -> int | None:
    ...

def preserve_position(
    old_playlist: list[FigureRef],
    old_index: int,
    new_playlist: list[FigureRef],
) -> int:
    """Return new index showing same FigureRef, or 0 if gone."""
```

### Sort implementation notes

**Category → Path:**
```python
keys = sorted(selected_keys, key=natural_key)
out: list[FigureRef] = []
for key in keys:
    cat = categories[key]
    sorted_refs = sorted(cat.refs, key=lambda r: natural_key(str(r.relative_path)))
    out.extend(sorted_refs)
return out
```

**Path → Category:**
```python
# Collect refs from selected categories
pool = [r for k in selected_keys for r in categories[k].refs]
# Group by parent directory
by_dir: dict[Path, list[FigureRef]] = defaultdict(list)
for r in pool:
    by_dir[r.parent_relative].append(r)
dirs = sorted(by_dir.keys(), key=lambda p: natural_key(str(p)))
keys = sorted(selected_keys, key=natural_key)
out = []
for d in dirs:
    refs_in_dir = {r.filename if mode==FILENAME else r.stem: r for r in by_dir[d]}
    for key in keys:
        if key in refs_in_dir:  # adjust for mode
            out.append(...)
return out
```

Careful: in stem mode, `key` is stem; map accordingly.

---

## 8. Image loading and cache

### 8.1 `cache.py`

```python
class ImageCache:
    def __init__(self, max_items: int = 5): ...

    def get(self, path: Path) -> QImage | None: ...

    def put(self, path: Path, image: QImage) -> None: ...

    def clear(self) -> None: ...
```

Use `collections.OrderedDict` LRU pattern.

### 8.2 `ui/loader.py`

```python
class FigureLoader(QThread):
    loaded = pyqtSignal(str, QImage)   # path, image
    failed = pyqtSignal(str, str)      # path, error message

    def __init__(self):
        self._cancelled_path: str | None = None

    def load(self, path: Path) -> None:
        self._cancelled_path = None
        ...

    def cancel(self) -> None:
        self._cancelled_path = str(path)  # set on pending load
```

Worker logic:
1. Call `figurecommon.render.load_figure_bytes(path, pdf_dpi=150, trim=False)`.
2. Convert PNG bytes → `QImage.fromData(data)`.
3. Emit `loaded` if not cancelled.

Main window slot:
- On `current_index` change, check cache → show immediately if hit.
- Else show placeholder ("Loading…") and start loader.
- On `loaded`, update viewport if path still current.

---

## 9. Platform integration (`platform.py`)

```python
def reveal_in_file_manager(path: Path) -> None:
    """Reveal file in system file manager."""
```

| Platform | Command |
|---|---|
| macOS | `subprocess.run(["open", "-R", str(path)])` |
| Windows | `subprocess.run(["explorer", "/select,", str(path)])` |
| Linux | `subprocess.run(["xdg-open", str(path.parent)])` |

---

## 10. Qt UI architecture

### 10.1 Application entry (`ui/app.py`)

```python
def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Figure Gallery")
    app.setOrganizationName("figuregallery")
    window = MainWindow()
    window.show()
    return app.exec_()
```

### 10.2 `MainWindow` state

```python
@dataclass
class AppState:
    scan_index: ScanIndex | None = None
    group_mode: GroupMode = GroupMode.STEM
    sort_mode: SortMode = SortMode.CATEGORY_THEN_PATH
    categories: dict[str, Category] = field(default_factory=dict)
    selected_keys: set[str] = field(default_factory=set)
    playlist: list[FigureRef] = field(default_factory=list)
    current_index: int = 0
```

### 10.3 Signal flow

```text
User opens root
  → build_scan_index()
  → group_refs() → categories
  → category_panel.set_categories()
  → (no selection) empty viewport

User checks category
  → selected_keys updated
  → build_playlist()
  → current_index = 0 (new selection) or preserve (sort change only)
  → show_current_figure()

User presses Next
  → current_index += 1
  → show_current_figure()

show_current_figure()
  → path_bar.set_path(ref.relative_path)
  → cache.get or loader.load
  → nav_controls.set_index(i, n)
  → status bar caption
```

### 10.4 `path_bar.py`

- Input: `relative_path: Path`, `root_label: str` optional.
- Render: `[run_A] / [cond1] / [results] / spike_raster.png`
- Segments 0..n-2 are `QPushButton` (flat style); last segment is `QLabel` (filename).
- v1: buttons disabled or show tooltip only.

### 10.5 `viewport.py`

- `FigureViewport(QWidget)` with `QLabel` centered in `QVBoxLayout`.
- `set_image(QImage | None)` scales with `Qt.KeepAspectRatio`, `Qt.SmoothTransformation`.
- `set_message(str)` for empty/loading/error states.

### 10.6 Window defaults

- Minimum size: 900 × 600.
- Category panel width: 240px.
- Use Fusion style for cross-platform consistency (optional; test on macOS first).

---

## 11. CLI (`cli.py`)

```python
import argparse
from pathlib import Path

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="figuregallery")
    parser.add_argument("root", nargs="?", type=Path, help="Root directory to scan")
    parser.add_argument(
        "--group-by",
        choices=["stem", "filename"],
        default="stem",
    )
    parser.add_argument(
        "--sort",
        choices=["category-then-path", "path-then-category"],
        default="category-then-path",
    )
    return parser.parse_args(argv)

def main() -> None:
    args = parse_args()
    # validate root if provided
    from figuregallery.ui.app import run
    raise SystemExit(run(initial_root=args.root, group_mode=..., sort_mode=...))
```

`MainWindow` accepts optional `initial_root` and scans on first show.

---

## 12. Settings (v1.1 stub)

```python
# figuregallery/settings.py
_CONFIG_DIR = Path.home() / ".config" / "figuregallery"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

def load_last_root() -> Path | None: ...
def save_last_root(path: Path) -> None: ...
```

Not used in v1.0; file can exist as stubs returning `None`.

---

## 13. Testing strategy

### Unit tests (no Qt)

| Module | Tests |
|---|---|
| `figurecommon/scan.py` | skip rules, gitignore basics, hidden dirs |
| `figurecommon/sort.py` | `fig2` before `fig10` |
| `figuregallery/grouping.py` | stem vs filename grouping |
| `figuregallery/playlist.py` | both sort orders, selection edge cases |
| `figuregallery/grouping.remap_selection` | stem ↔ filename |

Use `tmp_path` fixture with synthetic directory trees:

```text
root/
  run_a/plot.png
  run_b/plot.png
  run_a/other.png
```

### Manual QA checklist

- [ ] Launch with no args; Open picks folder; scan populates sidebar.
- [ ] Launch with path arg; immediate scan.
- [ ] Multi-select categories; count matches playlist length.
- [ ] Both sort modes; current figure preserved on sort change.
- [ ] Stem/filename toggle; selection remap correct.
- [ ] Reveal in Finder works on macOS.
- [ ] Rapid arrow-key scroll does not crash or show wrong image.
- [ ] Large PNG (e.g. 4000×4000) loads off UI thread.
- [ ] FigureViewer still launches and compares panels after `figurecommon` extraction.

### Optional Qt tests

`pytest-qt` for smoke test: window opens, empty state visible. Low priority for v1.

---

## 14. Implementation phases

### Phase 0 — `figurecommon` extraction

1. Create `src/figurecommon/` modules.
2. Update `figureviewer` imports.
3. Smoke test FigureViewer.
4. `python -m compileall src/`.

**Exit criteria:** FigureViewer behavior unchanged.

### Phase 1 — Core logic (no GUI)

1. `figuregallery/models.py`, `index.py`, `grouping.py`, `playlist.py`.
2. Unit tests for scan, group, playlist.
3. `platform.py`.

**Exit criteria:** Tests pass; can build playlist from CLI debug script.

### Phase 2 — PyQt shell

1. `cli.py`, `ui/app.py`, `main_window.py` skeleton.
2. Open folder → scan → category list (no images yet).

**Exit criteria:** Window shows categories with counts.

### Phase 3 — Viewport and navigation

1. `viewport.py`, `loader.py`, `cache.py`, `nav_controls.py`, `path_bar.py`.
2. Full navigation loop.

**Exit criteria:** US-1 through US-4 satisfied.

### Phase 4 — Polish

1. Sort dropdown, group toggle, filter box.
2. Keyboard shortcuts, status bar, error handling.
3. README section for Figure Gallery.

**Exit criteria:** US-5, US-6 satisfied; design approval checklist complete.

---

## 15. Error handling

| Condition | UI response |
|---|---|
| Root path not a directory | Dialog on open; CLI exit 1 |
| Permission denied during scan | Skip unreadable subtrees; log count in status bar |
| Image decode failure | Viewport shows error message; Next still works |
| PyMuPDF missing + SVG file | Error in viewport: "SVG requires PyMuPDF" |
| Empty selection | Viewport shows "Select categories…" |

---

## 16. Security notes

- App only reads local files user selects; no network.
- `subprocess` for folder picker and `open`/`xdg-open` — use list args, no shell=True.
- Scan respects root boundary; `relative_to` ensures no path traversal display issues.

---

## 17. Future hooks (do not implement in v1)

| Hook | Location |
|---|---|
| PDF in scan | `ScanOptions.include_pdf = True` |
| Path filter from breadcrumb | `playlist.filter_by_prefix(Path)` |
| Session restore | `settings.py` + `MainWindow.restore_state()` |
| Thumbnail strip | `ThumbnailCache` with downscaled `QImage` |

---

## 18. Approval checklist (technical)

- [ ] `figurecommon` extraction scope is acceptable (minimal FigureViewer churn).
- [x] v1 scan includes PDFs; PDF-only categories grayed, not selectable.
- [ ] `QThread` loader pattern acceptable (vs `QThreadPool` + `QRunnable`).
- [ ] LRU cache size 5 is acceptable.
- [ ] Implementation phase order is acceptable.

---

## 19. References

- `src/figureviewer/figures.py` — current extensions and natural sort
- `src/figureviewer/render.py` — render logic to extract
- `src/figureviewer/browsing.py` — folder picker to extract
- [`figuregallery-design.md`](figuregallery-design.md) — product requirements
