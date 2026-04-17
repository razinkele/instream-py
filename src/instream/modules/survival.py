"""Survival and mortality functions for inSTREAM trout model.

Implements NetLogo survival sources: high temperature, stranding, condition,
fish predation, terrestrial predation, and stochastic mortality application.
"""

import numpy as np

from instream.modules.behavior import evaluate_logistic


# ---------------------------------------------------------------------------
# 1. High Temperature Survival
# ---------------------------------------------------------------------------


def survival_high_temperature(temperature, T1=28.0, T9=24.0):
    """Survival probability from high water temperature.

    Uses a DECREASING logistic (T1 > T9): high temperature -> low survival.
    The logistic gives the mortality risk; survival = 1 - logistic.

    Parameters
    ----------
    temperature : float
        Water temperature (C).
    T1 : float
        Temperature at which logistic = 0.1 (high end).
    T9 : float
        Temperature at which logistic = 0.9 (low end).

    Returns
    -------
    float
        Survival probability in [0, 1].
    """
    return evaluate_logistic(temperature, T1, T9)


# ---------------------------------------------------------------------------
# 2. Stranding Survival
# ---------------------------------------------------------------------------


def survival_stranding(depth, survival_when_dry=0.5):
    """Survival probability from stranding (dry cell).

    Parameters
    ----------
    depth : float
        Water depth at the cell (cm).
    survival_when_dry : float
        Daily survival probability when depth <= 0.

    Returns
    -------
    float
        Survival probability.
    """
    if depth <= 0:
        return survival_when_dry
    return 1.0


# ---------------------------------------------------------------------------
# 3. Condition Survival (two-piece linear)
# ---------------------------------------------------------------------------


def survival_condition(condition, S_at_K5=0.8, S_at_K8=0.992, K_crit=0.8):
    """Survival probability based on body condition factor (K = weight / (length^3 * p1)).

    Two-piece linear function:
    - condition == 1.0 -> survival = 1.0
    - condition in (K_crit, 1.0) -> linear from S_at_K8 at K_crit to 1.0 at 1.0
    - condition <= K_crit -> linear from S_at_K5 at 0.5 to S_at_K8 at K_crit

    Parameters
    ----------
    condition : float
        Body condition factor (0..1+).
    S_at_K5 : float
        Survival at condition = 0.5.
    S_at_K8 : float
        Survival at condition = K_crit.
    K_crit : float
        Condition threshold separating the two linear pieces (default 0.8).

    Returns
    -------
    float
        Survival probability, clipped to [0, 1].
    """
    if condition <= 0.0:
        return 0.0
    if condition >= 1.0:
        return 1.0

    if condition > K_crit:
        # Upper piece: from (K_crit, S_at_K8) to (1.0, 1.0)
        denom = 1.0 - K_crit
        if denom <= 0.0:
            return 1.0
        slope = (1.0 - S_at_K8) / denom
        s = S_at_K8 + slope * (condition - K_crit)
    else:
        # Lower piece: from (0.5, S_at_K5) to (K_crit, S_at_K8)
        denom = K_crit - 0.5
        if denom <= 0.0:
            return S_at_K8
        slope = (S_at_K8 - S_at_K5) / denom
        intercept = S_at_K5 - (0.5 * slope)
        s = condition * slope + intercept

    return max(0.0, min(1.0, s))


# ---------------------------------------------------------------------------
# 4. Fish Predation Survival
# ---------------------------------------------------------------------------


def survival_fish_predation(
    length,
    depth,
    light,
    pisciv_density,
    temperature,
    activity,
    min_surv,
    L1,
    L9,
    D1,
    D9,
    P1,
    P9,
    I1,
    I9,
    T1,
    T9,
    hiding_factor,
):
    """Survival probability from piscivorous fish predation.

    Parameters
    ----------
    length : float
        Fish length (cm).
    depth : float
        Water depth (cm).
    light : float
        Light level.
    pisciv_density : float
        Piscivore density.
    temperature : float
        Water temperature (C).
    activity : str
        Current activity ("drift", "search", or "hide").
    min_surv : float
        Minimum survival (reach-level parameter).
    L1, L9 : float
        Length logistic parameters.
    D1, D9 : float
        Depth logistic parameters.
    P1, P9 : float
        Piscivore density logistic parameters.
    I1, I9 : float
        Light logistic parameters.
    T1, T9 : float
        Temperature logistic parameters.
    hiding_factor : float
        Predation risk reduction when hiding.

    Returns
    -------
    float
        Survival probability in [min_surv, 1.0].
    """
    is_hiding = (activity == "hide") if isinstance(activity, str) else (activity == 2)
    hide_factor = hiding_factor if is_hiding else 0.0

    relative_risk = (
        (1.0 - evaluate_logistic(length, L1, L9))
        * (1.0 - evaluate_logistic(depth, D1, D9))
        * (1.0 - evaluate_logistic(pisciv_density, P1, P9))
        * (1.0 - evaluate_logistic(light, I1, I9))
        * (1.0 - evaluate_logistic(temperature, T1, T9))
        * (1.0 - hide_factor)
    )

    return min_surv + (1.0 - min_surv) * (1.0 - relative_risk)


# ---------------------------------------------------------------------------
# 5. Terrestrial Predation Survival
# ---------------------------------------------------------------------------


def survival_terrestrial_predation(
    length,
    depth,
    velocity,
    light,
    dist_escape,
    activity,
    available_hiding,
    superind_rep,
    min_surv,
    L1,
    L9,
    D1,
    D9,
    V1,
    V9,
    I1,
    I9,
    H1,
    H9,
    hiding_factor,
):
    """Survival probability from terrestrial predation (birds, mammals).

    Parameters
    ----------
    length : float
        Fish length (cm).
    depth : float
        Water depth (cm).
    velocity : float
        Water velocity (cm/s).
    light : float
        Light level.
    dist_escape : float
        Distance to nearest escape cover (cm).
    activity : str
        Current activity.
    available_hiding : int
        Number of hiding places available in cell.
    superind_rep : int
        Number of individuals represented by this super-individual.
    min_surv : float
        Minimum survival (reach-level parameter).
    L1, L9 : float
        Length logistic parameters.
    D1, D9 : float
        Depth logistic parameters.
    V1, V9 : float
        Velocity logistic parameters.
    I1, I9 : float
        Light logistic parameters.
    H1, H9 : float
        Distance-to-escape logistic parameters.
    hiding_factor : float
        Predation risk reduction when hiding.

    Returns
    -------
    float
        Survival probability in [min_surv, 1.0].
    """
    is_hiding = (activity == "hide") if isinstance(activity, str) else (activity == 2)
    in_hiding = is_hiding and (available_hiding >= superind_rep)
    hide_factor = hiding_factor if in_hiding else 0.0

    relative_risk = (
        (1.0 - evaluate_logistic(length, L1, L9))
        * (1.0 - evaluate_logistic(depth, D1, D9))
        * (1.0 - evaluate_logistic(velocity, V1, V9))
        * (1.0 - evaluate_logistic(light, I1, I9))
        * (1.0 - evaluate_logistic(dist_escape, H1, H9))
        * (1.0 - hide_factor)
    )

    return min_surv + (1.0 - min_surv) * (1.0 - relative_risk)


# ---------------------------------------------------------------------------
# 6. Non-starve (combined) Survival
# ---------------------------------------------------------------------------


def non_starve_survival(s_high_temp, s_stranding, s_fish_pred, s_terr_pred):
    """Combined non-starvation survival (product of independent sources).

    Note: condition survival is NOT included here -- it is handled
    separately via mean_condition_survival in the fitness calculation.

    Parameters
    ----------
    s_high_temp : float
        High temperature survival.
    s_stranding : float
        Stranding survival.
    s_fish_pred : float
        Fish predation survival.
    s_terr_pred : float
        Terrestrial predation survival.

    Returns
    -------
    float
        Combined daily survival probability.
    """
    return s_high_temp * s_stranding * s_fish_pred * s_terr_pred


# ---------------------------------------------------------------------------
# 7. Stochastic Mortality Application
# ---------------------------------------------------------------------------


def apply_mortality(alive, survival_probs, rng):
    """Apply stochastic mortality to a population.

    For each alive fish, draw a uniform random number. If random > survival,
    the fish dies. Dead fish stay dead.

    Parameters
    ----------
    alive : ndarray of bool
        Alive status array, modified in place.
    survival_probs : ndarray of float
        Per-fish survival probabilities (already raised to step_length power
        if needed by the caller).
    rng : numpy.random.Generator
        Random number generator for reproducibility.
    """
    n = len(alive)
    draws = rng.random(n)
    # Fish dies if draw > survival AND was alive
    dies = alive & (draws >= survival_probs)
    alive[dies] = False


# ---------------------------------------------------------------------------
# 8. ED-based Starvation Mortality (HexSimPy integration)
# ---------------------------------------------------------------------------


def survival_mass_floor(
    weight: float,
    max_lifetime_weight: float,
    floor_fraction: float = 0.5,
    mass_floor_survival: float = 0.9,
) -> float:
    """Survival probability from energy depletion (starvation).

    If current weight drops below ``floor_fraction × max_lifetime_weight``,
    daily survival is reduced to ``mass_floor_survival``. Otherwise 1.0.

    Parameters
    ----------
    weight : float
        Current fish weight (g).
    max_lifetime_weight : float
        Peak weight ever achieved by this fish (g).
    floor_fraction : float
        Fraction of max weight below which starvation kicks in (default 0.5).
    mass_floor_survival : float
        Daily survival probability when starving (default 0.9).

    Returns
    -------
    float
        Survival probability in [0, 1].
    """
    if max_lifetime_weight <= 0.0:
        return 1.0
    if weight < floor_fraction * max_lifetime_weight:
        return mass_floor_survival
    return 1.0


# ---------------------------------------------------------------------------
# 9. Redd (Egg) Survival — Low Temperature
# ---------------------------------------------------------------------------


def _redd_logistic(x: float, T1: float, T9: float) -> float:
    """Return the inSTREAM logistic value for *x* given parameters T1 and T9."""
    return evaluate_logistic(x, T1, T9)


def redd_survival_lo_temp(
    temperature: float,
    T1: float = 1.7,
    T9: float = 4.0,
    step_length: float = 1.0,
) -> float:
    """Daily survival probability for low-temperature redd mortality.

    The logistic is *increasing* (T1 < T9): cold temperatures yield low
    logistic values -> high mortality.

    Returns the daily logistic value (step_length parameter is accepted
    for API compatibility but not used — step_length scaling is handled
    in apply_redd_survival via the constant-hazard formula, matching
    NetLogo's ``(1 - s_daily) * eggs * step_length`` approach).
    """
    logistic_val = _redd_logistic(temperature, T1, T9)
    return float(np.clip(logistic_val, 0.0, 1.0))


# ---------------------------------------------------------------------------
# 9. Redd (Egg) Survival — High Temperature
# ---------------------------------------------------------------------------


def redd_survival_hi_temp(
    temperature: float,
    T1: float = 23.0,
    T9: float = 17.5,
    step_length: float = 1.0,
) -> float:
    """Daily survival probability for high-temperature redd mortality.

    The logistic is *decreasing* (T1 > T9): hot temperatures yield low
    logistic values -> high mortality.

    Returns the daily logistic value (step_length parameter is accepted
    for API compatibility but not used — step_length scaling is handled
    in apply_redd_survival via the constant-hazard formula, matching
    NetLogo's ``(1 - s_daily) * eggs * step_length`` approach).
    """
    logistic_val = _redd_logistic(temperature, T1, T9)
    return float(np.clip(logistic_val, 0.0, 1.0))


# ---------------------------------------------------------------------------
# 10. Redd (Egg) Survival — Dewatering
# ---------------------------------------------------------------------------


def redd_survival_dewatering(
    depth: float,
    dewater_surv: float = 0.9,
) -> float:
    """Fraction of eggs surviving dewatering.

    If cell depth <= 0, survival equals *dewater_surv*; otherwise 1.0.
    """
    if depth <= 0.0:
        return float(dewater_surv)
    return 1.0


# ---------------------------------------------------------------------------
# 11. Redd (Egg) Survival — Scour
# ---------------------------------------------------------------------------


def redd_survival_scour(
    flow: float,
    is_flow_peak: bool,
    shear_A: float = 0.013,
    shear_B: float = 0.40,
    scour_depth: float = 20.0,
) -> float:
    """Fraction of eggs surviving scour.

    During a flow peak the shear stress is ``shear_A * flow ** shear_B``.
    If this exceeds *scour_depth* all eggs are lost (survival = 0).
    """
    if not is_flow_peak:
        return 1.0
    shear_stress = shear_A * (flow**shear_B)
    if shear_stress > scour_depth:
        return 0.0
    return 1.0


# ---------------------------------------------------------------------------
# 12. Combined Redd Survival (vectorised over redds)
# ---------------------------------------------------------------------------


def apply_redd_survival(
    num_eggs,
    frac_developed,
    temperatures,
    depths,
    flows,
    is_peak,
    *,
    step_length: float = 1.0,
    lo_T1: float = 1.7,
    lo_T9: float = 4.0,
    hi_T1: float = 23.0,
    hi_T9: float = 17.5,
    dewater_surv: float = 0.9,
    shear_A: float = 0.013,
    shear_B: float = 0.40,
    scour_depth: float = 20.0,
):
    """Apply all redd-survival components and return updated egg counts.

    Parameters
    ----------
    num_eggs : array
        Current egg counts per redd.
    frac_developed : array
        Fraction of development completed (0-1). Reserved for future use.
    temperatures, depths, flows : arrays
        Environmental conditions at each redd's cell.
    is_peak : bool array
        Whether the current step is a flow peak for each redd.

    Returns
    -------
    new_eggs, lo_deaths, hi_deaths, dw_deaths, sc_deaths : arrays
    """
    n = len(num_eggs)
    eggs = np.asarray(num_eggs, dtype=np.float64).copy()

    lo_deaths = np.zeros(n, dtype=np.float64)
    hi_deaths = np.zeros(n, dtype=np.float64)
    dw_deaths = np.zeros(n, dtype=np.float64)
    sc_deaths = np.zeros(n, dtype=np.float64)

    for i in range(n):
        current = eggs[i]

        # Low-temperature mortality (constant-hazard model, matches NetLogo)
        # NetLogo: deaths = random-poisson((1 - s_daily) * eggs * step_length)
        lo_surv_daily = redd_survival_lo_temp(
            float(temperatures[i]), lo_T1, lo_T9
        )
        lo_mortality_rate = (1.0 - lo_surv_daily) * current * step_length
        killed = min(lo_mortality_rate, current)  # deterministic expectation
        lo_deaths[i] = killed
        current -= killed

        # High-temperature mortality (constant-hazard model, matches NetLogo)
        hi_surv_daily = redd_survival_hi_temp(
            float(temperatures[i]), hi_T1, hi_T9
        )
        hi_mortality_rate = (1.0 - hi_surv_daily) * current * step_length
        killed = min(hi_mortality_rate, current)
        hi_deaths[i] = killed
        current -= killed

        # Dewatering
        dw_surv = redd_survival_dewatering(float(depths[i]), dewater_surv)
        killed = current * (1.0 - dw_surv)
        dw_deaths[i] = killed
        current -= killed

        # Scour
        sc_surv = redd_survival_scour(
            float(flows[i]),
            bool(is_peak[i]),
            shear_A,
            shear_B,
            scour_depth,
        )
        killed = current * (1.0 - sc_surv)
        sc_deaths[i] = killed
        current -= killed

        eggs[i] = max(current, 0.0)

    return eggs, lo_deaths, hi_deaths, dw_deaths, sc_deaths
