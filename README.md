# Figure Viewer

A local Streamlit app for comparing corresponding figures across multiple folders.

## Project layout

```text
FigureViewer/
├── pyproject.toml          # package metadata and dependencies
├── README.md
└── src/
    └── figureviewer/
        ├── app.py          # Streamlit entry point
        ├── cli.py          # `figureviewer` console command
        ├── figures.py      # panel config, file discovery, stem sync
        ├── navigation.py   # index / keyboard navigation state
        ├── render.py       # image and PDF rendering
        ├── metadata.py     # sidecar metadata read/write
        ├── keynav/         # focus-aware arrow-key component
        └── ui/
            ├── column_browser.py  # Finder-style directory columns (main area)
            ├── sidebar.py         # settings + selected panels
            └── viewport.py
```

## Install

Create the conda environment (first time only):

```bash
conda env create -f environment.yaml
conda activate figviewer
pip install -e .
```

This installs dependencies from conda-forge (including PyQt6). `pyproject.toml` declares no pip runtime deps; `pip install -e .` only registers the local packages and CLI entry points.

If you already have `figviewer`, update and reinstall the local package:

```bash
conda activate figviewer
conda env update -f environment.yaml --prune
pip install -e .
```

If a previous pip extra installed PyPI Qt (`PyQt6-Qt6`) and macOS fails with `Could not find the Qt platform plugin "cocoa"`: `pip uninstall -y PyQt6-Qt6` then `conda install -c conda-forge pyqt6`.

### Dependencies

- `streamlit` — app framework
- `pyyaml` — metadata sidecar files
- `pymupdf` — rasterize PDF figures for sharp side-by-side comparison
- `pillow` — image loading
- `pyqt6` — Figure Gallery GUI

Arrow-key navigation is built in and only applies outside the sidebar.

## Run

With `figviewer` activated:

```bash
conda activate figviewer
figureviewer
```

Equivalent alternatives:

```bash
python -m figureviewer
streamlit run src/figureviewer/app.py
```

## Choosing directories

Use the **Directories** panel above the figures (Finder column view):

1. Set a **root directory** (type a path or click **Browse…**), then **Open**.
2. The first column lists subfolders of the root; click a folder to open the next column to its right.
3. Highlighted folders show your current branch; the path breadcrumb shows where you are.
4. Click **+** beside a folder to add it as a panel, or use **Add “…” as panel** for the deepest folder.

The sidebar lists selected panels and display/sync settings. Uncheck **Show directory browser** (under **Panels**) to hide the browser and maximize figure space after choosing folders.

## Directory input format (manual)

In the sidebar, enter one panel per line:

```text
old = /Users/you/project/figures/iteration_1
new = /Users/you/project/figures/iteration_2
filtered = /Users/you/project/figures/filtered
```

You can also enter bare paths; the folder name is used as the panel label.

## Supported files

Images:

```text
.png, .jpg, .jpeg, .webp, .gif, .svg
```

PDFs:

```text
.pdf
```

## Display options

- **Display size**
  - **Fill panel** (default) — figures use the full column width
  - **Natural size** — native pixel dimensions up to the column width (sharpest for high-res PNGs)
  - **Custom width** — fixed pixel width
- **PDF display**
  - **Rasterize** (default) — render page 1 via PyMuPDF at configurable DPI; best for comparing PDFs with raster images
  - **Embedded viewer** — native `st.pdf` viewer (requires `streamlit[pdf]`)
- **Trim whitespace margins** — crop near-white page margins (useful for A4-centered PDF plots); applies to display and export

## Export

Use **Save figure** in the sidebar to write a single PNG of the current view:

- Panels are arranged in the same row/column layout as on screen.
- Each panel includes its title above the figure (panel labels by default).
- Enable **Use custom titles** to supply one title per line (must match the number of panels).
- **Output directory** defaults to the common parent folder of the selected panels; browse or type a path.
- The first save prompts for a folder if none is set; that folder is reused for the rest of the session.
- Check **Choose output folder on each save** to pick a different folder every time.
- **Save all figures** exports every synchronized index (by position or filename stem) with the same layout and titles.
- When syncing by **filename stem**, exports include a centered suptitle derived from the stem (underscores/hyphens → spaces, title case).
- Quality: **Export PDF / SVG DPI** (default 300) controls rasterization; **Preserve native resolution** (default on) never downscales panels, and **Min panel width** sets a lower bound.

## Navigation modes

- **Sync by position**: panel A file #20 is compared to panel B file #20.
- **Sync by filename stem**: `trial_001.png` matches `trial_001.pdf`, `trial_001.jpg`, etc.
- **Unsynced**: each panel gets its own index slider.

When syncing by stem, duplicate stems in one folder (e.g. `fig1.png` and `fig1.pdf`) use the first file in natural sort order.

## Keyboard shortcuts

Arrow keys navigate figures only when focus is not in the sidebar (sidebar sliders, radios, and text fields keep their normal behavior):

- Left arrow: previous
- Right arrow: next
- Home: first
- End: last

First/Last are also available in the sidebar.

## Metadata sidecars

Each directory can have a metadata file such as:

```text
_figuregroup.yaml
```

The app can read and write descriptions plus optional fields:

- description
- commit hash
- generating script / notebook
- source data path
- tags
- notes

## Figure Gallery (sister app)

Native PyQt6 app for browsing figures **across a directory tree**, grouped by filename or stem.

Use when you have **many folders with a few figures each** (the inverse of FigureViewer's use case).

```bash
conda activate figviewer
figuregallery
figuregallery /path/to/experiment/tree
```

(PyQt6 comes from conda-forge via `environment.yaml`.)

- Scan a root directory; categories appear in a sidebar with counts.
- Select one or more categories and scroll through all matching figures.
- Path shown relative to root; **Open enclosing folder** (`Cmd+E` / `Ctrl+E`).
- **Export PDF…** (`Cmd+S` / `Ctrl+S`) writes the current playlist as one figure per page with a path title.
- Toggle **Stem** vs **Filename** grouping; choose sort order **Category → Path** or **Path → Category**.
- PDFs are indexed and shown grayed in the sidebar (display support planned for v2).

Docs: [`docs/figuregallery-design.md`](docs/figuregallery-design.md), [`docs/figuregallery-technical.md`](docs/figuregallery-technical.md).

## Development

```bash
conda activate figviewer
pip install -e .
python -m compileall src/figureviewer src/figurecommon src/figuregallery
pytest
```

## Notes

This app is meant to do things Finder does not do well:

- compare several corresponding figure directories in one workspace
- synchronize navigation across panels
- compare by filename stem even when extensions differ
- preserve your filesystem organization
- attach research metadata directly to figure folders
