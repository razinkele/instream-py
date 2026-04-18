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
├── src/instream/             ← from src/instream/ (simulation engine)
├── data/fixtures/            ← from tests/fixtures/ (example data)
└── restart.txt               ← touch to restart Shiny Server
```

## Steps

### 1. Test gate

```bash
conda run -n shiny python -m pytest tests/ -q --tb=short
```

**Stop if tests fail.** Do not deploy broken code.

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

**IMPORTANT:** Use `scp -r "src/instream"` (no trailing slash) to copy INTO `src/`.
A trailing slash creates double-nesting (`src/instream/instream/`).

```bash
ssh razinka@laguna.ku.lt "rm -rf /srv/shiny-server/inSTREAMPY/src/instream"
```

```bash
scp -r "src/instream" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/src/"
```

### 5. Deploy configs

```bash
scp "configs/"*.yaml "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/configs/"
```

### 6. Deploy data fixtures

For each fixture directory, **wipe stale files first** — `scp -r` appends
to existing directories and leaves dead files behind. When reach names
change between versions (e.g. `example_baltic`'s v1→v2 rename moved
`MainStem` → `Nemunas`), the old CSVs would linger otherwise.

```bash
ssh razinka@laguna.ku.lt "rm -f /srv/shiny-server/inSTREAMPY/data/fixtures/example_a/*.csv /srv/shiny-server/inSTREAMPY/data/fixtures/example_a/Shapefile/*"
scp -r "tests/fixtures/example_a/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_a/"
```

```bash
ssh razinka@laguna.ku.lt "rm -f /srv/shiny-server/inSTREAMPY/data/fixtures/example_b/*.csv /srv/shiny-server/inSTREAMPY/data/fixtures/example_b/Shapefile/*"
scp -r "tests/fixtures/example_b/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_b/"
```

```bash
ssh razinka@laguna.ku.lt "mkdir -p /srv/shiny-server/inSTREAMPY/data/fixtures/example_baltic/Shapefile && rm -f /srv/shiny-server/inSTREAMPY/data/fixtures/example_baltic/*.csv /srv/shiny-server/inSTREAMPY/data/fixtures/example_baltic/Shapefile/*"
scp -r "tests/fixtures/example_baltic/." "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/fixtures/example_baltic/"
```

Note: `/.` suffix copies directory contents without creating a nested directory.

### 7. Restart and verify

```bash
ssh razinka@laguna.ku.lt "chmod -R g+r /srv/shiny-server/inSTREAMPY 2>/dev/null; touch /srv/shiny-server/inSTREAMPY/restart.txt"
```

```bash
ssh razinka@laguna.ku.lt "ls -la /srv/shiny-server/inSTREAMPY/app.py && ls /srv/shiny-server/inSTREAMPY/src/instream/__init__.py && echo 'OK: deploy verified'"
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
2. **scp -r trailing slash**: `scp -r "src/instream/"` into a target that already has `instream/` creates `instream/instream/`. Use `scp -r "src/instream"` (no trailing slash) and copy into parent.
3. **scp non-recursive glob**: `scp "dir/"*` fails on subdirectories. Use `scp -r "dir/."` to copy contents recursively.
4. **chmod pycache**: `chmod -R g+r` fails on `__pycache__` dirs owned by shiny user. Suppress with `2>/dev/null`.
5. **Server data path**: Test fixtures live at `data/fixtures/example_a/` on server (not `data/example_a/`).
6. **Stale fixtures**: `scp -r "dir/."` appends; it does NOT delete files that no longer exist in the source. When reach names change (e.g. `example_baltic` v1→v2 renamed `MainStem`→`Nemunas`), old CSVs linger. Always `rm -f *.csv` in the target fixture dir before scp. Step 6 does this explicitly.
7. **pyosmium missing on server**: the `shiny` micromamba env on laguna does NOT have `pyosmium` installed. As of v0.30.0, `app/modules/create_model_osm.py` guards the import so the app boots anyway — but the Create Model panel's `Fetch Rivers` / `Fetch Water` buttons raise `RuntimeError: pyosmium not installed` on click. To enable OSM fetching on production, SSH in and run `micromamba install -n shiny -c conda-forge pyosmium -y` directly (the conda solver is sometimes slow; expect 1-3 minutes).
8. **Shiny Server log path**: per-app logs live at `/var/log/shiny-server/inSTREAMPY-shiny-<timestamp>-<pid>.log`. The latest one has the stack trace of the most recent crash — see Step 8.
