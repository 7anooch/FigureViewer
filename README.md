# Multi-panel Figure Compare

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

If you already have `figviewer`, activate it and install/update the package:

```bash
conda activate figviewer
pip install -e .
```

With embedded PDF viewer support:

```bash
conda activate figviewer
pip install -e ".[pdf-embed]"
```

Minimal install (images only, no PDF rasterization):

```bash
pip install -e . --no-deps
pip install streamlit pyyaml
```

### Dependencies

- `streamlit` — app framework
- `pyyaml` — metadata sidecar files
- `pymupdf` — rasterize PDF figures for sharp side-by-side comparison (recommended)
- `streamlit[pdf]` — optional; only needed for **Embedded viewer** PDF mode (`pip install -e ".[pdf-embed]"`)

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

## Development

```bash
conda activate figviewer
pip install -e ".[dev]"
python -m compileall src/figureviewer
```

## Notes

This app is meant to do things Finder does not do well:

- compare several corresponding figure directories in one workspace
- synchronize navigation across panels
- compare by filename stem even when extensions differ
- preserve your filesystem organization
- attach research metadata directly to figure folders
