"""Tests for the preflight screen (Morris → Sobol funnel)."""
import pytest

SALib = pytest.importorskip("SALib")


class TestPreflightScreen:
    def test_detects_negligible_param(self):
        """A param with no effect on Y should be flagged NEGLIGIBLE."""
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            preflight_screen,
            IssueCategory,
        )

        params = [
            FreeParameter("influential", 0.0, 1.0, Transform.LINEAR),
            FreeParameter("negligible", 0.0, 1.0, Transform.LINEAR),
        ]

        # Y depends only on column 0
        def eval_fn(X):
            return (X[:, 0] * 10.0).reshape(-1, 1)

        issues = preflight_screen(params, eval_fn, morris_trajectories=30, sobol_n_base=32, seed=42)
        cats = [i.category for i in issues]
        # The negligible param should be flagged
        flagged = [i for i in issues if i.param == "negligible" and i.category == IssueCategory.NEGLIGIBLE]
        assert len(flagged) == 1
        assert flagged[0].auto_fixable

    def test_detects_all_negligible(self):
        """When Y is constant, ALL_NEGLIGIBLE should fire."""
        import numpy as np
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            preflight_screen,
            IssueCategory,
            IssueSeverity,
        )

        params = [
            FreeParameter("a", 0.0, 1.0, Transform.LINEAR),
            FreeParameter("b", 0.0, 1.0, Transform.LINEAR),
        ]

        def eval_fn(X):
            return np.ones(len(X)).reshape(-1, 1) * 5.0

        issues = preflight_screen(params, eval_fn, morris_trajectories=10, sobol_n_base=16, seed=42)
        all_negl = [i for i in issues if i.category == IssueCategory.ALL_NEGLIGIBLE]
        assert len(all_negl) == 1
        assert all_negl[0].severity == IssueSeverity.ERROR

    def test_detects_blowup(self):
        """eval_fn returning >50% inf should trigger BLOWUP error."""
        import numpy as np
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            preflight_screen,
            IssueCategory,
            IssueSeverity,
        )

        params = [FreeParameter("a", 0.0, 1.0, Transform.LINEAR)]

        def eval_fn(X):
            Y = X[:, 0].copy()
            Y[: len(Y) // 2 + 1] = np.inf  # >50% inf
            return Y.reshape(-1, 1)

        issues = preflight_screen(params, eval_fn, morris_trajectories=10, sobol_n_base=16, seed=42)
        blowup = [i for i in issues if i.category == IssueCategory.BLOWUP]
        assert len(blowup) == 1
        assert blowup[0].severity == IssueSeverity.ERROR

    def test_format_issues_renders(self):
        from salmopy.calibration import (
            format_issues,
            PreflightIssue,
            IssueCategory,
            IssueSeverity,
        )

        issues = [
            PreflightIssue(
                IssueCategory.NEGLIGIBLE, IssueSeverity.WARNING,
                "x", "test message", auto_fixable=True,
            ),
        ]
        txt = format_issues(issues)
        assert "negligible" in txt
        assert "x" in txt
        assert "test message" in txt

    def test_format_issues_empty(self):
        from salmopy.calibration import format_issues

        assert "No preflight issues" in format_issues([])
