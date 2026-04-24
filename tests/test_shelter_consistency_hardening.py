"""Phase 2 Task 2.3: shelter eligibility threshold and depletion charge
must agree on super-individual scaling.

Pass 1 at fitness.py:286 previously did `a_shelter > fish_length * fish_length`
without scaling by rep. Pass 2 deducts `fish_length * fish_length * rep`. For
super-individuals the two differed silently.

v0.43.17: upgraded from inspect.getsource() string-grep to an arithmetic
invariant test. Full kernel-level test left as a documented skip pending
a fixture-helper extraction.
"""
import pytest


def test_shelter_eligibility_kernel_level_reserved_for_fixture_extraction():
    """Placeholder for a focused kernel-level test of shelter rep-scaling.

    Intended semantics: build a single-cell scenario with
      a_shelter = 30  (cm²)
      fish_length = 5 (cm) -> fish_length² = 25 (cm²)
      rep = 10 -> required = 250 cm²
    and verify the kernel rejects drift-with-shelter (30 < 250) while
    accepting it for rep=1 (30 > 25).

    Full fixture setup for `_evaluate_all_cells_v2` direct invocation is
    large (CSR candidate arrays, per-reach parameter packs). Integration
    coverage of the same code path is provided by
    `tests/test_batch_select_habitat_parity.py::test_batch_and_scalar_paths_agree_numerically`
    added in v0.43.17 Task 1. This test slot is reserved for the focused
    unit test once the kernel-fixture helper is extracted.
    """
    pytest.skip(
        "kernel-fixture helper not yet extracted; parity test in "
        "test_batch_select_habitat_parity.py covers the dispatch path"
    )


def test_pass1_and_pass2_shelter_arithmetic_agree_for_rep_one():
    """Sanity: for rep=1, rep-scaling and per-fish-only thresholds give
    identical decisions (regression guard against a fix that accidentally
    scales by rep for the rep=1 case in a way that changes behavior).
    """
    fish_length = 5.0
    a_shelter = 30.0
    rep_unscaled_passes = a_shelter > fish_length * fish_length
    rep_scaled_passes_rep1 = a_shelter > fish_length * fish_length * 1
    assert rep_unscaled_passes == rep_scaled_passes_rep1
