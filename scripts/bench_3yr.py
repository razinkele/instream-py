"""3-year Baltic benchmark — runs N iterations, reports min/mean."""
import time
import sys
from pathlib import Path
import numpy as np
from salmopy.model import SalmopyModel
from salmopy.state.life_stage import LifeStage

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2

times = []
for run in range(N):
    m = SalmopyModel(
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
    times.append(elapsed)
    print(f"  Run {run+1}/{N}: {elapsed:.1f}s")

print(f"Min: {min(times):.1f}s  Mean: {sum(times)/len(times):.1f}s")
