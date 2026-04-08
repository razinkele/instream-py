"""MarineSpace — spatial container for marine zones."""
from instream.state.zone_state import ZoneState


class MarineSpace:
    def __init__(self, zone_config: dict):
        self.zone_names = list(zone_config.keys())
        self.num_zones = len(self.zone_names)
        self._name_to_idx = {n: i for i, n in enumerate(self.zone_names)}
        self.zone_areas = {n: cfg.get("area_km2", 0) for n, cfg in zone_config.items()}
        self.zone_graph = {}
        for i, (name, cfg) in enumerate(zone_config.items()):
            conns = cfg.get("connections", [])
            self.zone_graph[i] = [self._name_to_idx[c] for c in conns
                                   if c in self._name_to_idx]
        self.zone_state = ZoneState.zeros(self.num_zones)

    def name_to_idx(self, name: str) -> int:
        return self._name_to_idx[name]
