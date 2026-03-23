"""inSTREAM-py Shiny Frontend — main application."""

import asyncio
import queue
import sys
from pathlib import Path

# Ensure instream package is importable (deployed as src/instream/ on server)
_src = Path(__file__).parent / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from shiny import App, reactive, render, ui
import shinyswatch

from modules.population_panel import population_ui, population_server
from modules.environment_panel import environment_ui, environment_server
from modules.distribution_panel import distribution_ui, distribution_server
from modules.redd_panel import redd_ui, redd_server
from modules.spatial_panel import spatial_ui, spatial_server
from simulation import run_simulation


# --- Discover available configs ---
CONFIGS_DIR = Path(__file__).parent / "configs"
if not CONFIGS_DIR.exists():
    CONFIGS_DIR = Path(__file__).parent.parent / "configs"
CONFIG_CHOICES = (
    {str(p): p.stem for p in sorted(CONFIGS_DIR.glob("*.yaml"))}
    if CONFIGS_DIR.exists()
    else {}
)


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h4("inSTREAM-py"),
        ui.input_select("config_file", "Configuration", choices=CONFIG_CHOICES),
        ui.input_date("start_date", "Start Date", value="2011-04-01"),
        ui.input_date("end_date", "End Date", value="2013-09-30"),
        ui.hr(),
        ui.h5("Reach Parameters"),
        ui.input_slider(
            "drift_conc",
            "Drift Concentration",
            min=-12,
            max=-6,
            value=-9.5,
            step=0.5,
            post=" (10^x)",
        ),
        ui.input_slider(
            "search_prod",
            "Search Productivity",
            min=-8,
            max=-4,
            value=-6,
            step=0.5,
            post=" (10^x)",
        ),
        ui.input_slider("shading", "Shading", min=0, max=1, value=0.85, step=0.05),
        ui.input_slider(
            "fish_pred_min", "Fish Pred. Min", min=0.8, max=1, value=0.95, step=0.01
        ),
        ui.input_slider(
            "terr_pred_min", "Terr. Pred. Min", min=0.8, max=1, value=0.92, step=0.01
        ),
        ui.hr(),
        ui.input_select(
            "backend", "Backend", choices=["numpy", "numba"], selected="numpy"
        ),
        ui.input_action_button("run_btn", "Run Simulation", class_="btn-primary w-100"),
        ui.output_text("progress_text"),
        width=320,
    ),
    ui.navset_tab(
        ui.nav_panel("Population", population_ui("pop")),
        ui.nav_panel("Spatial", spatial_ui("spatial")),
        ui.nav_panel("Environment", environment_ui("env")),
        ui.nav_panel("Size Distribution", distribution_ui("dist")),
        ui.nav_panel("Redds", redd_ui("redds")),
    ),
    title="inSTREAM-py Simulation Explorer",
    theme=shinyswatch.theme.flatly,
)


def server(input, output, session):
    results_rv = reactive.value(None)
    _progress_q = queue.Queue()
    _latest_progress = reactive.value((0, 1))

    @reactive.extended_task
    async def run_sim_task(config_path, overrides):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, run_simulation, config_path, overrides, _progress_q
        )

    @reactive.effect
    @reactive.event(input.run_btn)
    def _launch():
        config_path = input.config_file()
        if not config_path:
            ui.notification_show("Please select a configuration file.", type="error")
            return
        overrides = {
            "simulation": {
                "start_date": str(input.start_date()),
                "end_date": str(input.end_date()),
            },
            "performance": {"backend": input.backend()},
        }
        # Build reach overrides
        reach_overrides = {
            "drift_conc": 10 ** input.drift_conc(),
            "search_prod": 10 ** input.search_prod(),
            "shading": input.shading(),
            "fish_pred_min": input.fish_pred_min(),
            "terr_pred_min": input.terr_pred_min(),
        }
        # Load config to get reach names
        import yaml

        with open(config_path) as f:
            raw = yaml.safe_load(f)
        if "reaches" in raw:
            overrides["reaches"] = {}
            for rname in raw["reaches"]:
                overrides["reaches"][rname] = dict(reach_overrides)

        # Drain queue safely (thread-safe)
        while not _progress_q.empty():
            try:
                _progress_q.get_nowait()
            except Exception:
                break
        _latest_progress.set((0, 1))
        run_sim_task(config_path, overrides)

    @reactive.effect
    def _poll_progress():
        status = run_sim_task.status()
        if status == "running":
            reactive.invalidate_later(1)
            # Drain queue into reactive value (single consumer)
            step, total = _latest_progress.get()
            try:
                while not _progress_q.empty():
                    step, total = _progress_q.get_nowait()
            except Exception:
                pass
            _latest_progress.set((step, total))
        elif status == "success":
            results_rv.set(run_sim_task.result())
            ui.notification_show("Simulation complete!", type="message", duration=3)
        elif status == "error":
            ui.notification_show(
                f"Simulation failed: {run_sim_task.error()}", type="error"
            )

    @output
    @render.text
    def progress_text():
        status = run_sim_task.status()
        if status == "running":
            step, total = _latest_progress.get()
            pct = int(100 * step / max(total, 1))
            return f"Running... {pct}% ({step}/{total} steps)"
        elif status == "success":
            return "Complete!"
        elif status == "error":
            return "Error — see notification"
        return "Ready"

    # Wire panel modules
    population_server("pop", results_rv=results_rv)
    environment_server("env", results_rv=results_rv)
    distribution_server("dist", results_rv=results_rv)
    redd_server("redds", results_rv=results_rv)
    spatial_server("spatial", results_rv=results_rv)


app = App(app_ui, server)
