"""Tests for release script helpers."""

import sys
from pathlib import Path

import pytest

# Add scripts to path so we can import release module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from release import (
    bump_version_string,
    format_changelog_section,
    insert_changelog_entry,
    parse_commits,
    update_readme_metrics,
)


class TestParseCommits:
    def test_groups_by_type(self):
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
        assert "Update README with benchmarks" in grouped["Changed"]
        assert "Improve .gitignore" in grouped["Changed"]

    def test_strips_scope(self):
        raw = ["feat(jax): vectorized growth kernel"]
        grouped = parse_commits(raw)
        assert grouped["Added"] == ["Vectorized growth kernel"]

    def test_skips_release_commits(self):
        raw = ["release: v0.8.0 — JAX backend", "feat: new thing"]
        grouped = parse_commits(raw)
        assert len(grouped["Added"]) == 1

    def test_skips_unknown_prefixes(self):
        raw = ["wip: half-done thing", "feat: real feature"]
        grouped = parse_commits(raw)
        assert "Added" in grouped
        assert len(grouped["Added"]) == 1

    def test_empty_input(self):
        assert parse_commits([]) == {}


class TestFormatChangelog:
    def test_basic_format(self):
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

    def test_section_order(self):
        grouped = {"Fixed": ["Bug"], "Added": ["Feature"]}
        section = format_changelog_section("1.0.0", "2026-01-01", grouped)
        assert section.index("### Added") < section.index("### Fixed")


class TestBumpVersion:
    def test_minor(self):
        assert bump_version_string("0.8.0", "minor") == "0.9.0"

    def test_patch(self):
        assert bump_version_string("0.8.0", "patch") == "0.8.1"

    def test_major(self):
        assert bump_version_string("0.8.0", "major") == "1.0.0"

    def test_major_resets_minor_patch(self):
        assert bump_version_string("1.3.7", "major") == "2.0.0"

    def test_invalid_part(self):
        with pytest.raises(ValueError):
            bump_version_string("0.8.0", "invalid")


class TestInsertChangelog:
    def test_inserts_before_existing(self, tmp_path):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\nSome preamble.\n\n"
            "## [0.8.0] - 2026-03-22\n\n### Added\n- Old stuff\n"
        )
        new_section = "## [0.9.0] - 2026-03-22\n\n### Added\n- New stuff\n"
        insert_changelog_entry(changelog, new_section)
        content = changelog.read_text()
        assert content.index("[0.9.0]") < content.index("[0.8.0]")
        assert "---" in content

    def test_creates_file_if_missing(self, tmp_path):
        changelog = tmp_path / "CHANGELOG.md"
        new_section = "## [0.1.0] - 2026-01-01\n\n### Added\n- First\n"
        insert_changelog_entry(changelog, new_section)
        content = changelog.read_text()
        assert "# Changelog" in content
        assert "[0.1.0]" in content


class TestUpdateReadme:
    def test_updates_version_and_tests(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(
            "# Salmopy-py\n\n"
            "**v0.7.0** -- InSTREAM-SD complete.\n\n"
            "| Tests           | 455                            |\n"
            "| Step time       | 48 ms (Example A, Numba JIT)   |\n"
        )
        update_readme_metrics(readme, "0.9.0", 472)
        content = readme.read_text()
        assert "**v0.9.0**" in content
        assert "472" in content

    def test_only_replaces_first_version(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(
            "**v0.7.0** -- current.\n\nPreviously **v0.6.0** was released.\n"
        )
        update_readme_metrics(readme, "0.9.0", 100)
        content = readme.read_text()
        assert "**v0.9.0**" in content
        assert "**v0.6.0**" in content  # second occurrence preserved

    def test_removes_planned_items(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(
            "**v0.7.0** -- current.\n\n"
            "| Tests           | 455                            |\n"
            "### Planned\n\n"
            "- JAX GPU backend (stub interface ready)\n"
            "- FEM mesh reader for River2D/GMSH (stub ready)\n"
            "- Angler harvest module\n"
        )
        update_readme_metrics(
            readme,
            "0.9.0",
            472,
            remove_planned=["JAX GPU backend", "FEM mesh reader"],
        )
        content = readme.read_text()
        assert "JAX GPU backend" not in content
        assert "FEM mesh reader" not in content
        assert "Angler harvest module" in content

    def test_adds_completed_items(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(
            "**v0.7.0** -- current.\n\n"
            "| Tests           | 455                            |\n"
            "### Planned\n\n"
            "- Angler harvest module\n"
        )
        update_readme_metrics(
            readme,
            "0.9.0",
            472,
            completed_items=["JAX GPU backend with vectorized kernels"],
        )
        content = readme.read_text()
        assert "JAX GPU backend with vectorized kernels" in content
