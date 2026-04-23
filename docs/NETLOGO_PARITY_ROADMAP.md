# NetLogo Parity Status

> **Notice:** The original `NETLOGO_PARITY_ROADMAP.md` (dated 2026-03-22, from
> v0.2.0) has been archived to
> [`docs/releases/archive-2026-03-22-netlogo-parity-roadmap.md`](releases/archive-2026-03-22-netlogo-parity-roadmap.md).
> Its phase-completion tables and performance numbers were 40+ versions stale
> and systematically misleading. This redirect page replaces it.

## Current status

See the README for up-to-date parity metrics (test count, NetLogo validation
pass/skip ratios, performance vs. the NetLogo reference).

For granular per-calibration-arc status, see the per-release notes under
`docs/releases/` and project memory entries (`project_vXX_status.md`).

## NetLogo reference data

NetLogo oracle CSVs live under `tests/fixtures/reference/` and are consumed
by `test_validation.py` + `test_run_level_parity.py`. When absent, those
tests silently skip — but as of Phase 4 (v0.43.2) a `pytest_configure`
hook emits a `UserWarning` to surface the gap in CI logs.

Regenerate oracle CSVs with the `netlogo-oracle` skill/workflow.
