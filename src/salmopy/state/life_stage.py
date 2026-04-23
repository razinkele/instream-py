"""Life stage definitions for inSTREAM/inSALMON fish agents."""
from enum import IntEnum


class LifeStage(IntEnum):
    """Life history stage stored as int8 in TroutState.life_history arrays.

    Names follow the InSALMON design doc (docs/plans/2026-04-08-insalmon-design.md)
    to avoid a breaking rename when marine stages are activated in v0.14.0.
    Values 3-6 were defined in v0.13.0 but not used until v0.14.0.
    KELT (7) is a v0.17.0 InSALMON extension — no NetLogo counterpart.
    """
    FRY = 0              # post-emergence juvenile (was "resident")
    PARR = 1             # anadromous juvenile, pre-smolt (was "anad_juvenile")
    SPAWNER = 2          # active spawner (was "anad_adult")
    SMOLT = 3            # outmigrating juvenile (v0.14.0+)
    OCEAN_JUVENILE = 4   # marine feeding (v0.14.0+)
    OCEAN_ADULT = 5      # marine mature (v0.14.0+)
    RETURNING_ADULT = 6  # upstream migration to natal reach
    KELT = 7             # post-spawn survivor returning to ocean (v0.17.0,
                         # InSALMON extension — no NetLogo reference)
