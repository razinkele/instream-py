# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-22

### Added
- Survival-integrated fitness function (Phase 5)
- Piscivore density computed from fish distribution
- Annual age increment on January 1
- Numba @njit compiled fitness evaluation kernel (60x speedup)
- Hypothesis property-based tests
- Performance regression tests
- Population file configurable via YAML
- `netlogo-oracle` skill for validation data generation
- `validation-checker` agent for implementation completeness

### Fixed
- Random sex assignment for initial population and emerged fish
- `spawned_this_season` reset at spawn season start
- Growth stored during habitat selection (not recomputed from depleted resources)
- Deferred imports moved to module level
- Condition factor updated after spawning weight loss
- Division-by-zero guards on all logistic functions
- Clamped max_swim_temp_term >= 0, resp_temp_term overflow guard
- Zombie fish at weight=0 (condition=0 now lethal)
- Egg count rounding (np.round instead of truncation)
- Negative velocity and egg development clamped to non-negative
- Survival probability raised to step_length power
- Redd survival uses logistic^step_length formula
- Logistic exp() argument clipped to prevent overflow

### Changed
- `evaluate_logistic` uses math.exp instead of np.exp (2.7x faster)
- `survival_condition` uses min/max instead of np.clip (55x faster)
- `cmax_temp_function` uses bisect instead of np.interp (4.8x faster)
- Habitat selection inner loop pre-computes step/fish invariants
- Vectorized hydraulic interpolation using searchsorted + lerp
- Batch redd emergence (eliminates O(eggs*capacity) scan)
- Integer activity codes in growth and survival functions

### Performance
- Full step: 62s -> 179ms (346x faster)
- Full 912-day run: ~129 min -> ~2.1 min (61x faster)

## [0.1.0] - 2026-03-20

### Added
- Initial Python implementation of inSTREAM 7.4
- Mesa 3.x model orchestration
- SoA state containers (TroutState, CellState, ReddState, ReachState)
- FEMSpace with KD-tree spatial queries
- Wisconsin bioenergetics (growth, consumption, respiration)
- 5 survival sources (temperature, stranding, condition, fish predation, terrestrial predation)
- Spawning, egg development, redd emergence
- Migration framework
- YAML configuration with NLS converter
- NumPy and Numba compute backends
- 376 unit tests
