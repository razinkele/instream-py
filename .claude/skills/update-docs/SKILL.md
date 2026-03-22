---
name: update-docs
description: Update all project documentation (README, CHANGELOG, API reference, user manual) after a version bump or significant changes. Use when releasing a new version or after completing a batch of features.
---

# Update Documentation Skill

When invoked via `/update-docs`, perform these steps in order:

## 1. Gather Changes

- Read the current version from `pyproject.toml`
- Run `git -C "<project_root>" log --oneline <last_tag>..HEAD` to get commits since the last release tag
- If no previous tag exists, use the full log
- Categorize commits by type: features, fixes, performance, refactoring, docs, tests, build

## 2. Update CHANGELOG.md

- Open `CHANGELOG.md` in the project root (create if it does not exist)
- Add a new section at the top under `## [<version>] - <YYYY-MM-DD>`
- Group entries under these headings as applicable:
  - **Added** -- new features
  - **Changed** -- changes to existing functionality
  - **Fixed** -- bug fixes
  - **Performance** -- performance improvements
  - **Removed** -- removed features
  - **Infrastructure** -- build, CI, tooling changes
- Each entry should be a single line starting with `- ` and referencing the commit if useful
- Keep the format consistent with existing entries

## 3. Update README.md

- Update the version badge or version reference at the top if present
- Update the **Status** or **Current State** section to reflect newly completed work
- Update the performance benchmarks table if any performance-related changes were made
- Update the feature checklist or roadmap section to mark completed items
- Do NOT remove or rewrite sections that are still accurate

## 4. Update API Reference (if applicable)

- Only if public API surface changed (new classes, renamed methods, changed signatures)
- Update `docs/api/` files or docstrings as needed
- Ensure all public classes and functions have docstrings

## 5. Update Version References in Docs

- Search for old version strings in all `.md` and `.rst` files
- Replace with the new version where appropriate (skip historical references in CHANGELOG)

## 6. Commit Documentation Updates

- Stage all modified documentation files
- Commit with message: `docs: update documentation for v<version>`
- Do NOT create a tag -- tagging is done separately during the release process

## Usage Notes

- Invoke this skill after running `python scripts/bump_version.py [major|minor|patch]`
- The version bump script updates `pyproject.toml` and `src/instream/__init__.py`
- This skill then updates all documentation to match the new version
- After both steps, create the release tag: `git tag -a v<version> -m "Release <version>"`

## Release Checklist

1. `python scripts/bump_version.py [major|minor|patch]`
2. `git commit -m "release: v<version>"`
3. `/update-docs`
4. `git tag -a v<version> -m "Release <version>"`
5. `git push origin main --tags`
