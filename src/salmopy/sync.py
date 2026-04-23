"""Mesa <-> SoA synchronization."""
import numpy as np
from salmopy.agents.trout import TroutAgent


def sync_trout_agents(model):
    """Create/remove Mesa TroutAgent shells to match alive mask in trout_state."""
    alive_set = set(np.where(model.trout_state.alive)[0])
    current_set = set(model._trout_agents.keys())

    # Remove dead
    for idx in current_set - alive_set:
        del model._trout_agents[idx]

    # Add born
    for idx in alive_set - current_set:
        model._trout_agents[idx] = TroutAgent(model, idx)
