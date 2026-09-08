# Packaging a Python GUI as a macOS app

An educational overview of what it means to turn something like **Figure Gallery** into a double‑clickable Mac application (Spotlight, Dock, custom icon)—and how that differs from running `figuregallery` in a terminal.

This repo currently uses the **thin launcher** approach. A **frozen / portable** app is the higher‑effort alternative if you ever want to hand someone a `.app` without asking them to install conda.

---

## 1. What macOS actually launches

On macOS, “an app” is not a single executable file. It is a **bundle**: a directory whose name ends in `.app` and that follows a conventional layout. Finder, Spotlight, and the Dock treat that folder as one icon.

```text
Figure Gallery.app/
└── Contents/
    ├── Info.plist          # metadata: name, bundle id, icon, which binary to run
    ├── MacOS/
    │   └── FigureGallery   # the program Launch Services actually executes
    └── Resources/
        └── AppIcon.icns    # Dock / Finder / Spotlight icon
```

When you open the app (double‑click, Spotlight, `open -a …`), **Launch Services**:

1. Reads `Info.plist`
2. Runs `Contents/MacOS/<CFBundleExecutable>`
3. Associates the running process with the bundle (so the Dock can show *your* icon and name)

That is the whole contract. Everything else—Python, PyQt, conda, PyInstaller—is about *what that MacOS executable does*.

### Important keys in `Info.plist`

| Key | Role |
|-----|------|
| `CFBundleDisplayName` | Name under the icon / in Spotlight |
| `CFBundleIdentifier` | Unique id (e.g. `edu.ucsb.figuregallery`) |
| `CFBundleExecutable` | Filename inside `Contents/MacOS/` |
| `CFBundleIconFile` | Icon resource name **without** `.icns` |
| `NSHighResolutionCapable` | Retina-aware drawing |

Our template lives at [`packaging/macos/Info.plist`](../packaging/macos/Info.plist).

### Icons (`.icns`)

macOS wants a multi-resolution icon set, not one PNG. Typical workflow:

1. Design a **1024×1024** master PNG (`assets/figuregallery/icon_1024.png`)
2. Generate sizes (16…512 and `@2x`) into an `.iconset` folder (`sips`)
3. Compile with Apple’s `iconutil -c icns …`

`install_app.sh` does steps 2–3 for you. Re-run it after replacing the master PNG.

### GUI vs terminal entry points

A CLI entry point (`figuregallery` from `pyproject.toml`) is fine in a Terminal. Inside a Dock app you usually want:

- No “Terminal pops open”
- No spam on stderr at startup (shortcuts help, etc.)

We handle that with `FIGUREGALLERY_QUIET=1` set by the launcher, and by skipping the console help when stderr is not a TTY. The same Python package still powers both CLI and app.

---

## 2. Two strategies (same `.app` shell, different guts)

```text
                    ┌─────────────────────────────────────┐
                    │     Figure Gallery.app (bundle)     │
                    │  Info.plist + icon + MacOS stub     │
                    └─────────────────────────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
   Thin launcher (what we have)                    Frozen / portable app
   Stub runs *your machine’s*                      Stub *is* (or starts) a
   conda Python + installed package                self-contained runtime
```

| | **Thin launcher** | **Frozen / portable** |
|--|-------------------|------------------------|
| **What ships in the `.app`** | Plist, icon, small shell/Python stub | Stub + embedded Python + PyQt + PyMuPDF + your code (+ libs) |
| **Where the real app lives** | `figviewer` conda env / editable install | Inside the bundle (or beside it) |
| **Size** | Kilobytes–megabytes (icon-dominated) | Often **100–300+ MB** |
| **Works on another Mac?** | Only if that Mac has the same env setup | Usually yes (same arch: arm64 vs x86_64) |
| **Update your code** | Edit repo → next launch (with `pip install -e .`) | Rebuild the `.app` |
| **Effort** | Low | Medium–high (tooling, debugging missing libs, signing) |
| **Best for** | Personal Dock/Spotlight on *your* machine | Sharing with collaborators who shouldn’t touch conda |

Both approaches can keep a normal CLI (`figuregallery`) for development.

---

## 3. Thin launcher (implemented here)

### Idea

The `.app` is a **friendly face**. Its `MacOS/FigureGallery` script roughly does:

```bash
export FIGUREGALLERY_QUIET=1
export FIGUREGALLERY_APP_ICON="…/Resources/AppIcon.icns"
exec /path/to/figviewer/bin/python -m figuregallery.cli "$@"
```

So:

- Spotlight finds “Figure Gallery”
- Dock shows your `.icns`
- Execution is still the same code as `conda activate figviewer && figuregallery`

Install / refresh:

```bash
conda activate figviewer
pip install -e .    # once, or after packaging changes
./packaging/macos/install_app.sh
# optional: --icon path/to/1024.png  --prefix ~/Applications
open ~/Applications/Figure\ Gallery.app
```

Details: [`packaging/macos/install_app.sh`](../packaging/macos/install_app.sh), logo prompts in [`LOGO_PROMPTS.md`](../packaging/macos/LOGO_PROMPTS.md).

### What the install script does

1. **Resolve Python** — prefer `conda run -n figviewer which python` (overridable with `--python`)
2. **Sanity-check** — that interpreter can `import figuregallery, PyQt6`
3. **Build icon** — PNG → `.iconset` → `AppIcon.icns`
4. **Write the bundle** under `~/Applications/Figure Gallery.app` (or `--prefix`)
5. **Bake absolute paths** into the launcher so double-click does not depend on your shell `PATH`

### Strengths

- Trivial to maintain: change Python code, relaunch
- Uses the same conda stack as development (`environment.yaml`)
- No fight with PyInstaller/Qt plugin discovery day-to-day
- Perfect match for “just for me on this laptop”

### Limitations (important to understand)

- **Not portable.** Another machine needs conda, the `figviewer` env, and `pip install -e .` (or an equivalent install). The `.app` alone is not enough.
- **Brittle paths.** If you rename the conda env, move Anaconda, or reinstall Python, re-run `install_app.sh`.
- **Editable install coupling.** The stub imports `figuregallery` from whatever that Python’s `site-packages` sees. That’s usually what you want while developing; it’s surprising if you expect the `.app` to be a frozen snapshot of last week’s code.
- **Dock identity edge cases.** A shell script that `exec`s into Python usually keeps the right icon when opened via the `.app`, but odd setups (launching the inner Python binary directly) can show a generic Python icon.

### Mental model

> The thin `.app` is a **shortcut with metadata**, not a copy of the program.

---

## 4. Frozen / portable app (higher effort)

### Idea

Bake a **private copy** of the runtime into the bundle (or a folder the stub knows about) so double-click does not need conda on the target Mac.

```text
Figure Gallery.app/Contents/
  MacOS/FigureGallery          # bootloader
  Frameworks/ …                # Qt, Python dylibs, …
  Resources/                   # icon, maybe data files
  # plus your package + site-packages, layout depends on the tool
```

Common toolchains:

| Tool | Notes |
|------|--------|
| **PyInstaller** | Widely used; “onedir” `.app` recipes exist for Qt |
| **Briefcase** (BeeWare) | Opinionated macOS app projects; good docs for GUI apps |
| **py2app** | Classic Mac-oriented freezer; still seen in older tutorials |
| **conda-constructor / pixi / micromamba pack** | Package an *env* as a relocatable prefix, then wrap with a thin stub—hybrid approach |

### What you must solve beyond “wrap my script”

1. **Dependency graph**  
   This project keeps runtime deps in **conda** (`environment.yaml`) and leaves `pyproject.toml` `dependencies = []`. Freezers usually expect **pip-visible** packages, or you point them at conda’s `site-packages` carefully. Plan either:
   - a packaging-specific requirements set (PyQt6, PyMuPDF, Pillow, …), or  
   - a relocatable conda env shipped next to the stub.

2. **Qt plugins / platform**  
   PyQt needs `platforms/libqcocoa.dylib` and friends. Missing plugins → “could not find the Qt platform plugin”. Gallery already has `configure_qt_plugins()` for *dev* launches; a freezer must copy the plugin tree and set `QT_PLUGIN_PATH` (or equivalent) inside the bundle.

3. **Native libraries**  
   PyMuPDF, Pillow, etc. pull `.dylib`s. Freezers miss some; you discover them by running on a clean Mac (or a VM) without your conda env.

4. **Architecture**  
   An arm64 (Apple Silicon) build won’t run on Intel without a separate build (or a universal2 effort).

5. **Gatekeeper / notarization** (if you distribute outside your own account)  
   Unsigned downloads get “cannot be opened because it is from an unidentified developer.” Sharing with a lab often means either:
   - ad‑hoc sign + users right‑click → Open once, or  
   - Apple Developer ID + notarization (real distribution path).

6. **Build reproducibility**  
   CI or a documented “release machine” recipe; “works on my laptop” freezes are fragile.

7. **Update story**  
   Users replace the whole `.app` (or you add an updater). You no longer get editable-install freebies.

### Rough effort profile

| Phase | What happens |
|-------|----------------|
| First successful freeze | 1–3 days of tooling + “missing module / plugin” whack‑a‑mole for a Qt app |
| Clean-machine test | Half day catching dylibs and permissions |
| Signing / notarization | Extra setup if you care about Gatekeeper |
| Ongoing | Rebuild on each release; watch Qt/Python version bumps |

Size and startup time are usually worse than the thin launcher; portability is the payoff.

### Hybrid option (middle ground)

Ship a **relocatable env tarball** (micromamba/conda-pack) plus the same thin `.app` stub that `exec`s `…/envs/figviewer/bin/python -m figuregallery.cli`. Still larger than a freezer’s minimal set, but often easier than teaching PyInstaller about every binary dependency—and still “copy folder + open app” for a collaborator.

---

## 5. How this maps to Figure Gallery / Figure Viewer today

| Piece | Role |
|-------|------|
| `figuregallery` console script | Day-to-day CLI |
| `FIGUREGALLERY_QUIET` / TTY check | Quiet when launched as an app |
| `FIGUREGALLERY_APP_ICON` | `QApplication.setWindowIcon` while running |
| `packaging/macos/install_app.sh` | Builds the **thin** `.app` into `~/Applications` |
| `packaging/macos/bootstrap_install.sh` | Create/use `figviewer` env + editable install + thin `.app` |
| Future desktop FigureViewer merge | Same packaging story: one umbrella `.app`, stub points at one Python entry that can offer Browse vs Compare modes |

A frozen build would **not** replace the need for a good GUI entry point; it would change only *where Python and libraries live*.

---

## 6. Bootstrap installer (middle ground — implemented)

For collaborators who **have conda** but should not hand-assemble the env:

```bash
git clone <repo> && cd FigureViewer
./packaging/macos/bootstrap_install.sh
```

That script:

1. Locates `conda` (PATH or common install locations)
2. **Creates** the `figviewer` env from `environment.yaml` if it does not exist  
   (optional `--update-env` refreshes an existing env)
3. `pip install -e .` into that env (editable — code updates track the clone until you freeze)
4. Runs [`install_app.sh`](../packaging/macos/install_app.sh) to write `~/Applications/Figure Gallery.app`

Still requires conda and a clone of the repo. It does **not** replace a frozen app; it removes the “read the README and type four commands” tax.

| Approach | User needs | Portable `.app` alone? |
|----------|------------|-------------------------|
| Manual thin install | conda + follow README | No |
| **Bootstrap script** | conda + clone + one script | No |
| conda-pack / micromamba hybrid | Copy a folder | Mostly |
| Frozen (PyInstaller etc.) | Nothing else | Yes (same arch) |

---

## 7. Practical decision guide

**Stay on the thin launcher / bootstrap if:**

- You’re the main user, or collaborators already use conda
- The machine can keep a clone + `figviewer` env
- You want fast iteration and a Dock icon

**Invest in frozen (or conda-pack hybrid) if:**

- Someone else should run it without setting up Python / conda
- You want a versioned “release” artifact
- You’re okay rebuilding and testing on a clean Mac

**Do not expect** the thin `.app` alone to be that portable artifact—by design it isn’t.

---

## 8. Glossary

| Term | Meaning |
|------|---------|
| **Bundle** | The `.app` directory tree |
| **Launch Services** | macOS subsystem that opens apps by bundle id / path |
| **Thin launcher** | Tiny stub that calls an external interpreter |
| **Frozen app** | Bundle that embeds (most of) its runtime |
| **Notarization** | Apple cloud check for Developer ID–signed apps |
| **Editable install** | `pip install -e .` — imports track your source tree |
| **Bootstrap install** | One script: create env (if needed) + editable install + thin `.app` |

---

## See also

- Install commands: [README — macOS app](../README.md#macos-app-spotlight--dock)
- Icon prompts: [`packaging/macos/LOGO_PROMPTS.md`](../packaging/macos/LOGO_PROMPTS.md)
- Combined-app UX backlog: [`docs/desktop-figureviewer-refinement.md`](desktop-figureviewer-refinement.md)
