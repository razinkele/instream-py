# Release Automation Design Spec

**Date:** 2026-04-10
**Current version:** 0.14.0 (766 tests)
**Scope:** Automated versioning, README/CHANGELOG/API docs updates on release, CI/CD

---

## Motivation

Each release (v0.12.0, v0.13.0, v0.14.0) required manual CHANGELOG editing, README metric updates, version bumping in multiple files, and doc rebuilding. `scripts/release.py` already automates most of this, but lacks Sphinx doc generation and CI/CD workflows. This spec completes the automation.

---

## Component 1: Enhanced release.py

The existing `scripts/release.py` already handles:
- Semver bump (major/minor/patch) in `pyproject.toml` + `__init__.py`
- CHANGELOG generation from conventional commits
- README metrics update (version badge, test count)
- Git commit + annotated tag

**Additions:**

1. **`--push` flag**: After commit+tag, run `git push origin master --tags`
2. **Sphinx API docs rebuild**: Before committing, run `sphinx-build -b html docs/source docs/_build/html` and stage any generated API reference files (if committing built docs) OR just verify the build succeeds (if docs are built by CI)
3. **`docs/source/conf.py` version sync**: Update the `version` field in Sphinx conf.py to match the new release version
4. **Stage `docs/source/conf.py`** in the commit alongside pyproject.toml, __init__.py, CHANGELOG.md, README.md

**New release flow:**
```
python scripts/release.py minor --push
  1. Run tests (gate)
  2. Gather commits since last tag
  3. Bump version in pyproject.toml + __init__.py + docs/source/conf.py
  4. Generate CHANGELOG section from conventional commits
  5. Update README metrics (version, test count)
  6. Build Sphinx docs (verify success, don't commit _build/)
  7. Git add + commit + tag
  8. Git push origin master --tags (if --push)
```

---

## Component 2: Sphinx Documentation

Create `docs/source/` with autodoc for all public modules.

**Files:**
- `docs/source/conf.py` — Sphinx config with autodoc, napoleon, viewcode, RTD theme
- `docs/source/index.rst` — Landing page with TOC
- `docs/source/api.rst` — Autodoc directives for all key modules
- `docs/Makefile` — Convenience build target

**API reference structure (api.rst):**
```rst
API Reference
=============

Model
-----
.. automodule:: instream.model
   :members:

State
-----
.. automodule:: instream.state.trout_state
   :members:
.. automodule:: instream.state.redd_state
   :members:
.. automodule:: instream.state.life_stage
   :members:

Modules
-------
.. automodule:: instream.modules.growth
   :members:
.. automodule:: instream.modules.survival
   :members:
.. automodule:: instream.modules.behavior
   :members:
.. automodule:: instream.modules.spawning
   :members:
.. automodule:: instream.modules.migration
   :members:
.. automodule:: instream.modules.harvest
   :members:

Marine
------
.. automodule:: instream.marine.domain
   :members:
.. automodule:: instream.marine.config
   :members:

Configuration
-------------
.. automodule:: instream.io.config
   :members:

Backends
--------
.. automodule:: instream.backends
   :members:
```

`docs/_build/` is gitignored — docs are built by CI, not committed.

---

## Component 3: GitHub Actions Workflows

### 3.1 CI (`ci.yml`)

Triggers: push to master, pull requests.

```yaml
jobs:
  lint:
    - ruff check src/ tests/
  test:
    matrix: [python 3.11, 3.12, 3.13]
    - pip install -e ".[dev]"
    - pytest tests/ -q --tb=short --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
  test-slow:
    python: 3.12 only
    - pytest tests/ -q --tb=short -m slow --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

### 3.2 Release (`release.yml`)

Triggers: push of tag `v*`.

```yaml
jobs:
  publish:
    - hatch build
    - pypa/gh-action-pypi-publish (needs PYPI_API_TOKEN secret)
  github-release:
    - Extract CHANGELOG section for this version
    - Create GitHub Release with body = CHANGELOG excerpt
```

### 3.3 Docs (`docs.yml`)

Triggers: push to master (paths: `src/**`, `docs/**`).

```yaml
jobs:
  build-docs:
    - pip install -e ".[docs]"
    - sphinx-build -b html docs/source docs/_build/html
    - Deploy to GitHub Pages via actions/deploy-pages
```

---

## Modern README Structure

Restructure README.md with:

1. **Badges row**: Python version, license, CI status, PyPI version, docs link
2. **One-line description** + key image/diagram
3. **Quick Start** section (install + run)
4. **Features** list (concise)
5. **Architecture** summary (model.py 108 lines, 3 mixins, marine domain)
6. **Current Metrics** table (version, tests, validation, model.py lines)
7. **Documentation** link to GitHub Pages
8. **Contributing** section
9. **Citation** section (BibTeX for Railsback et al.)
10. **License**

The README update happens automatically via `release.py` (version + test count), but the restructuring is a one-time manual task in this plan.

---

## Files

### New
- `docs/source/conf.py`
- `docs/source/index.rst`
- `docs/source/api.rst`
- `docs/Makefile`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `.github/workflows/docs.yml`

### Modified
- `scripts/release.py` — add --push, Sphinx rebuild, conf.py version sync
- `README.md` — modern restructure with badges, quick start, architecture
- `.gitignore` — add `docs/_build/`
- `pyproject.toml` — verify `[project.optional-dependencies] docs` includes sphinx deps

---

## Testing

- `scripts/release.py --dry-run minor` works without modifying files
- `sphinx-build -b html docs/source docs/_build/html` succeeds
- CI workflow runs on push (verify via `gh run list`)
- Existing 766 tests still pass

---

## Timeline

| Task | Est. |
|------|------|
| Sphinx docs setup (conf.py, index.rst, api.rst, Makefile) | 1 hour |
| GitHub Actions (ci.yml, release.yml, docs.yml) | 1 hour |
| Enhanced release.py (--push, conf.py sync, Sphinx verify) | 1 hour |
| Modern README restructure | 1 hour |
| Testing + commit | 30 min |

**Total: ~4.5 hours / 1 day**
