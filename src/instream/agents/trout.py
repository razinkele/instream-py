"""Thin Mesa agent shell for trout -- all state lives in TroutState SoA."""
import mesa


class TroutAgent(mesa.Agent):
    def __init__(self, model, idx: int):
        super().__init__(model)
        self.idx = idx

    @property
    def length(self):
        return float(self.model.trout_state.length[self.idx])

    @property
    def weight(self):
        return float(self.model.trout_state.weight[self.idx])

    @property
    def species_idx(self):
        return int(self.model.trout_state.species_idx[self.idx])

    @property
    def age(self):
        return int(self.model.trout_state.age[self.idx])

    def step(self):
        pass  # All computation in batch kernels
