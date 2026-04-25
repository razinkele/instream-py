---
name: deploy
description: Use when deploying the Shiny app to the server, after completing features or fixes, before demos, or when user says /deploy. Triggers on "deploy", "push to server", "update laguna".
---

# Deploy inSTREAM-py Shiny App to laguna.ku.lt

## Connection

| Field | Value |
|-------|-------|
| Server | laguna.ku.lt |
| SSH user | razinka (passwordless SSH key) |
| Target | /srv/shiny-server/inSTREAMPY |
| Method | scp (rsync is broken on this Windows — missing msys-xxhash-0.dll) |

## Project root

All commands run from: `C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py`

## Server layout

```
/srv/shiny-server/inSTREAMPY/
├── app.py                    ← from app/app.py
├── simulation.py             ← from app/simulation.py
├── __init__.py               ← from app/__init__.py
├── modules/                  ← from app/modules/*.py
├── configs/                  ← from configs/*.yaml
├── src/salmopy/              ← from src/salmopy/ (simulation engine; renamed from `instream` pre-v0.20)
├── data/fixtures/            ← from tests/fixtures/ (example data, 7 fixtures as of v0.46.0)
└── restart.txt               ← touch to restart Shiny Server
```

## Steps

### 1. Test gate

```bash
micromamba run -n shiny python -m pytest tests/ -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py -q --tb=short
```

**Stop if tests fail.** Do not deploy broken code. The full suite runs ~25-30 min; if you ran it within the last hour and only edited release metadata since, skip and proceed.

### 2. Confirm with user

Show a brief summary of what changed (check git diff --stat if helpful).
Ask: "Deploy to laguna.ku.lt? (y/n)"

### 3. Deploy app files

```bash
scp "app/app.py" "app/simulation.py" "app/__init__.py" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/"
```

```bash
scp "app/modules/"*.py "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/modules/"
```

### 4. Deploy simulation engine

**IMPORTANT:** Use `scp -r "src/salmopy"` (no trailing slash) to copy INTO `src/`.
A trailing slash creates double-nesting (`src/salmopy/salmopy/`).

```bash
ssh razinka@laguna.ku.lt "rm -rf /srv/shiny-server/inSTREAMPY/src/salmopy"
```

```bash
scp -r "src/salmopy" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/src/"
```

The `src/salmopy/` tree is large (~250+ files); expect this scp to take 1-3 minutes over a typical link.

### 5. Deploy configs

```bash
scp "configs/"*.yaml "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/configs/"
```

### 6. Deploy data fixtures

For each fixture directory, **wipe stale files first** — `scp -r` appends
to existing directories and leaves dead files behind. When reach names
change between versions (e.g. `example_baltic`'s v1→v2 rename moved
`MainStem` → `Nemunas`), the old CSVs would linger otherwise.

The full v0.46.0 fixture set is 7 directories. The Edit Model panel's
`discover_fixtures()` walks `data/fixtures/` AND `configs/`; any
fixture missing from the server is silently dropped from the dropdown.

Wipe them all in one ssh round-trip:

```bash
ssh razinka@laguna.ku.lt "for f in example_a example_b example_baltic example_byskealven example_morrumsan example_simojoki example_tornionjoki; do mkdir -p /srv/shiny-server/inSTREAMPY/data/fixtures/\$f/Shapefile && rm -f /srv/shiny-server/inSTREAMPY/data/fixtures/\$f/*.csv /srv/shiny-server/inSTREAMPY/data/fixtures/\$f/Shapefile/*; done"
```

Then scp each fixture's contents (the `/.` suffix copies CONTENTS, not a
nested dir). Bundle 2-3 fixtures per scp to amortize SSH session setup:

```bash
scp -r "tests/fixtures/example_a/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_a/"
scp -r "tests/fixtures/example_b/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_b/"
scp -r "tests/fixtures/example_baltic/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_baltic/"
```

```bash
scp -r "tests/fixtures/example_byskealven/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_byskealven/"
scp -r "tests/fixtures/example_morrumsan/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_morrumsan/"
```

```bash
scp -r "tests/fixtures/example_simojoki/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_simojoki/"
scp -r "tests/fixtures/example_tornionjoki/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_tornionjoki/"
```

The 4 WGBAST rivers (byskealven, morrumsan, simojoki, tornionjoki) are
the heaviest — each carries 500-3000 hex cells + per-reach hydrology
CSVs. `example_morrumsan` is the largest at ~40 CSVs. Expect each scp
batch to take 30-90s.

Note: `/.` suffix copies directory contents without creating a nested directory.

### 7. Restart and verify

```bash
ssh razinka@laguna.ku.lt "chmod -R g+r /srv/shiny-server/inSTREAMPY 2>/dev/null; touch /srv/shiny-server/inSTREAMPY/restart.txt"
```

```bash
ssh razinka@laguna.ku.lt "ls -la /srv/shiny-server/inSTREAMPY/app.py && ls /srv/shiny-server/inSTREAMPY/src/salmopy/__init__.py && ls /srv/shiny-server/inSTREAMPY/modules/edit_model_panel.py && echo 'OK: deploy verified'"
```

### 8. Live health check

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 20 https://laguna.ku.lt/inSTREAMPY/
```

Expected: `HTTP 200`. If you get `HTTP 500`, read the latest log:

```bash
ssh razinka@laguna.ku.lt "ls -lt /var/log/shiny-server/inSTREAMPY-*.log | head -1 | awk '{print \$NF}' | xargs cat"
```

Report: files synced, server restarted, structure verified.

## Shell rules (from CLAUDE.md)

- Double-quote all paths containing spaces
- No `$()` command substitution — run inner commands separately
- No backslash-escaped whitespace
- No `cd && command` — use full paths or `ssh host "command"`
- Prefer multiple simple commands over one compound command

## Pitfalls learned

1. **rsync broken**: Git Bash rsync on this machine has broken DLL. Always use scp.
2. **scp -r trailing slash**: `scp -r "src/salmopy/"` into a target that already has `salmopy/` creates `salmopy/salmopy/`. Use `scp -r "src/salmopy"` (no trailing slash) and copy into parent. Same goes for any fixture or module dir — always omit the trailing slash, or use `dir/.` to copy CONTENTS into an existing target.
3. **scp non-recursive glob**: `scp "dir/"*` fails on subdirectories. Use `scp -r "dir/."` to copy contents recursively.
4. **chmod pycache**: `chmod -R g+r` fails on `__pycache__` dirs owned by shiny user. Suppress with `2>/dev/null`.
5. **Server data path**: Test fixtures live at `data/fixtures/example_a/` on server (not `data/example_a/`).
6. **Stale fixtures**: `scp -r "dir/."` appends; it does NOT delete files that no longer exist in the source. When reach names change (e.g. `example_baltic` v1→v2 renamed `MainStem`→`Nemunas`), old CSVs linger. Always `rm -f *.csv` in the target fixture dir before scp. Step 6 does this explicitly.
7. **pyosmium missing on server**: the `shiny` micromamba env on laguna does NOT have `pyosmium` installed. As of v0.30.0, `app/modules/create_model_osm.py` guards the import so the app boots anyway — but the Create Model panel's `Fetch Rivers` / `Fetch Water` buttons raise `RuntimeError: pyosmium not installed` on click. To enable OSM fetching on production, SSH in and run `micromamba install -n shiny -c conda-forge pyosmium -y` directly (the conda solver is sometimes slow; expect 1-3 minutes).
8. **Shiny Server log path**: per-app logs live at `/var/log/shiny-server/inSTREAMPY-shiny-<timestamp>-<pid>.log`. The latest one has the stack trace of the most recent crash — see Step 8.
9. **Skill drifts from reality**: this file pins fixture names + the package directory. Both change. v0.20 renamed `src/instream/` → `src/salmopy/`; v0.45.0 added 4 WGBAST rivers (byskealven, morrumsan, simojoki, tornionjoki). Before deploying, sanity-check `ls src/` and `ls tests/fixtures/` — if there's a directory the skill doesn't list, add it here.
10. **PyPI Trusted Publisher OIDC**: tag-push triggers `.github/workflows/release.yml` which uses PyPI Trusted Publishing. Recurring failure mode `invalid-publisher: ... Publisher with matching claims was not found` with `environment: MISSING` in the failed claims means the PyPI publisher record expects an `environment:` declaration the workflow doesn't provide. Last seen on v0.44.1, v0.44.2, v0.45.2, v0.45.3, v0.46.0. Doesn't block laguna deploy or GitHub release; needs fixing on PyPI side or in `release.yml` (`environment: pypi` in the publish job).
