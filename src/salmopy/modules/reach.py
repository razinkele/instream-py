"""Reach state update module.

Updates reach-level state variables from time-series environmental conditions
and computes species-dependent intermediate variables used by downstream modules.
"""
import numpy as np


def update_reach_state(reach_state, conditions, reach_names, species_params, backend,
                       species_order=None):
    """Update reach state from current time-series conditions.

    Sets flow, temperature, turbidity for each reach.
    Computes species-dependent intermediate variables:
    - cmax_temp_func: CMax temperature multiplier (from interpolation table)
    - max_swim_temp_term: C*T^2 + D*T + E
    - resp_temp_term: exp(C * T^2)

    Parameters
    ----------
    reach_state : ReachState
        Mutable reach state arrays to update in-place.
    conditions : dict[str, dict]
        Mapping from reach name to {"flow", "temperature", "turbidity"}.
    reach_names : list[str]
        Ordered reach names matching reach_state array indices.
    species_params : dict[str, SpeciesParams]
        Mapping from species name to its parameter object.
    backend : ComputeBackend or None
        Compute backend (needed for interpolation). Can be None if no
        species computations are required.
    species_order : list[str] or None
        Ordered species names matching the species axis (axis=1) of
        reach_state intermediate arrays.
    """
    for i, reach_name in enumerate(reach_names):
        cond = conditions[reach_name]
        reach_state.flow[i] = cond["flow"]
        reach_state.temperature[i] = cond["temperature"]
        reach_state.turbidity[i] = cond["turbidity"]

    # Compute species intermediates if params provided
    if species_order and species_params and backend:
        for i, reach_name in enumerate(reach_names):
            T = reach_state.temperature[i]
            for j, sp_name in enumerate(species_order):
                sp = species_params[sp_name]
                # CMax temperature function (interpolation table)
                if hasattr(sp, 'cmax_temp_table_x') and len(sp.cmax_temp_table_x) > 0:
                    reach_state.cmax_temp_func[i, j] = backend.interp1d(
                        np.array([T]), sp.cmax_temp_table_x, sp.cmax_temp_table_y
                    )[0]
                # Max swim speed temperature term: C*T² + D*T + E
                C = getattr(sp, 'max_speed_C', 0.0)
                D = getattr(sp, 'max_speed_D', 0.0)
                E = getattr(sp, 'max_speed_E', 0.0)
                reach_state.max_swim_temp_term[i, j] = max(0.0, C * T * T + D * T + E)
                # Respiration temperature term: exp(resp_C * T²)
                resp_C = getattr(sp, 'resp_C', 0.0)
                exponent = resp_C * T * T
                exponent = max(exponent, -500.0)
                exponent = min(exponent, 50.0)
                reach_state.resp_temp_term[i, j] = np.exp(exponent)
