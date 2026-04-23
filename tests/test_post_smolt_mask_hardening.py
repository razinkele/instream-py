"""Phase 2 Task 2.7: post-smolt forced-hazard array must only be written
for fish that are actually in the post-smolt window. Guard at line 222
currently rescues the code; removing it silently applies the post-smolt
hazard to adults sharing the smolt year."""
import inspect
from salmopy.marine import survival as ms


def test_post_smolt_write_is_masked_by_post_smolt_mask():
    src = inspect.getsource(ms)
    assert ("post_smolt_mask & (smolt_years == sy)" in src
            or "post_smolt_mask & (smolt_years" in src), (
        "h_forced_array write at marine/survival.py:~221 must AND with "
        "post_smolt_mask; currently the mask is only `smolt_years == sy`. "
        "Removing the downstream forced_mask guard would silently apply "
        "post-smolt hazard to adult fish sharing the smolt year."
    )
