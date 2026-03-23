---
name: deploy
description: Use when deploying the Shiny app to the server, after completing features or fixes, before demos, or when user says /deploy. Triggers on "deploy", "push to server", "update laguna".
---

# Deploy inSTREAM-py Shiny App

Deploy the Shiny frontend to laguna.ku.lt Shiny Server.

**All commands must run from the project root:** `C:\Users\DELL\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py`

## Steps

### 1. Test Gate

```bash
conda run -n shiny python -m pytest tests/ -q --tb=short
```

**Stop if tests fail.** Do not deploy broken code.

### 2. Confirm with User

Show what will be deployed:
- `app/` → `/srv/shiny-server/inSTREAMPY/` (with `--delete`)
- `configs/` → `.../configs/` (additive)
- `tests/fixtures/` → `.../data/` (additive)

Ask: "Deploy to laguna.ku.lt? (y/n)"

### 3. Sync (stop on any failure)

Run each command. If any fails, stop and report — do not continue.

```bash
rsync -avz --delete --exclude=configs --exclude=data "app/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/"
```

```bash
rsync -avz "configs/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/configs/"
```

```bash
rsync -avz "tests/fixtures/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/"
```

### 4. Permissions + Restart

```bash
ssh razinka@laguna.ku.lt "chmod -R g+r /srv/shiny-server/inSTREAMPY && touch /srv/shiny-server/inSTREAMPY/restart.txt"
```

If sudo is available, prefer: `sudo systemctl reload shiny-server`

### 5. Verify

```bash
ssh razinka@laguna.ku.lt "ls -la /srv/shiny-server/inSTREAMPY/app.py && echo 'OK: app.py present'"
```

Report: files synced, permissions set, server restarted, app.py confirmed.

## Connection Details

| Field | Value |
|-------|-------|
| Server | laguna.ku.lt |
| SSH user | razinka (passwordless) |
| Target | /srv/shiny-server/inSTREAMPY |
| Package | `instream` installed via `pip install -e .` on server |

## Shell Rules

- Double-quote all paths
- No `$()` substitution
- No backslash escapes
