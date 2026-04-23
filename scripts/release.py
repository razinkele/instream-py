"""Automated release: version bump, CHANGELOG, README update, commit + tag.

Usage:
    python scripts/release.py patch          # 0.8.0 -> 0.8.1
    python scripts/release.py minor          # 0.8.0 -> 0.9.0
    python scripts/release.py major          # 0.8.0 -> 1.0.0
    python scripts/release.py --dry-run minor  # preview without changes
    python scripts/release.py --push minor     # push after commit+tag
"""

import re
import subprocess
import sys
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
        if line.startswith("release:"):
            continue
        m = re.match(r"(\w+)(?:\([^)]*\))?:\s*(.+)", line)
        if not m:
            continue
        prefix, desc = m.group(1), m.group(2)
        section = PREFIX_MAP.get(prefix)
        if section is None:
            continue
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
    """Update version in pyproject.toml, __init__.py, and docs/source/conf.py."""
    for path, pattern, replacement in [
        (
            PROJECT_ROOT / "pyproject.toml",
            r'(version\s*=\s*)"[^"]+"',
            f'\\1"{new_version}"',
        ),
        (
            PROJECT_ROOT / "src" / "salmopy" / "__init__.py",
            r'__version__\s*=\s*"[^"]+"',
            f'__version__ = "{new_version}"',
        ),
        (
            PROJECT_ROOT / "docs" / "source" / "conf.py",
            r'(version\s*=\s*)"[^"]+"',
            f'\\1"{new_version}"',
        ),
        (
            PROJECT_ROOT / "docs" / "source" / "conf.py",
            r'(release\s*=\s*)"[^"]+"',
            f'\\1"{new_version}"',
        ),
    ]:
        if not path.exists():
            print(f"WARNING: {path} not found, skipping version update.")
            continue
        content = path.read_text()
        content = re.sub(pattern, replacement, content)
        path.write_text(content)


def insert_changelog_entry(changelog_path, new_section):
    """Insert a new CHANGELOG section before the first existing ## entry."""
    if not changelog_path.exists():
        header = (
            "# Changelog\n\n"
            "All notable changes to this project will be documented in this file.\n\n"
            "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),\n"
            "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).\n\n"
        )
        changelog_path.write_text(header + new_section)
        return
    content = changelog_path.read_text()
    m = re.search(r"^## \[", content, re.MULTILINE)
    if m:
        before = content[: m.start()]
        after = content[m.start() :]
        content = before + new_section + "\n---\n\n" + after
    else:
        content += "\n" + new_section
    changelog_path.write_text(content)


def get_test_count():
    """Run pytest --co -q and count collected tests."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--co", "-q"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    for line in result.stdout.strip().splitlines()[::-1]:
        m = re.search(r"(\d+) tests? collected", line)
        if m:
            return int(m.group(1))
    return 0


def update_readme_metrics(
    readme_path, new_version, test_count, completed_items=None, remove_planned=None
):
    """Update version badge, test count, and project status in README."""
    content = readme_path.read_text()

    # Update version in status line (first occurrence only)
    content = re.sub(
        r"\*\*v\d+\.\d+\.\d+\*\*",
        f"**v{new_version}**",
        content,
        count=1,
    )

    # Update version in shields.io release badge URL.
    # Previous release scripts missed this and the badge sat at v0.33.0
    # for 8 minor versions (Phase 5 fix, 2026-04-23).
    content = re.sub(
        r"release-v\d+\.\d+\.\d+-blue",
        f"release-v{new_version}-blue",
        content,
    )

    # Update test count in metrics table
    content = re.sub(
        r"(\|\s*Tests\s*\|\s*)\d+",
        f"\\g<1>{test_count}",
        content,
    )

    # Add completed items before Planned section
    if completed_items:
        completed_block = "\n".join(f"- {item}" for item in completed_items)
        content = re.sub(
            r"(### Planned)",
            f"{completed_block}\n\n\\1",
            content,
        )

    # Remove items from Planned section by substring match
    if remove_planned:
        for item in remove_planned:
            content = re.sub(
                rf"^- .*{re.escape(item)}.*\n",
                "",
                content,
                flags=re.MULTILINE,
            )

    readme_path.write_text(content)


def get_commits_since_last_tag():
    """Get commit subject lines since the last annotated tag."""
    tags = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    if tags.returncode == 0 and tags.stdout.strip():
        last_tag = tags.stdout.strip()
        result = subprocess.run(
            ["git", "log", f"{last_tag}..HEAD", "--format=%s"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
    else:
        print("WARNING: No tags found. Using all commits.")
        result = subprocess.run(
            ["git", "log", "--format=%s"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
    return result.stdout.strip().splitlines() if result.stdout.strip() else []


def run_tests():
    """Run pytest and return True if all tests pass."""
    print("Running tests...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"],
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode == 0


def verify_sphinx_build():
    """Run Sphinx build and return True if it succeeds."""
    print("Verifying Sphinx documentation build...")
    conf_py = PROJECT_ROOT / "docs" / "source" / "conf.py"
    if not conf_py.exists():
        print("WARNING: docs/source/conf.py not found, skipping Sphinx verification.")
        return True
    result = subprocess.run(
        [
            sys.executable, "-m", "sphinx",
            "-b", "html",
            str(PROJECT_ROOT / "docs" / "source"),
            str(PROJECT_ROOT / "docs" / "_build" / "html"),
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        print("WARNING: Sphinx build failed (non-blocking):")
        print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        return False
    print("Sphinx build succeeded.")
    return True


def git_commit_and_tag(version, dry_run=False):
    """Stage changed files, commit, and create annotated tag."""
    files = [
        "pyproject.toml",
        "src/instream/__init__.py",
        "CHANGELOG.md",
        "README.md",
        "docs/source/conf.py",
    ]
    if dry_run:
        print(f"[dry-run] Would stage: {', '.join(files)}")
        print(f"[dry-run] Would commit: 'release: v{version}'")
        print(f"[dry-run] Would tag: v{version}")
        return
    for f in files:
        filepath = PROJECT_ROOT / f
        if filepath.exists():
            subprocess.run(["git", "add", f], cwd=str(PROJECT_ROOT), check=True)
    subprocess.run(
        ["git", "commit", "-m", f"release: v{version}"],
        cwd=str(PROJECT_ROOT),
        check=True,
    )
    subprocess.run(
        ["git", "tag", "-a", f"v{version}", "-m", f"Release {version}"],
        cwd=str(PROJECT_ROOT),
        check=True,
    )


def git_push(dry_run=False):
    """Push commits and tags to origin master."""
    if dry_run:
        print("[dry-run] Would push: git push origin master --tags")
        return
    print("Pushing to origin master with tags...")
    subprocess.run(
        ["git", "push", "origin", "master", "--tags"],
        cwd=str(PROJECT_ROOT),
        check=True,
    )
    print("Push complete.")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Release Salmopy-py")
    parser.add_argument(
        "part", choices=["major", "minor", "patch"], help="Version part to bump"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--skip-tests", action="store_true", help="Skip running the test suite"
    )
    parser.add_argument(
        "--push", action="store_true", help="Push to origin master with tags after release"
    )
    args = parser.parse_args()

    current = get_current_version()
    new_version = bump_version_string(current, args.part)
    today = date.today().isoformat()

    print(f"Releasing: v{current} -> v{new_version}")

    # 1. Gate on tests (skip in dry-run with warning)
    if args.dry_run:
        print("[dry-run] Skipping test suite.")
    elif not args.skip_tests:
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
        print(f"[dry-run] Would bump {current} -> {new_version}")
        print("[dry-run] Would update CHANGELOG.md, README.md, docs/source/conf.py")
        print("[dry-run] Would verify Sphinx build")
        git_commit_and_tag(new_version, dry_run=True)
        if args.push:
            git_push(dry_run=True)
        print("[dry-run] No files modified.")
        return

    # 3. Bump version (pyproject.toml + __init__.py + docs/source/conf.py)
    set_version(new_version)
    print(f"Version bumped: {current} -> {new_version}")

    # 4. Update CHANGELOG
    insert_changelog_entry(PROJECT_ROOT / "CHANGELOG.md", changelog_section)
    print("CHANGELOG.md updated.")

    # 5. Update README metrics
    test_count = get_test_count()
    update_readme_metrics(PROJECT_ROOT / "README.md", new_version, test_count)
    print(f"README.md updated (tests: {test_count}).")

    # 6. Verify Sphinx build (non-blocking)
    verify_sphinx_build()

    # 7. Commit and tag
    git_commit_and_tag(new_version)
    print(f"\nRelease v{new_version} complete!")

    # 8. Push if requested
    if args.push:
        git_push()
    else:
        print("Push with: git push origin master --tags")


if __name__ == "__main__":
    main()
