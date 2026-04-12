"""Quick 3-year Baltic benchmark for v0.26.0 optimization."""
import time
from pathlib import Path
import numpy as np
from instream.model import InSTREAMModel
from instream.state.life_stage import LifeStage

m = InSTREAMModel(
    Path("configs/example_calibration_baltic.yaml"),
    data_dir=Path("tests/fixtures/example_a"),
    end_date_override="2014-03-31",
)
ts = m.trout_state
dead = np.where(~ts.alive)[0]
parr = dead[:min(len(dead), 3000)]
sp = m.config.species[m.species_order[0]]
ts.alive[parr] = True
ts.species_idx[parr] = 0
ts.life_history[parr] = int(LifeStage.PARR)
ts.age[parr] = 1
ts.length[parr] = 15.0
ts.weight[parr] = sp.weight_A * 15.0 ** sp.weight_B
ts.condition[parr] = 1.0
ts.smolt_readiness[parr] = 0.9
ts.fitness_memory[parr] = 0.5
ts.reach_idx[parr] = 0
ts.natal_reach_idx[parr] = 0
ts.zone_idx[parr] = -1
ts.sea_winters[parr] = 0
ts.smolt_date[parr] = -1
ts.is_hatchery[parr] = False

t0 = time.time()
m.run()
elapsed = time.time() - t0
print(f"3-year Baltic sim: {elapsed:.1f}s (v0.25.0 baseline: 175.8s)")
