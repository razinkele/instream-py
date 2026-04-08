"""LifeStage enum for all salmon life history stages."""
from enum import IntEnum


class LifeStage(IntEnum):
    FRY = 0              # freshwater: post-emergence juvenile / resident
    PARR = 1             # freshwater: anadromous juvenile, pre-smolt
    SPAWNER = 2          # freshwater: active spawner
    SMOLT = 3            # marine: estuary transition
    OCEAN_JUVENILE = 4   # marine: open Baltic feeding
    OCEAN_ADULT = 5      # marine: mature, pre-return
    RETURNING_ADULT = 6  # freshwater: migrating upstream

    @property
    def is_freshwater(self) -> bool:
        return self in (LifeStage.FRY, LifeStage.PARR,
                        LifeStage.SPAWNER, LifeStage.RETURNING_ADULT)

    @property
    def is_marine(self) -> bool:
        return self in (LifeStage.SMOLT, LifeStage.OCEAN_JUVENILE,
                        LifeStage.OCEAN_ADULT)
