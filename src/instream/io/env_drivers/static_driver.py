"""StaticDriver — seasonal lookup tables from YAML config."""
import numpy as np
from datetime import date
from instream.state.zone_state import ZoneState


class StaticDriver:
    """Provides zone conditions from monthly lookup tables with linear interpolation."""

    def __init__(self, static_config, zone_names, zone_areas):
        self._zone_names = zone_names
        self._zone_areas = zone_areas
        self._tables = {}
        for zname in zone_names:
            zcfg = static_config.get(zname, {})
            self._tables[zname] = {
                "temperature": self._parse_monthly(zcfg.get("temperature", {})),
                "salinity": self._parse_monthly(zcfg.get("salinity", {})),
                "prey_index": self._parse_monthly(zcfg.get("prey_index", {})),
                "predation_risk": self._parse_monthly(zcfg.get("predation_risk", {})),
            }

    @staticmethod
    def _parse_monthly(table):
        if not table:
            return np.arange(1, 13, dtype=float), np.zeros(12)
        months = sorted(table.keys())
        values = [table[m] for m in months]
        return np.array(months, dtype=float), np.array(values, dtype=float)

    def _interp(self, months_arr, values_arr, day_of_year):
        frac_month = 1 + (day_of_year - 1) * 12 / 365.0
        return float(np.interp(frac_month, months_arr, values_arr))

    def get_zone_conditions(self, current_date: date) -> ZoneState:
        doy = current_date.timetuple().tm_yday
        n = len(self._zone_names)
        zs = ZoneState.zeros(n)
        for i, zname in enumerate(self._zone_names):
            t = self._tables[zname]
            zs.temperature[i] = self._interp(*t["temperature"], doy)
            zs.salinity[i] = self._interp(*t["salinity"], doy)
            zs.prey_index[i] = self._interp(*t["prey_index"], doy)
            zs.predation_risk[i] = self._interp(*t["predation_risk"], doy)
            zs.area_km2[i] = self._zone_areas.get(zname, 0)
        return zs
