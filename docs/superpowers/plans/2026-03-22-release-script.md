# Release Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual multi-step release process with a single `python scripts/release.py minor` command that bumps version, generates CHANGELOG entries from git commits, updates README metrics, commits, and tags.

**Architecture:** Single script `scripts/release.py` that: (1) parses git log since last tag to build CHANGELOG section, (2) bumps version in `pyproject.toml` + `__init__.py`, (3) runs pytest to gate the release, (4) updates README metrics via regex replacement, (5) creates the release commit and annotated tag. Subsumes the existing `bump_version.py`.

**Tech Stack:** Python stdlib only (subprocess, re, pathlib, datetime, sys). No external dependencies.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/release.py` | Create | Release automation: version bump, CHANGELOG generation, README update, commit + tag |
| `scripts/bump_version.py` | Delete | Superseded by `release.py` |
| `tests/test_release.py` | Create | Unit tests for changelog generation and version bump logic |

---

### Task 1: Changelog Generator

**Files:**
- Create: `scripts/release.py` (changelog functions only)
- Test: `tests/test_release.py`

- [ ] **Step 1: Write failing test for commit parsing**

```python
"""Tests for release script helpers."""
import pytest
import sys
from pathlib import Path

# Add scripts to path so we can import release module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from release import parse_commits, format_changelog_section


def test_parse_commits_groups_by_type():
    raw = [
        "feat: add JAX backend for hydraulics",
        "feat: implement FEM mesh reader",
        "fix: case-insensitive column matching",
        "docs: update README with benchmarks",
        "test: add FEM mesh tests",
        "chore: improve .gitignore",
    ]
    grouped = parse_commits(raw)
    assert grouped["Added"] == [
        "Add JAX backend for hydraulics",
        "Implement FEM mesh reader",
    ]
    assert grouped["Fixed"] == ["Case-insensitive column matching"]
    assert grouped["Changed"] == ["Improve .gitignore"]
    assert "docs" not in grouped  # docs mapped to Changed or excluded


def test_parse_commits_strips_scope():
    raw = ["feat(jax): vectorized growth kernel"]
    grouped = parse_commits(raw)
    assert grouped["Added"] == ["Vectorized growth kernel"]


def test_parse_commits_skips_release_commits():
    raw = ["release: v0.8.0 — JAX backend", "feat: new thing"]
    grouped = parse_commits(raw)
    assert "Added" in grouped
    assert len(grouped["Added"]) == 1


def test_format_changelog_section():
    grouped = {
        "Added": ["JAX backend", "FEM mesh reader"],
        "Fixed": ["Column matching"],
    }
    section = format_changelog_section("0.9.0", "2026-03-22", grouped)
    assert "## [0.9.0] - 2026-03-22" in section
    assert "### Added" in section
    assert "- JAX backend" in section
    assert "### Fixed" in section
    assert "- Column matching" in section
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_release.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'release'`

- [ ] **Step 3: Implement parse_commits and format_changelog_section**

In `scripts/release.py`:

```python
"""Automated release: version bump, CHANGELOG, README update, commit + tag.

Usage:
    python scripts/release.py patch     # 0.8.0 -> 0.8.1
    python scripts/release.py minor     # 0.8.0 -> 0.9.0
    python scripts/release.py major     # 0.8.0 -> 1.0.0
    python scripts/release.py --dry-run minor   # preview without changes
"""

import re
import subprocess
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Conventional-commit prefix -> CHANGELOG section
PREFIX_MAP = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Performance",
    "test": "Testing",
    "docs": "Changed",
    "chore": "Changed",
    "refactor": "Changed",
    "ci": "Changed",
}

# Section display order
SECTION_ORDER = ["Added", "Changed", "Fixed", "Performance", "Testing", "Validation"]


def parse_commits(lines):
    """Group conventional-commit messages into CHANGELOG sections.

    Returns dict mapping section name -> list of description strings.
    Skips release commits. Strips optional (scope) prefix.
    Capitalizes the first letter of each description.
    """
    sections = {}
    for line in lines:
        # Skip release commits
        if line.startswith("release:"):
            continue
        # Match "type(scope): description" or "type: description"
        m = re.match(r"(\w+)(?:\([^)]*\))?:\s*(.+)", line)
        if not m:
            continue
        prefix, desc = m.group(1), m.group(2)
        section = PREFIX_MAP.get(prefix)
        if section is None:
            continue
        # Capitalize first letter
        desc = desc[0].upper() + desc[1:] if desc else desc
        sections.setdefault(section, []).append(desc)
    return sections


def format_changelog_section(version, date_str, grouped):
    """Format a CHANGELOG section from grouped commits."""
    lines = [f"## [{version}] - {date_str}", ""]
    for section in SECTION_ORDER:
        if section not in grouped:
            continue
        lines.append(f"### {section}")
        for item in grouped[section]:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_release.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "<project>" add scripts/release.py tests/test_release.py
git -C "<project>" commit -m "feat: add changelog generator for release script"
```

---

### Task 2: Version Bump + CHANGELOG Insert

**Files:**
- Modify: `scripts/release.py`
- Modify: `tests/test_release.py`

- [ ] **Step 1: Write failing tests for version bump and CHANGELOG insertion**

Append to `tests/test_release.py`:

```python
def test_bump_version_minor():
    from release import bump_version_string
    assert bump_version_string("0.8.0", "minor") == "0.9.0"
    assert bump_version_string("0.8.0", "patch") == "0.8.1"
    assert bump_version_string("0.8.0", "major") == "1.0.0"


def test_insert_changelog_entry(tmp_path):
    from release import insert_changelog_entry

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\nSome preamble.\n\n## [0.8.0] - 2026-03-22\n\n### Added\n- Old stuff\n"
    )
    new_section = "## [0.9.0] - 2026-03-22\n\n### Added\n- New stuff\n"
    insert_changelog_entry(changelog, new_section)
    content = changelog.read_text()
    # New section appears before old
    assert content.index("[0.9.0]") < content.index("[0.8.0]")
    assert "---" in content  # separator between versions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_release.py::test_bump_version_minor tests/test_release.py::test_insert_changelog_entry -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement bump_version_string and insert_changelog_entry**

Add to `scripts/release.py`:

```python
def bump_version_string(current, part):
    """Bump a semver string. Returns new version string."""
    major, minor, patch = (int(x) for x in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    elif part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Unknown part: {part}. Use major, minor, or patch.")


def get_current_version():
    """Read version from pyproject.toml."""
    content = (PROJECT_ROOT / "pyproject.toml").read_text()
    m = re.search(r'version\s*=\s*"([^"]+)"', content)
    return m.group(1) if m else "0.0.0"


def set_version(new_version):
    """Update version in pyproject.toml and __init__.py."""
    for path, pattern, replacement in [
        (
            PROJECT_ROOT / "pyproject.toml",
            r'(version\s*=\s*)"[^"]+"',
            f'\\1"{new_version}"',
        ),
        (
            PROJECT_ROOT / "src" / "instream" / "__init__.py",
            r'__version__\s*=\s*"[^"]+"',
            f'__version__ = "{new_version}"',
        ),
    ]:
        content = path.read_text()
        content = re.sub(pattern, replacement, content)
        path.write_text(content)


def insert_changelog_entry(changelog_path, new_section):
    """Insert a new CHANGELOG section before the first existing ## entry."""
    content = changelog_path.read_text()
    # Find the first version heading
    m = re.search(r"^## \[", content, re.MULTILINE)
    if m:
        before = content[: m.start()]
        after = content[m.start() :]
        content = before + new_section + "\n---\n\n" + after
    else:
        content += "\n" + new_section
    changelog_path.write_text(content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_release.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "<project>" add scripts/release.py tests/test_release.py
git -C "<project>" commit -m "feat: add version bump and CHANGELOG insertion"
```

---

### Task 3: README Metrics Updater

**Files:**
- Modify: `scripts/release.py`
- Modify: `tests/test_release.py`

- [ ] **Step 1: Write failing test for README update**

Append to `tests/test_release.py`:

```python
def test_update_readme_metrics(tmp_path):
    from release import update_readme_metrics

    readme = tmp_path / "README.md"
    readme.write_text(
        "# inSTREAM-py\n\n"
        "**v0.7.0** -- InSTREAM-SD complete.\n\n"
        "| Tests           | 455                            |\n"
        "| Step time       | 48 ms (Example A, Numba JIT)   |\n"
        "- An optional **JAX** backend for GPU acceleration (planned)\n"
        "### Planned\n\n"
        "- JAX GPU backend (stub interface ready)\n"
        "- FEM mesh reader for River2D/GMSH (stub ready)\n"
        "- Angler harvest module\n"
    )
    update_readme_metrics(
        readme,
        new_version="0.9.0",
        test_count=472,
        completed_items=["JAX GPU backend with vectorized kernels", "FEM mesh reader (River2D/GMSH via meshio)"],
        remove_planned=["JAX GPU backend", "FEM mesh reader"],
    )
    content = readme.read_text()
    assert "**v0.9.0**" in content
    assert "472" in content
    assert "JAX GPU backend (stub interface ready)" not in content
    assert "FEM mesh reader for River2D/GMSH (stub ready)" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_release.py::test_update_readme_metrics -v`
Expected: FAIL

- [ ] **Step 3: Implement update_readme_metrics**

Add to `scripts/release.py`:

```python
def get_test_count():
    """Run pytest --co -q and count collected tests."""
    result = subprocess.run(
        ["conda", "run", "-n", "shiny", "python", "-m", "pytest", "tests/", "--co", "-q"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    # Last meaningful line: "N tests collected"
    for line in result.stdout.strip().splitlines()[::-1]:
        m = re.search(r"(\d+) tests? collected", line)
        if m:
            return int(m.group(1))
    return 0


def update_readme_metrics(readme_path, new_version, test_count,
                          completed_items=None, remove_planned=None):
    """Update version badge, test count, and project status in README."""
    content = readme_path.read_text()

    # Update version in status line: **v0.X.Y** -- ...
    content = re.sub(
        r"\*\*v\d+\.\d+\.\d+\*\*",
        f"**v{new_version}**",
        content,
    )

    # Update test count in metrics table
    content = re.sub(
        r"(\|\s*Tests\s*\|\s*)\d+",
        f"\\g<1>{test_count}",
        content,
    )

    # Move items from Planned to Completed
    if completed_items:
        # Find "### Completed" section and append items
        completed_block = "\n".join(f"- {item}" for item in completed_items)
        content = re.sub(
            r"(### Planned)",
            f"{completed_block}\n\n\\1",
            content,
        )

    # Remove items from Planned section
    if remove_planned:
        for item in remove_planned:
            # Remove lines matching the planned item (fuzzy: startswith after "- ")
            content = re.sub(
                rf"^- {re.escape(item)}.*\n",
                "",
                content,
                flags=re.MULTILINE,
            )

    readme_path.write_text(content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_release.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "<project>" add scripts/release.py tests/test_release.py
git -C "<project>" commit -m "feat: add README metrics updater to release script"
```

---

### Task 4: Main Release Orchestrator + Dry-Run

**Files:**
- Modify: `scripts/release.py`
- Delete: `scripts/bump_version.py`

- [ ] **Step 1: Implement the main() orchestrator**

Add to `scripts/release.py`:

```python
def get_commits_since_last_tag():
    """Get commit subject lines since the last annotated tag."""
    result = subprocess.run(
        ["git", "log", "--oneline", "--format=%s", "HEAD"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        return []
    # Try to get commits since last tag
    tags = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if tags.returncode == 0 and tags.stdout.strip():
        last_tag = tags.stdout.strip()
        result = subprocess.run(
            ["git", "log", f"{last_tag}..HEAD", "--oneline", "--format=%s"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
    return result.stdout.strip().splitlines() if result.stdout.strip() else []


def run_tests():
    """Run pytest and return True if all tests pass."""
    print("Running tests...")
    result = subprocess.run(
        ["conda", "run", "-n", "shiny", "python", "-m", "pytest", "tests/", "-q", "--tb=short"],
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode == 0


def git_commit_and_tag(version, dry_run=False):
    """Stage changed files, commit, and create annotated tag."""
    files = ["pyproject.toml", "src/instream/__init__.py", "CHANGELOG.md", "README.md"]
    if dry_run:
        print(f"[dry-run] Would stage: {', '.join(files)}")
        print(f"[dry-run] Would commit: 'release: v{version}'")
        print(f"[dry-run] Would tag: v{version}")
        return
    for f in files:
        subprocess.run(["git", "add", f], cwd=str(PROJECT_ROOT), check=True)
    subprocess.run(
        ["git", "commit", "-m", f"release: v{version}"],
        cwd=str(PROJECT_ROOT), check=True,
    )
    subprocess.run(
        ["git", "tag", "-a", f"v{version}", "-m", f"Release {version}"],
        cwd=str(PROJECT_ROOT), check=True,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Release inSTREAM-py")
    parser.add_argument("part", choices=["major", "minor", "patch"],
                        help="Version part to bump")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without modifying files")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Skip running the test suite")
    args = parser.parse_args()

    current = get_current_version()
    new_version = bump_version_string(current, args.part)
    today = date.today().isoformat()

    print(f"Releasing: v{current} -> v{new_version}")

    # 1. Gate on tests
    if not args.skip_tests and not args.dry_run:
        if not run_tests():
            print("ERROR: Tests failed. Fix before releasing.")
            sys.exit(1)
        print("All tests passed.")

    # 2. Gather commits and build changelog
    commits = get_commits_since_last_tag()
    if not commits:
        print("WARNING: No commits found since last tag.")
    grouped = parse_commits(commits)
    changelog_section = format_changelog_section(new_version, today, grouped)

    print(f"\n--- CHANGELOG entry ---\n{changelog_section}")

    if args.dry_run:
        print(f"\n[dry-run] Would bump {current} -> {new_version}")
        print("[dry-run] Would update CHANGELOG.md and README.md")
        print("[dry-run] No files modified.")
        return

    # 3. Bump version
    set_version(new_version)
    print(f"Version bumped: {current} -> {new_version}")

    # 4. Update CHANGELOG
    insert_changelog_entry(PROJECT_ROOT / "CHANGELOG.md", changelog_section)
    print("CHANGELOG.md updated.")

    # 5. Update README metrics
    test_count = get_test_count()
    update_readme_metrics(PROJECT_ROOT / "README.md", new_version, test_count)
    print(f"README.md updated (tests: {test_count}).")

    # 6. Commit and tag
    git_commit_and_tag(new_version)
    print(f"\nRelease v{new_version} complete!")
    print(f"Push with: git push origin main --tags")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Delete old bump_version.py**

```bash
git -C "<project>" rm scripts/bump_version.py
```

- [ ] **Step 3: Test dry-run manually**

Run: `conda run -n shiny python scripts/release.py --dry-run minor`
Expected: Prints changelog preview and "[dry-run]" messages, no files changed.

- [ ] **Step 4: Commit**

```bash
git -C "<project>" add scripts/release.py
git -C "<project>" commit -m "feat: add release orchestrator with dry-run, remove bump_version.py"
```

---

### Task 5: End-to-End Verification

- [ ] **Step 1: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`
Expected: All tests pass (including test_release.py)

- [ ] **Step 2: Dry-run the release**

Run: `conda run -n shiny python scripts/release.py --dry-run minor`
Expected: Clean preview of v0.9.0 changelog with all commits since v0.8.0

- [ ] **Step 3: Commit all remaining changes**

```bash
git -C "<project>" add -A
git -C "<project>" commit -m "chore: release script end-to-end verification"
```
