# Figure Gallery — Design Document

**Status:** Draft for approval  
**Package name:** `figuregallery`  
**CLI command:** `figuregallery`  
**Last updated:** 2026-09-01

---

## 1. Purpose and relationship to FigureViewer

### Problem

Research workflows often produce **many leaf directories**, each containing **only a few figures**, arranged in a deep tree (e.g. one folder per run, condition, or subject). Browsing these in Finder means constant directory navigation, and the **directory context** (which experiment produced this figure?) is easy to lose if figures are copied into a flat folder.

FigureViewer solves the **opposite** shape: a **small number of directories**, each with **many figures**, compared side-by-side with synchronized navigation.

**Figure Gallery** solves: scan a parent directory tree, **group figures by name** (stem or full filename), let the user **select one or more groups**, and **scroll through all matching instances** in a single gallery view — while showing **where each copy lives** in the tree.

### Sister apps, shared foundation

| | FigureViewer | Figure Gallery |
|---|---|---|
| **Unit of organization** | Panel = directory | Category = filename / stem |
| **Typical tree shape** | Few dirs × many files | Many dirs × few files |
| **Primary interaction** | Side-by-side comparison | Sequential gallery scroll |
| **GUI** | Streamlit (existing) | Native PyQt5 (new) |
| **Shared code** | `figurecommon` (extensions, sort, scan, render) | same |

Both apps address gaps in Finder for neuroscience figure review. They are complementary, not overlapping.

---

## 2. Goals and non-goals

### Goals (v1)

- Scan a directory tree for figure files and index them by **stem** (default) or **filename**.
- Present categories in a sidebar with **counts**; user selects one or more.
- Display one large figure at a time with **relative path** shown above it.
- **Scroll** through the union of selected categories (keyboard, buttons, slider).
- **Configurable sort order** for the playlist.
- **Reveal in Finder** (or platform equivalent) for the current figure.
- **Lazy image loading** with a small in-memory cache.
- Launch via **CLI** with optional root path argument.

### Non-goals (v1)

- Side-by-side multi-panel comparison (use FigureViewer).
- Metadata YAML sidecars (`_figuregroup.yaml`).
- Export / save composite images.
- Live filesystem watching.
- PDF **display** (deferred to v2); PDFs are **indexed** and shown grayed in the sidebar so you can see how many exist.

### Non-goals (ever, unless scope changes)

- Cloud sync, remote URLs, or database backends.
- Image editing or annotation.

---

## 3. User stories

### US-1: Scan and discover categories

> As a researcher, I select a parent directory so the app finds all figures in the tree and shows me how many copies exist of each name.

**Acceptance:**
- User can pick a root via CLI argument or native folder dialog.
- Scan completes and sidebar lists categories with counts, e.g. `spike_raster (12)`.
- Scan skips common junk directories (`.git`, `__pycache__`, hidden dirs, etc.).
- Status line shows total files found and scan duration.

### US-2: Select categories and browse

> As a researcher, I check `X` and `Z` in the sidebar and scroll through all 20 matching figures without reopening folders.

**Acceptance:**
- Multi-select categories via checkboxes.
- Main view shows one figure; position indicator shows e.g. `7 / 20`.
- Left/Right arrows, Home/End, and a slider all navigate the playlist.
- Changing selection rebuilds the playlist; index resets to 0 (or clamps if shorter).

### US-3: Retain directory context

> As a researcher, I see which run/condition produced the figure I'm looking at.

**Acceptance:**
- Path displayed **relative to scan root**, e.g. `run_A / cond1 / spike_raster.png`.
- Path segments are visually distinct (breadcrumb buttons); v1 click is informational only (no filter).
- Sub-caption shows category context, e.g. `spike_raster · 3 of 12 in this category`.

### US-4: Jump to filesystem

> As a researcher, I press a hotkey to open Finder at the current figure's location.

**Acceptance:**
- Toolbar button **Reveal in Finder** (platform-appropriate label on non-macOS).
- Hotkey: `Cmd+E` (macOS) / `Ctrl+E` (Windows/Linux).
- Uses `open -R <file>` on macOS; reasonable equivalents elsewhere.

### US-5: Match my workflow with sort order

> As a researcher, I sometimes want all copies of figure X together; sometimes I want to walk folder-by-folder.

**Acceptance:**
- Toolbar dropdown with two modes:
  - **Category → Path** — all instances of category A (sorted by path), then category B, …
  - **Path → Category** — depth-first by directory; within each dir, selected categories in natural name order.
- Changing sort preserves the **currently displayed figure** if it remains in the playlist.

### US-6: Handle extension ambiguity

> As a researcher, I toggle between stem and filename grouping when `X.png` and `X.pdf` are or aren't the same figure.

**Acceptance:**
- Toggle: **Group by stem** (default) / **Group by filename**.
- Toggle rebuilds category list from existing scan (no rescan).
- Selection preserved where possible: stem `X` selected → filename mode selects all `X.*` variants.

---

## 4. UI layout

### Main window

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Figure Gallery                                    [Open…] [Rescan]      │
├──────────────────────────────────────────────────────────────────────────┤
│  Root: /Users/you/experiments/batch_03    Sort: [Category → Path ▼]    │
│  Group: (•) Stem  ( ) Filename                                           │
├──────────────────┬───────────────────────────────────────────────────────┤
│  Categories      │  run_A / cond1 / results                              │
│  ──────────────  │  ─────────────────────────────────────────────────    │
│  Filter: [____]  │                                                       │
│                  │                                                       │
│  ☑ spike_raster  │              ┌─────────────────────┐                  │
│     (12)         │              │                     │                  │
│  ☐ mean_fr       │              │    [figure image]   │                  │
│     (12)         │              │                     │                  │
│  ☑ waveform      │              └─────────────────────┘                  │
│     (8)          │                                                       │
│                  │  ◀   7 / 20   ▶          [========●==========]          │
│  2 selected      │  spike_raster · 3 of 12 in this category              │
│  20 figures      │                                                       │
│                  │  [Reveal in Finder]                                     │
└──────────────────┴───────────────────────────────────────────────────────┘
```

### Regions

| Region | Widget | Notes |
|---|---|---|
| **Menu / toolbar** | Open, Rescan, Reveal, sort dropdown, group toggle | Standard `QMainWindow` toolbar |
| **Category panel** | `QListWidget` or `QTreeWidget` with checkboxes | Fixed width ~220px; collapsible in v2 |
| **Filter box** | `QLineEdit` | Case-insensitive substring filter on category keys |
| **Path bar** | Row of `QPushButton` segments + filename | Relative to root; last segment is filename |
| **Viewport** | `QLabel` or `QGraphicsView` | Fit-to-window with aspect ratio preserved |
| **Navigation** | Prev/Next buttons, slider, counter label | Disabled when playlist empty |
| **Status bar** | Scan stats, load errors | `QStatusBar` |

### Empty states

| State | Message |
|---|---|
| No root selected | "Open a directory to scan for figures." |
| Scan found 0 figures | "No figures found under \<root\>." |
| Root selected, no categories checked | "Select one or more categories to browse." |

---

## 5. Interaction details

### Keyboard shortcuts

| Key | Action |
|---|---|
| `←` / `→` | Previous / next figure |
| `Home` / `End` | First / last figure |
| `Cmd+O` / `Ctrl+O` | Open root directory |
| `Cmd+E` / `Ctrl+E` | Reveal in Finder |
| `Cmd+R` / `Ctrl+R` | Rescan |
| `Space` | Next figure (optional; matches some gallery apps) |

Shortcuts apply when main viewport has focus, not when typing in the filter box.

### Category filter

- Filters the **sidebar list** only; does not change which categories are checked.
- Hidden categories remain checked; they still contribute to the playlist.

### Group-by toggle behavior

1. User scans tree → index built once per file: `{ path, relative_path, stem, filename }`.
2. **Stem mode:** categories keyed by `stem`; label shows stem only.
3. **Filename mode:** categories keyed by full `filename` including extension.
4. On toggle: rebuild category map from scan index; remap selection (stem → all matching filenames).

**Rationale:** Re-indexing from cached scan is instant; rescanning the filesystem is unnecessary.

### Sort order semantics

**Category → Path** (default):
```
for category in selected_categories (natural sort):
    for path in category.files sorted by relative_path (natural sort):
        emit
```

**Path → Category**:
```
for directory in unique_parent_dirs (depth-first, natural sort):
    for category in selected_categories (natural sort):
        if file exists in directory:
            emit
```

Depth-first directory order: sort full relative **parent** paths naturally, not inode order.

---

## 6. Supported file types

### v1 (display)

| Extension | Handling |
|---|---|
| `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` | Load via Pillow → `QImage` |
| `.svg` | Rasterize via PyMuPDF (same approach as FigureViewer) |

### v2 (display)

| Extension | Handling |
|---|---|
| `.pdf` | Rasterize page 1 via PyMuPDF |

### Indexing

PDFs are **included in the scan index**. Categories that contain only PDFs appear **grayed out** in the sidebar; attempting to select them shows a message that PDF display is coming in v2. Mixed categories (e.g. `X.png` and `X.pdf` under stem grouping) are selectable; the playlist includes displayable files only.

---

## 7. Scan exclusions

Always skip during walk:

- Hidden files and directories (name starts with `.`)
- Directory names: `.git`, `__pycache__`, `node_modules`, `.venv`, `venv`, `.eggs`

Optional (v1, enabled by default):

- If `<root>/.gitignore` exists, skip files/dirs matching **simple glob rules** (no full gitignore spec parser).

**Rationale:** Avoids scanning artifact trees; `.gitignore` support is familiar and cheap at basic level.

---

## 8. Performance and memory

### Targets

| Metric | Target |
|---|---|
| Scan 5,000 files | < 3 s on local SSD |
| Category toggle | < 100 ms |
| Figure navigation | < 50 ms when cached; show spinner if load > 200 ms |
| Memory (decoded images) | ≤ 5 full-resolution images in LRU cache |

### Strategy

- Scan stores paths and metadata only.
- Decode images in a **background `QThread`**; cancel stale loads when user scrolls quickly.
- LRU cache keyed by absolute path; evict oldest when size exceeds limit.

**Rationale:** Same philosophy as FigureViewer — responsiveness over holding everything in memory.

---

## 9. CLI

```bash
figuregallery                          # GUI with empty state; Open to pick root
figuregallery /path/to/experiments     # Scan immediately on launch
figuregallery --group-by filename      # Override default stem grouping
figuregallery --sort path-then-category
```

Exit codes: `0` normal quit; `1` for CLI usage errors (invalid path, etc.).

---

## 10. Version roadmap

### v1.0 — MVP (this spec)

All user stories US-1 through US-6; raster image formats; PyQt5 GUI; `figurecommon` extraction.

### v1.1 — Polish

- Session persistence (last root, window geometry, sort mode, group mode) via `~/.config/figuregallery/settings.json`
- Breadcrumb segment click → filter playlist to path prefix
- Thumbnail strip below main image (small cache of downscaled thumbs)

### v2.0 — PDF and parity

- PDF display in viewport
- Optional whitespace trim (port from FigureViewer)
- Include PDFs in scan index

---

## 11. Rationale summary

| Decision | Why |
|---|---|
| Native PyQt5, not Streamlit | Gallery scroll and keyboard nav need snappy local UI; Streamlit reruns are a poor fit for rapid sequential browsing. |
| Monorepo + `figurecommon` | Extensions, natural sort, scan, and render logic are identical; avoids drift. FigureViewer migrates incrementally. |
| Default group by stem | Most cross-directory comparisons are "same figure name, different run folder." |
| Filename toggle | `X.png` vs `X.pdf` are often duplicates but not always; user judgment required. |
| Relative paths | Absolute paths are long and repetitive when all files share a root. |
| Two sort modes only | Covers the two observed workflows without over-engineering interleaved orderings. |
| Reveal in Finder | Browsing is exploratory; user often needs neighboring scripts, data, or logs. |
| Exclude PDFs from v1 scan | Avoids selecting categories that cannot be displayed yet. |
| No metadata sidecars | Context here is **path**, not experiment metadata; keeps v1 focused. |

---

## 12. Approval checklist

Before implementation begins, confirm:

- [ ] Package name `figuregallery` and CLI `figuregallery` are acceptable.
- [x] PyQt6 (approved over PyQt5).
- [x] PDFs indexed but grayed until v2 display support.
- [ ] Selection preservation on stem/filename toggle is acceptable.
- [ ] Sort-change preserves current figure (not reset to index 0).
- [x] Hotkey `Cmd+E` / `Ctrl+E` for Reveal in Finder.

---

## 13. References

- FigureViewer README: multi-panel comparison, sync modes, supported extensions.
- Technical implementation: [`figuregallery-technical.md`](figuregallery-technical.md)
