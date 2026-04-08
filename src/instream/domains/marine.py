"""MarineDomain — orchestrates marine life phase step."""
import numpy as np
from datetime import date
from instream.agents.life_stage import LifeStage
from instream.modules.marine_growth import marine_growth_rate
from instream.modules.marine_survival import combined_marine_survival
from instream.modules.marine_fishing import apply_fishing_mortality
from instream.modules.marine_migration import check_maturation


class MarineDomain:
    def __init__(self, space, driver, species_params, gear_configs,
                 min_legal_length=60.0):
        self.space = space
        self.driver = driver
        self.sp = species_params
        self.gear_configs = gear_configs
        self.min_legal_length = min_legal_length
        self.harvest_records = []

    def update_environment(self, current_date):
        self.space.zone_state = self.driver.get_zone_conditions(current_date)

    def daily_step(self, trout_state, current_date, rng):
        ts = trout_state
        zs = self.space.zone_state

        # Marine fish mask
        marine = ts.alive & (ts.zone_idx >= 0)
        idx = np.where(marine)[0]
        if len(idx) == 0:
            return

        zones = ts.zone_idx[idx]
        temps = zs.temperature[zones]
        prey = zs.prey_index[zones]
        pred_risk = zs.predation_risk[zones]
        days_ocean = np.maximum(current_date.toordinal() - ts.smolt_date[idx], 0)

        # Sea-winters increment (anniversary of ocean entry)
        current_ordinal = current_date.toordinal()
        for j, i in enumerate(idx):
            entry_ordinal = int(ts.smolt_date[i])
            if entry_ordinal > 0:
                days_at_sea = current_ordinal - entry_ordinal
                expected_sw = max(0, days_at_sea // 365)
                if expected_sw > ts.sea_winters[i]:
                    ts.sea_winters[i] = expected_sw

        # 1. Growth
        dw = marine_growth_rate(
            ts.length[idx], ts.weight[idx], temps, prey, ts.condition[idx],
            cmax_A=self.sp["marine_cmax_A"], cmax_B=self.sp["marine_cmax_B"],
            growth_efficiency=self.sp["marine_growth_efficiency"],
            resp_A=self.sp.get("resp_A", 0.03),
            resp_B=self.sp.get("resp_B", -0.25),
            temp_opt=self.sp.get("temp_opt", 12.0),
            temp_max=self.sp.get("temp_max", 24.0),
        )
        ts.weight[idx] = np.maximum(ts.weight[idx] + dw, 1.0)
        a = 0.01  # Fulton K=1 => W = 0.01 * L^3
        ts.length[idx] = np.power(ts.weight[idx] / a, 1.0 / 3.0)
        ts.condition[idx] = ts.weight[idx] / (a * ts.length[idx] ** 3)

        # 2. Natural survival
        surv = combined_marine_survival(
            ts.length[idx], ts.weight[idx], ts.condition[idx],
            temps, pred_risk, zones, days_ocean, rng,
            seal_L1=self.sp["marine_mort_seal_L1"],
            seal_L9=self.sp["marine_mort_seal_L9"],
            cormorant_L1=self.sp["marine_mort_cormorant_L1"],
            cormorant_L9=self.sp["marine_mort_cormorant_L9"],
            cormorant_zones=self.sp["marine_mort_cormorant_zones"],
            base_mort=self.sp["marine_mort_base"],
            temp_threshold=self.sp.get("temp_threshold", 20.0),
            m74_prob=self.sp["marine_mort_m74_prob"],
            post_smolt_window=self.sp.get("post_smolt_window", 60),
        )
        dies_natural = rng.random(len(idx)) > surv
        ts.alive[idx[dies_natural]] = False

        # Recompute alive
        still_alive = ts.alive[idx]
        idx = idx[still_alive]
        if len(idx) == 0:
            return

        # 3. Fishing
        landed, bycatch_dead = apply_fishing_mortality(
            ts.length[idx], ts.zone_idx[idx],
            current_month=current_date.month,
            gear_configs=self.gear_configs,
            zone_names=self.space.zone_names,
            min_legal_length=self.min_legal_length, rng=rng,
        )
        ts.alive[idx[landed | bycatch_dead]] = False

        still_alive = ts.alive[idx]
        idx = idx[still_alive]
        if len(idx) == 0:
            return

        # 4. Maturation
        mature = check_maturation(
            ts.length[idx], ts.condition[idx], ts.sea_winters[idx], rng,
            min_sea_winters=self.sp["maturation_min_sea_winters"],
            prob_by_sw=self.sp["maturation_probs"],
            min_length=self.sp["maturation_min_length"],
            min_condition=self.sp["maturation_min_condition"],
        )
        returning = idx[mature]
        ts.life_history[returning] = int(LifeStage.RETURNING_ADULT)
        ts.zone_idx[returning] = -1
        ts.reach_idx[returning] = ts.natal_reach_idx[returning]
