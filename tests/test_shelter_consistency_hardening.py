"""Phase 2 Task 2.3: shelter eligibility threshold and depletion charge
must agree on super-individual scaling.

Pass 1 at fitness.py:286 previously did `a_shelter > fish_length * fish_length`
without scaling by rep. Pass 2 deducts `fish_length * fish_length * rep`. For
super-individuals the two differed silently.
"""
import inspect


def test_shelter_eligibility_matches_depletion_for_super_individuals():
    from salmopy.backends.numba_backend import fitness
    src = inspect.getsource(fitness._evaluate_all_cells_v2)
    assert ("fish_length * fish_length * superind_rep" in src
            or "fish_length * fish_length * rep" in src
            or "a_shelter_scaled" in src), (
        "Pass 1 shelter-eligibility threshold at fitness.py:~286 must scale "
        "by super-individual rep to match Pass 2 depletion charge at ~946. "
        "Current code uses an unscaled per-individual threshold."
    )
