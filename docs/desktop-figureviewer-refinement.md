# Desktop FigureViewer — refinement outline

**Status:** backlog (not scheduled)  
**Context:** Capture gaps vs polished Figure Gallery UX and vs Streamlit FigureViewer, so a future merge into one `.app` is less painful.  
**Related:** Gallery focus/shortcuts, HiDPI zoom viewport, adaptive cache/prefetch, thin macOS `.app` packaging.

Desktop today is a workable MVP port of the multi-panel Streamlit workflow onto Qt. It reuses Gallery’s loader/cache/nav and shared `display_state` / export helpers, but does **not** yet carry Gallery’s interaction DNA.

---

## Correctness blockers (fix first when work resumes)

| Issue | Where | Fix sketch | Status |
|-------|--------|------------|--------|
| **Export Save crashes** — `self._titles = QTextEdit()` shadows method `_titles()`; Save calls `self._titles()` → TypeError | `desktop/export_panel.py` | Rename widget → `_titles_edit`; method → `_resolve_titles()` | Done |
| **Stale loader races** — mid-load refresh can leave cells on “Loading…” forever | `desktop/viewport.py` `_on_loaded` / `_on_failed` | Ignore stale path **and** drain/restart pending queue (mirror Gallery prefetch resume) | Done |
| **←/→ steal focus** — window-level shortcuts fight column browser, lists, text fields | `desktop/main_window.py` | Scope nav to viewport (`WidgetWithChildrenShortcut`); `` ` `` toggle browser ↔ figures (Gallery pattern) | Done |
| **Unsync + global nav** — Left/Right move slider but figures don’t change when `sync_mode=False` | `main_window` + `display_state` | No-op global nav in unsync, or define explicit behavior; keep per-panel sliders as source of truth | Done |
| **Natural / custom HiDPI wrong** — Retina can show tiny or soft images outside fill mode | `desktop/viewport.py` `_PanelCell.set_image` | Always scale with `logical * dpr` + `setDevicePixelRatio` (Gallery viewport math) | Done |

---

## Workstreams (Gallery lessons → Viewer)

### A. Interaction parity with Gallery — high impact

Carry over patterns already proven in Gallery:

1. ~~**Scoped shortcuts + focus toggle** (`` ` ``) between column browser and figure grid~~ **done**  
2. ~~**Space = next** when figures focused~~ **done**  
3. ~~**Status bar + empty-state shortcut sheet** (thin adapt of `figuregallery.shortcuts`)~~ **done**  
4. ~~**Keyboard column browser** — ↑/↓ in column, ←/→ change column, Enter/Space toggle panel~~ **superseded** — desktop now uses Gallery-style hidden nearby navigator (`DirectoryNavigator`)  

### B. Viewport: zoom + resize — high impact

Gallery invested here for “leave one figure open as reference / flip quickly”:

- Pinch / ⌘-scroll zoom, pan when zoomed, dbl-click / ⌘0 reset — **done** (shared across all panels)  
- Decision: **shared multi-panel zoom** (compare workflow) — per-panel focus zoom removed  
- ~~`resizeEvent` / post-layout refit for fill mode~~ **done**  

### C. Cache / prefetch under multi-panel cost — high impact

- ~~Cache size 12 is too small when each “page” is N panels × DPI/trim variants~~ **done** (BrowsePacing + panels×radius)  
- ~~Prefetch **next/prev index’s full panel set**, not a single path~~ **done**  
- ~~Reuse or generalize `BrowsePacing` with budget ≈ `panels × radius`~~ **done**  
- ~~Clear pending cleanly on DPI / trim / panel-set change~~ **done**  

### D. Streamlit feature parity (selective) — medium

| Gap | Notes | Status |
|-----|--------|--------|
| Metadata for **all** panels | Tabs/stack; today only `panels[0]` | Done |
| Missing-dir / no-common-stems warnings | Streamlit is explicit; desktop goes silent/generic | Done |
| Manual paths as multiline | Placeholder says “one per line”; widget is `QLineEdit` → `QPlainTextEdit` | Done |
| Batch export errors | Don’t `except: continue` silently; summarize failures | Done |
| `pdf_mode` embed | State exists, no UI — drop or open externally | Open |

### E. Chrome / packaging readiness — lower until merge

- ~~Persist a small sticky set (display mode, DPI, last export dir) beyond browse root~~ **done**  
- ~~Reveal in Finder; clearer Open-root errors~~ **done**  
- When merging with Gallery: one app name (**FigureViewer**), modes **Compare** / **Browse**; one `.app` installer  

---

## Suggested order when time opens up

1. ~~**A0 blockers** — export `_titles`, loader race, shortcut scoping (1 sitting)~~ **done**  
2. ~~**HiDPI + resize refit** — fill-mode `resizeEvent` / post-layout refit~~ **done**  
3. ~~**Focus toggle + keyboard browser** — `` ` ``, Space=next, ↑/↓/←/→/Enter in columns~~ **done**  
4. ~~**Zoom (all panels)** — shared pinch / ⌘-scroll / ⌘0~~ **done**  
5. ~~**Prefetch / pacing** — snappy multi-panel flipping~~ **done**  
6. ~~**Metadata tabs + export error surfacing**~~ **done** (also multiline paths + missing-dir warnings)  
7. **Merge shell** with Gallery Browse mode + single macOS `.app`  
8. ~~**Status bar + empty-state shortcut sheet** · sticky prefs · Reveal in Finder~~ **done** · remaining: `pdf_mode` decision  

---

## Out of scope for this outline

- Implementing the above  
- Redesigning Streamlit UI  
- Freezing a redistributable binary (thin conda `.app` already exists for Gallery only)

## Quick verification checklist (after fixes)

- [x] Save current / Save all export without traceback *(unit: titles not shadowed)*  
- [x] Flip figures while focus in column list does **not** steal ←/→ (or `` ` `` returns focus cleanly) *(scoped shortcuts + backtick toggle)*  
- [x] Natural size looks correct on Retina *(logical × dpr scaling)*  
- [x] Rapid ←/→ across a 4-panel set rarely shows stuck “Loading…” *(stale load resumes queue)*  
- [x] Unsync: per-panel sliders work; global nav behavior is intentional and documented in-app  
