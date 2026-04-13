"""SalmoPy — individual-based salmonid simulation explorer."""

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
from shiny_deckgl import head_includes

from modules.population_panel import population_ui, population_server
from modules.environment_panel import environment_ui, environment_server
from modules.distribution_panel import distribution_ui, distribution_server
from modules.redd_panel import redd_ui, redd_server
from modules.spatial_panel import spatial_ui, spatial_server
from modules.help_panel import help_ui, help_server, TEST_CASES  # noqa: F401
from modules.dashboard_panel import dashboard_ui, dashboard_server, DASHBOARD_JS  # noqa: F401
from modules.movement_panel import movement_ui, movement_server  # noqa: E402
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

# --- Data directory resolution ---
# Local dev: app/ is a subdirectory of instream-py/, data is in inSTREAM/ (grandparent)
# Server:    app.py is at inSTREAMPY/ root, data is in inSTREAMPY/data/fixtures/
_APP_DIR = Path(__file__).resolve().parent
_LOCAL_DATA = (
    _APP_DIR.parent.parent
)  # inSTREAM/ (local dev: holds Example-Project-* dirs)
_SERVER_DATA = (
    _APP_DIR / "data" / "fixtures"
)  # server: holds example_a/, example_b/ dirs


def _resolve_data_dir(config_path):
    """Resolve the data directory for a given config file.

    Local dev: returns inSTREAM/ parent directory (Example-Project-A_1Reach-1Species/ etc.)
    Server:    returns data/fixtures/example_a/ (matched by config stem)
    Fallback:  returns config file's parent directory
    """
    # Local: parent inSTREAM/ directory has Example-Project-* folders
    if (
        _LOCAL_DATA.exists()
        and (_LOCAL_DATA / "Example-Project-A_1Reach-1Species").exists()
    ):
        return str(_LOCAL_DATA)

    # Server: map config name to fixtures subdirectory
    if _SERVER_DATA.exists():
        config_stem = Path(config_path).stem  # e.g. "example_a"
        fixture_dir = _SERVER_DATA / config_stem
        if fixture_dir.exists():
            return str(fixture_dir)

    # Fallback: config file's own directory
    return str(Path(config_path).parent)


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h4("SalmoPy"),
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
    head_includes(),
    ui.tags.head(
        ui.tags.link(
            rel="stylesheet",
            href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
        ),
        ui.tags.script(
            src="https://cdn.plot.ly/plotly-2.35.2.min.js",
            charset="utf-8",
        ),
        ui.tags.script(DASHBOARD_JS),
    ),
    ui.navset_tab(
        ui.nav_panel("Dashboard", dashboard_ui("dash")),
        ui.nav_panel("Movement", movement_ui("movement")),
        ui.nav_panel("Population", population_ui("pop")),
        ui.nav_panel("Spatial", spatial_ui("spatial")),
        ui.nav_panel("Environment", environment_ui("env")),
        ui.nav_panel("Size Distribution", distribution_ui("dist")),
        ui.nav_panel("Redds", redd_ui("redds")),
        ui.nav_panel("Help & Tests", help_ui("help")),
    ),
    title=ui.div(
        ui.span("SalmoPy", style="flex:1;"),
        ui.popover(
            ui.span(
                ui.tags.i(class_="bi bi-info-circle", style="font-size:1.2rem;"),
                " About",
                style="cursor:pointer; opacity:0.85;",
            ),
            ui.h4("SalmoPy"),
            ui.p(
                "Individual-based salmonid population model. "
                "Python port of ",
                ui.a("inSTREAM 7", href="https://www.fs.usda.gov/treesearch/pubs/65856", target="_blank"),
                " / inSALMO, extended with marine lifecycle, "
                "Baltic Atlantic salmon calibration, and Numba-accelerated habitat selection."
            ),
            ui.tags.hr(),
            ui.p(
                ui.strong("Version: "), "0.29.0",
                ui.br(),
                ui.strong("Engine: "), "instream-py",
                ui.br(),
                ui.strong("Source: "),
                ui.a("github.com/razinkele/instream-py", href="https://github.com/razinkele/instream-py", target="_blank"),
                ui.br(),
                ui.strong("Funding: "), "Horizon Europe",
            ),
            placement="bottom",
        ),
        style="display:flex; align-items:center; gap:1rem; width:100%;",
    ),
    theme=shinyswatch.theme.flatly,
)


def server(input, output, session):
    results_rv = reactive.value(None)
    _progress_q = queue.Queue()
    _latest_progress = reactive.value((0, 1))
    _sim_state = reactive.value("idle")  # "idle", "running", "success", "error"
    _metrics_q = queue.Queue()
    _dashboard_data = reactive.value([])

    @reactive.extended_task
    async def run_sim_task(config_path, overrides):
        data_dir = _resolve_data_dir(config_path)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: run_simulation(
                config_path, overrides, _progress_q, _metrics_q, data_dir
            ),
        )

    @reactive.effect
    @reactive.event(input.run_btn)
    def _launch():
        import traceback

        try:
            config_path = input.config_file()
            if not config_path:
                ui.notification_show(
                    "Please select a configuration file.", type="error"
                )
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
            while not _metrics_q.empty():
                try:
                    _metrics_q.get_nowait()
                except Exception:
                    break
            _dashboard_data.set([])
            _latest_progress.set((0, 1))
            _sim_state.set("running")
            _active_task.set("sim")
            run_sim_task(config_path, overrides)
        except Exception as e:
            _sim_state.set("error")
            tb = traceback.format_exc()
            ui.notification_show(
                "Launch error: {}".format(str(e)), type="error", duration=30
            )
            Path(_APP_DIR / "app_error.log").write_text(tb)

    # Track which task is active to prevent race conditions
    _active_task = reactive.value("none")  # "none", "sim", "test"

    @reactive.effect
    def _poll_progress():
        state = _sim_state.get()
        if state != "running":
            return
        if _active_task() != "sim":
            return
        reactive.invalidate_later(1)

        with reactive.isolate():
            step, total = _latest_progress.get()
        try:
            while not _progress_q.empty():
                step, total = _progress_q.get_nowait()
        except Exception:
            pass
        _latest_progress.set((step, total))

        try:
            status = run_sim_task.status()
        except Exception:
            status = "running"

        if status == "success":
            with reactive.isolate():
                _dash_current = _dashboard_data.get()
            _dash_remaining = []
            try:
                while True:
                    _dash_remaining.append(_metrics_q.get_nowait())
            except Exception:
                pass
            if _dash_remaining:
                _dashboard_data.set(_dash_current + _dash_remaining)
            _sim_state.set("success")
            _active_task.set("none")
            results_rv.set(run_sim_task.result())
            ui.notification_show("Simulation complete!", type="message", duration=3)
        elif status == "error":
            _sim_state.set("error")
            _active_task.set("none")
            err = "unknown"
            try:
                err = str(run_sim_task.result())
            except Exception as ex:
                err = str(ex)
            ui.notification_show("Simulation failed: {}".format(err), type="error")

    @reactive.effect
    def _poll_dashboard():
        if _sim_state.get() != "running":
            return
        if _active_task() != "sim":
            return
        reactive.invalidate_later(2)
        with reactive.isolate():
            current = _dashboard_data.get()
        new_items = []
        try:
            while True:
                new_items.append(_metrics_q.get_nowait())
        except queue.Empty:
            pass
        if new_items:
            _dashboard_data.set(current + new_items)

    @output
    @render.text
    def progress_text():
        state = _sim_state.get()
        if state == "running":
            reactive.invalidate_later(2)
            with reactive.isolate():
                step, total = _latest_progress.get()
            pct = int(100 * step / max(total, 1))
            return "Running... {}% ({}/{} steps)".format(pct, step, total)
        elif state == "success":
            return "Complete!"
        elif state == "error":
            return "Error — see notification"
        return "Ready"

    # Wire panel modules
    population_server("pop", results_rv=results_rv)
    environment_server("env", results_rv=results_rv)
    distribution_server("dist", results_rv=results_rv)
    redd_server("redds", results_rv=results_rv)
    spatial_server("spatial", results_rv=results_rv)
    dashboard_server("dash", dashboard_data_rv=_dashboard_data)
    movement_server("movement", dashboard_data_rv=_dashboard_data)

    # --- Help & Test Cases ---
    _test_key = reactive.value(None)

    @reactive.extended_task
    async def run_test_task(config_path, overrides):
        data_dir = _resolve_data_dir(config_path)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: run_simulation(config_path, overrides, None, None, data_dir)
        )

    def _run_test(test_key):
        tc = TEST_CASES.get(test_key)
        if tc is None:
            return
        config_path = input.config_file()
        if not config_path:
            ui.notification_show("Select a configuration first.", type="error")
            return

        import yaml

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        overrides = {
            "simulation": {
                "start_date": tc["start_date"],
                "end_date": tc["end_date"],
            },
            "performance": {"backend": input.backend()},
        }
        if tc["overrides"] and "reaches" in raw:
            overrides["reaches"] = {}
            reach_overrides = {}
            for k, v in tc["overrides"].items():
                if k in ("drift_conc", "search_prod"):
                    reach_overrides[k] = 10**v
                else:
                    reach_overrides[k] = v
            for rname in raw["reaches"]:
                overrides["reaches"][rname] = dict(reach_overrides)

        _test_key.set(test_key)
        _sim_state.set("running")
        _active_task.set("test")
        ui.notification_show(
            "Running test: {}".format(tc["name"]), type="message", duration=3
        )
        run_test_task(config_path, overrides)

    set_test_results = help_server("help", run_test_callback=_run_test)

    @reactive.effect
    def _poll_test():
        key = _test_key()
        if key is None:
            return
        if _active_task() != "test":
            return
        reactive.invalidate_later(1)
        try:
            status = run_test_task.status()
        except Exception:
            return
        if status == "success":
            result = run_test_task.result()
            results_rv.set(result)
            _sim_state.set("success")
            _active_task.set("none")
            set_test_results(result, key)
            _test_key.set(None)
            ui.notification_show("Test complete!", type="message", duration=3)
        elif status == "error":
            _sim_state.set("error")
            _active_task.set("none")
            _test_key.set(None)
            err = "unknown"
            try:
                run_test_task.result()
            except Exception as ex:
                err = str(ex)
            ui.notification_show("Test failed: {}".format(err), type="error")


app = App(app_ui, server)
