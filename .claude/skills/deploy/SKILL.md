---
name: deploy
description: Deploy the inSTREAM-py Shiny app to laguna.ku.lt. Use when user says /deploy or asks to deploy the app.
---

# Deploy inSTREAM-py Shiny App

When invoked via `/deploy`, perform these steps:

## 1. Run Tests

Run the test suite to gate the deployment:

```bash
conda run -n shiny python -m pytest tests/ -q --tb=short
```

If tests fail, stop and report the failures. Do not deploy broken code.

## 2. Sync App Files

```bash
rsync -avz --delete --exclude=configs --exclude=data "app/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/"
```

## 3. Sync Configs

```bash
rsync -avz "configs/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/configs/"
```

## 4. Sync Data

```bash
rsync -avz "tests/fixtures/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/"
```

## 5. Set Permissions and Restart

```bash
ssh razinka@laguna.ku.lt "chmod -R g+r /srv/shiny-server/inSTREAMPY && touch /srv/shiny-server/inSTREAMPY/restart.txt"
```

If `sudo` is available, use `sudo systemctl reload shiny-server` instead of `touch restart.txt`.

## 6. Verify

```bash
ssh razinka@laguna.ku.lt "ls -la /srv/shiny-server/inSTREAMPY/app.py"
```

Report the deployment status: files synced, permissions set, server restarted.

## Notes

- SSH user: `razinka` (passwordless SSH required)
- Server: `laguna.ku.lt`
- Target directory: `/srv/shiny-server/inSTREAMPY`
- The `instream` package must be installed on the server via `pip install -e .` from a repo clone
- All commands must use double-quoted paths (no backslash escapes, no `$()`)
