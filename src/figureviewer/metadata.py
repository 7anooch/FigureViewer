from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import streamlit as st

from figureviewer.figures import PanelConfig

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

METADATA_BASENAMES = ["_figuregroup", "figuregroup", "metadata", "description"]


def load_metadata(directory: Path) -> Dict[str, str]:
    candidates = []
    for base in METADATA_BASENAMES:
        candidates.extend([
            directory / f"{base}.yaml",
            directory / f"{base}.yml",
            directory / f"{base}.json",
            directory / f"{base}.txt",
        ])
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.suffix in {".yaml", ".yml"} and yaml is not None:
                data = yaml.safe_load(path.read_text()) or {}
                return data if isinstance(data, dict) else {"description": str(data)}
            if path.suffix == ".json":
                data = json.loads(path.read_text())
                return data if isinstance(data, dict) else {"description": str(data)}
            if path.suffix == ".txt":
                return {"description": path.read_text()}
        except Exception as exc:
            return {"description": f"Could not read metadata file {path.name}: {exc}"}
    return {}


def save_metadata(directory: Path, data: Dict[str, str], fmt: str = "yaml") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path = directory / "_figuregroup.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return path
    if fmt == "txt":
        path = directory / "_figuregroup.txt"
        lines = []
        for k, v in data.items():
            if k == "description":
                lines.append(str(v))
            elif v:
                lines.append(f"\n[{k}]\n{v}")
        path.write_text("\n".join(lines).strip() + "\n")
        return path
    path = directory / "_figuregroup.yaml"
    if yaml is None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return path


def render_metadata_editor(panel: PanelConfig, key_prefix: str) -> None:
    meta = load_metadata(panel.directory)
    with st.expander(f"Description / metadata: {panel.label}", expanded=False):
        description = st.text_area(
            "Description",
            value=str(meta.get("description", "")),
            key=f"{key_prefix}_desc",
            height=100,
        )
        col1, col2 = st.columns(2)
        with col1:
            commit_hash = st.text_input(
                "Commit hash",
                value=str(meta.get("commit_hash", "")),
                key=f"{key_prefix}_commit",
            )
            generating_script = st.text_input(
                "Generating script / notebook",
                value=str(meta.get("generating_script", "")),
                key=f"{key_prefix}_script",
            )
        with col2:
            source_data = st.text_input(
                "Source data path",
                value=str(meta.get("source_data", "")),
                key=f"{key_prefix}_source",
            )
            tags = st.text_input(
                "Tags",
                value=str(meta.get("tags", "")),
                key=f"{key_prefix}_tags",
            )
        notes = st.text_area(
            "Notes",
            value=str(meta.get("notes", "")),
            key=f"{key_prefix}_notes",
            height=80,
        )
        fmt = st.selectbox("Save format", ["yaml", "json", "txt"], key=f"{key_prefix}_fmt")
        if st.button("Save metadata", key=f"{key_prefix}_save"):
            path = save_metadata(
                panel.directory,
                {
                    "description": description,
                    "commit_hash": commit_hash,
                    "generating_script": generating_script,
                    "source_data": source_data,
                    "tags": tags,
                    "notes": notes,
                },
                fmt=fmt,
            )
            st.success(f"Saved {path}")
