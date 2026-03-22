"""Bump version in pyproject.toml, __init__.py, and add CHANGELOG entry."""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_current_version():
    """Read the current version from pyproject.toml."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    content = pyproject.read_text()
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    return match.group(1) if match else "0.0.0"


def set_version(new_version):
    """Update version in pyproject.toml and __init__.py."""
    # Update pyproject.toml
    pyproject = PROJECT_ROOT / "pyproject.toml"
    content = pyproject.read_text()
    content = re.sub(r'(version\s*=\s*)"[^"]+"', f'\\1"{new_version}"', content)
    pyproject.write_text(content)

    # Update __init__.py
    init = PROJECT_ROOT / "src" / "instream" / "__init__.py"
    content = init.read_text()
    content = re.sub(
        r'__version__\s*=\s*"[^"]+"', f'__version__ = "{new_version}"', content
    )
    init.write_text(content)

    print(f"Version bumped to {new_version}")
    print("Next steps:")
    print(f"  1. Update CHANGELOG.md with changes under [{new_version}]")
    print(f"  2. git commit -m 'release: v{new_version}'")
    print(f"  3. git tag -a v{new_version} -m 'Release {new_version}'")


def bump(part):
    """Bump the specified version part (major, minor, or patch)."""
    current = get_current_version()
    major, minor, patch = [int(x) for x in current.split(".")]
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1
    else:
        print(f"Unknown part: {part}. Use major, minor, or patch.")
        sys.exit(1)
    new = f"{major}.{minor}.{patch}"
    set_version(new)
    return new


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Current version: {get_current_version()}")
        print("Usage: python bump_version.py [major|minor|patch]")
        sys.exit(0)
    bump(sys.argv[1])
