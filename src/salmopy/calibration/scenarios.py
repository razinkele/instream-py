"""Scenario manager — save/fork/compare/export calibration scenarios.

Adapted from osmopy's `scenarios.py`. A Scenario wraps one overrides
dict + metadata (name, tags, parent). Manager persists scenarios as
JSON under a directory, supports fork (child with partial overrides)
and ZIP export/import for sharing calibration runs.

Security: path names are validated to prevent path-traversal attacks
when loading externally-supplied ZIP archives.
"""
from __future__ import annotations

import json
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-\. ]{1,64}$")


@dataclass
class Scenario:
    """One named calibration scenario.

    Attributes
    ----------
    name : str
        Scenario identifier. Must match ``[A-Za-z0-9_\\-. ]{1,64}``.
    overrides : dict
        {dot_path: physical_value} — same shape the calibration layer
        consumes.
    tags : list[str]
        Free-form labels.
    parent_scenario : str, optional
        Name of the scenario this was forked from.
    metadata : dict
        Free-form scalar/string key-values (NetLogo seed, date, etc.).
    created : str
        ISO-8601 UTC timestamp; auto-filled by ScenarioManager.save().
    """
    name: str
    overrides: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    parent_scenario: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "overrides": dict(self.overrides),
            "tags": list(self.tags),
            "parent_scenario": self.parent_scenario,
            "metadata": dict(self.metadata),
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Scenario":
        return cls(
            name=str(d["name"]),
            overrides=dict(d.get("overrides", {})),
            tags=list(d.get("tags", [])),
            parent_scenario=d.get("parent_scenario"),
            metadata=dict(d.get("metadata", {})),
            created=str(d.get("created", "")),
        )


def _validate_name(name: str) -> None:
    if not _SAFE_NAME.match(name):
        raise ValueError(
            f"Scenario name must match {_SAFE_NAME.pattern!r}; got {name!r}"
        )


class ScenarioManager:
    """Per-directory scenario store. One JSON file per scenario.

    Parameters
    ----------
    root : Path
        Directory holding `<name>.json` files. Created if absent.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        _validate_name(name)
        return self.root / f"{name}.json"

    def save(self, scenario: Scenario) -> Path:
        """Atomic write of scenario JSON. Stamps `created` if empty."""
        _validate_name(scenario.name)
        if not scenario.created:
            scenario.created = datetime.now(timezone.utc).isoformat()
        path = self._path(scenario.name)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(scenario.to_dict(), f, indent=2, default=str)
        os.replace(tmp, path)
        return path

    def load(self, name: str) -> Scenario:
        path = self._path(name)
        with open(path, "r", encoding="utf-8") as f:
            return Scenario.from_dict(json.load(f))

    def list(self) -> List[str]:
        """Scenario names available in this manager."""
        return sorted(p.stem for p in self.root.glob("*.json"))

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.exists():
            path.unlink()

    def fork(
        self,
        parent_name: str,
        child_name: str,
        *,
        overrides_update: Optional[Dict[str, float]] = None,
        tags_add: Optional[Sequence[str]] = None,
    ) -> Scenario:
        """Create a new scenario as a fork of `parent_name`.

        The child inherits all of parent's overrides + tags, then
        applies `overrides_update` (overwriting keys if present) and
        appends `tags_add`.
        """
        parent = self.load(parent_name)
        child_overrides = dict(parent.overrides)
        if overrides_update:
            child_overrides.update(overrides_update)
        child_tags = list(parent.tags)
        if tags_add:
            for t in tags_add:
                if t not in child_tags:
                    child_tags.append(t)
        child = Scenario(
            name=child_name,
            overrides=child_overrides,
            tags=child_tags,
            parent_scenario=parent_name,
            metadata=dict(parent.metadata),
        )
        self.save(child)
        return child

    def compare(self, a: str, b: str) -> Dict[str, Any]:
        """Return a dict describing the differences between two scenarios.

        Keys: only_in_a, only_in_b, changed (dict of key -> (a_val, b_val)).
        """
        sa = self.load(a)
        sb = self.load(b)
        keys_a = set(sa.overrides.keys())
        keys_b = set(sb.overrides.keys())
        common = keys_a & keys_b
        changed = {
            k: (sa.overrides[k], sb.overrides[k])
            for k in common
            if sa.overrides[k] != sb.overrides[k]
        }
        return {
            "only_in_a": {k: sa.overrides[k] for k in sorted(keys_a - keys_b)},
            "only_in_b": {k: sb.overrides[k] for k in sorted(keys_b - keys_a)},
            "changed": changed,
        }

    def export_all(self, zip_path: Path) -> Path:
        """Bundle every scenario JSON into a ZIP archive."""
        zip_path = Path(zip_path)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in self.root.glob("*.json"):
                zf.write(p, arcname=p.name)
        return zip_path

    def import_all(self, zip_path: Path, overwrite: bool = False) -> List[str]:
        """Restore scenarios from a ZIP archive.

        Raises ValueError on path-traversal attempts or invalid names.
        If overwrite=False, existing scenario files are skipped.
        Returns list of imported names.
        """
        imported: List[str] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                name_in_zip = info.filename
                # Path-traversal guard
                if "/" in name_in_zip or "\\" in name_in_zip or ".." in name_in_zip:
                    raise ValueError(
                        f"rejecting archive entry with path separator: {name_in_zip!r}"
                    )
                if not name_in_zip.endswith(".json"):
                    continue
                stem = Path(name_in_zip).stem
                _validate_name(stem)
                out = self.root / name_in_zip
                if out.exists() and not overwrite:
                    continue
                with zf.open(info) as src:
                    data = src.read()
                # Parse to validate it's a scenario JSON
                try:
                    payload = json.loads(data)
                    Scenario.from_dict(payload)
                except Exception as e:
                    raise ValueError(
                        f"archive entry {name_in_zip!r} failed to parse as Scenario: {e}"
                    )
                tmp = out.with_suffix(".json.tmp")
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, out)
                imported.append(stem)
        return imported
