---
name: run-app
description: Start the inSTREAM Shiny app locally for manual testing. Use when user says /run-app, "run the app", "start the app", "manual testing", or "test the frontend".
---

# Run inSTREAM-py Shiny App Locally

Start the Shiny frontend on localhost for manual testing.

**Project root:** The instream-py directory containing `app/`, `src/`, `configs/`.

## Steps

### 1. Kill any existing app processes

Check for and kill any Python processes already bound to port 8000:

```bash
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true
```

On Windows (Git Bash), use:

```bash
netstat -ano 2>/dev/null | grep ":8000 " | grep LISTENING | awk '{print $5}' | sort -u | while read pid; do taskkill //F //PID "$pid" 2>/dev/null; done || true
```

### 2. Start the app

Run from the `app/` directory using nohup so the process survives:

```bash
cd "<project-root>/app" && nohup micromamba run -n shiny shiny run --reload --port 8000 app:app > /tmp/instream-app.log 2>&1 &
```

The `--reload` flag enables auto-restart on file changes.

### 3. Verify startup

Wait 3 seconds, then check the log for successful startup:

```bash
sleep 3 && cat /tmp/instream-app.log
```

Look for: `Uvicorn running on http://127.0.0.1:8000`

If startup failed, read the full log and diagnose the error.

### 4. Report

Tell the user:
- App is running at **http://127.0.0.1:8000**
- Auto-reload is enabled (file changes take effect automatically)
- To view logs: `cat /tmp/instream-app.log`
- To stop: `lsof -ti:8000 | xargs kill` (or on Windows: find PID with `netstat -ano | grep :8000` and `taskkill //F //PID <pid>`)

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Port 8000 already in use | Step 1 should handle this. If not, manually find and kill the process. |
| ModuleNotFoundError | Ensure micromamba env `shiny` has all deps: `micromamba run -n shiny pip list` |
| App exits immediately | Check `/tmp/instream-app.log` for traceback. Common: missing config YAML or fixture data. |
| Import error for shiny_deckgl | Install: `micromamba run -n shiny pip install shiny-deckgl` |
