"""Thin Mesa agent shell for redds."""
import mesa


class ReddAgent(mesa.Agent):
    def __init__(self, model, idx: int):
        super().__init__(model)
        self.idx = idx

    @property
    def num_eggs(self):
        return int(self.model.redd_state.num_eggs[self.idx])

    def step(self):
        pass
