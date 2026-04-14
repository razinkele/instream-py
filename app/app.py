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
from modules.setup_panel import setup_ui, setup_server
from modules.create_model_panel import create_model_ui, create_model_server
from simulation import run_simulation


# --- Discover available configs ---
CONFIGS_DIR = Path(__file__).parent / "configs"
if not CONFIGS_DIR.exists():
    CONFIGS_DIR = Path(__file__).parent.parent / "configs"
CONFIG_CHOICES = (
    {
        str(p): p.stem
        for p in sorted(CONFIGS_DIR.glob("*.yaml"))
        if p.stem.startswith("example")  # exclude species-only configs
    }
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

    Local dev: tests/fixtures/{config_stem}/ or inSTREAM/ parent directory
    Server:    data/fixtures/{config_stem}/
    Fallback:  config file's parent directory
    """
    config_stem = Path(config_path).stem  # e.g. "example_baltic"

    # Local dev: check tests/fixtures/{config_stem}/ first (Baltic, etc.)
    _local_fixtures = _APP_DIR.parent / "tests" / "fixtures" / config_stem
    if _local_fixtures.exists():
        return str(_local_fixtures)

    # Local dev: parent inSTREAM/ directory has Example-Project-* folders
    if (
        _LOCAL_DATA.exists()
        and (_LOCAL_DATA / "Example-Project-A_1Reach-1Species").exists()
    ):
        return str(_LOCAL_DATA)

    # Server: map config name to fixtures subdirectory
    if _SERVER_DATA.exists():
        fixture_dir = _SERVER_DATA / config_stem
        if fixture_dir.exists():
            return str(fixture_dir)

    # Fallback: config file's own directory
    return str(Path(config_path).parent)


_SIDEBAR_CSS = """
/* ── SalmoPy sidebar (AQUABC-aligned) ─────────────────────── */
:root {
    --sp-sidebar-w: 220px;
    --sp-sidebar-bg: #1e293b;
    --sp-accent: #2bb89d;
    --sp-text: rgba(255,255,255,.7);
    --sp-text-bright: #fff;
}
.sp-sidebar {
    width: var(--sp-sidebar-w); min-width: var(--sp-sidebar-w);
    background: var(--sp-sidebar-bg);
    display: flex; flex-direction: column;
    overflow-y: auto; height: 100vh; position: fixed; top: 0; left: 0; z-index: 1040;
    transition: width .25s ease, min-width .25s ease;
}
.sp-sidebar.collapsed { width: 56px; min-width: 56px; }
.sp-sidebar.collapsed .sp-label,
.sp-sidebar.collapsed .sp-section-title,
.sp-sidebar.collapsed .sp-config { display: none; }
.sp-sidebar.collapsed .sp-nav-link { justify-content: center; padding: .7rem 0; }
.sp-sidebar.collapsed .sp-nav-link i { margin-right: 0; }
.sp-sidebar.collapsed .sp-header { justify-content: center; padding: .6rem .4rem; }
.sp-sidebar.collapsed .sp-header-title { display: none; }

.sp-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: .75rem 1rem; background: rgba(0,0,0,.25);
    border-bottom: 1px solid rgba(255,255,255,.08);
}
.sp-header-title { color: var(--sp-accent); font-weight: 700; font-size: 1.05rem; letter-spacing: .5px; }
.sp-toggle {
    background: none; border: none; color: var(--sp-text-bright); font-size: 1.3rem;
    cursor: pointer; padding: .3rem .5rem; border-radius: 4px;
    transition: background .15s;
}
.sp-toggle:hover { background: rgba(255,255,255,.1); color: var(--sp-accent); }

.sp-section-title {
    font-size: .65rem; text-transform: uppercase; letter-spacing: 1.5px;
    color: rgba(255,255,255,.35); padding: .7rem 1rem .3rem; margin: 0;
}
.sp-nav { padding: .25rem 0; flex: 1; }
.sp-nav-link {
    display: flex; align-items: center; gap: .6rem;
    padding: .55rem 1rem; color: var(--sp-text);
    text-decoration: none; border-left: 3px solid transparent;
    font-size: .85rem; cursor: pointer; transition: all .15s;
}
.sp-nav-link:hover { background: rgba(43,184,157,.08); border-left-color: var(--sp-accent); color: var(--sp-text-bright); }
.sp-nav-link:hover i { color: var(--sp-accent); }
.sp-nav-link.active {
    background: rgba(43,184,157,.12); border-left-color: var(--sp-accent);
    color: var(--sp-text-bright); font-weight: 600;
}
.sp-nav-link.active i { color: var(--sp-accent); }
.sp-nav-link i { font-size: .95rem; width: 1.2rem; text-align: center; }

.sp-config {
    border-top: 1px solid rgba(255,255,255,.08);
    padding: .6rem .85rem; font-size: .78rem;
}
.sp-config label { color: var(--sp-text); font-size: .72rem; margin-bottom: .15rem; }
.sp-config select, .sp-config input[type="date"] {
    background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.12);
    color: var(--sp-text-bright); border-radius: 4px; padding: .25rem .4rem;
    font-size: .78rem; width: 100%;
}
.sp-config select:focus, .sp-config input:focus { border-color: var(--sp-accent); outline: none; }
.sp-config select option { background: #1e293b; color: #fff; }
.sp-config .btn-load-config {
    background: rgba(43,184,157,.2); color: var(--sp-accent); border: 1px solid var(--sp-accent);
    border-radius: 4px; padding: .3rem; width: 100%; font-size: .75rem; font-weight: 600;
    cursor: pointer; margin-top: .3rem; margin-bottom: .5rem;
}
.sp-config .btn-load-config:hover { background: rgba(43,184,157,.35); }
.sp-config .btn-run {
    background: var(--sp-accent); color: #fff; border: none; border-radius: 4px;
    padding: .4rem; width: 100%; font-size: .8rem; font-weight: 600;
    cursor: pointer; margin-top: .4rem;
}
.sp-config .btn-run:hover { filter: brightness(1.1); }
.sp-config .sp-progress { color: rgba(255,255,255,.5); font-size: .72rem; margin-top: .3rem; }

.sp-main-offset { margin-left: var(--sp-sidebar-w); transition: margin-left .25s ease; padding: 0; background: #f0f4f8; min-height: 100vh; }
body.sp-collapsed .sp-main-offset { margin-left: 56px; }
body { background: #f0f4f8; }

.sp-gpu-badge {
    display: inline-flex; align-items: center; gap: .3rem;
    background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
    color: #155724; border: 1px solid #b1dfbb; border-radius: 10px;
    padding: .15rem .55rem; font-size: .7rem; font-weight: 600;
    letter-spacing: .3px; margin-left: .6rem; vertical-align: middle;
    white-space: nowrap; cursor: help;
}
.sp-gpu-badge i { font-size: .75rem; }
"""

_SIDEBAR_JS = """
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('sp-sidebar');
    const toggle = document.getElementById('sp-toggle');
    if (toggle && sidebar) {
        toggle.onclick = function() {
            sidebar.classList.toggle('collapsed');
            document.body.classList.toggle('sp-collapsed');
        };
    }
    document.querySelectorAll('.sp-nav-link').forEach(function(link) {
        link.onclick = function(e) {
            e.preventDefault();
            document.querySelectorAll('.sp-nav-link').forEach(function(l) { l.classList.remove('active'); });
            link.classList.add('active');
            var tab = link.getAttribute('data-tab');
            // Update Shiny navset_hidden via its input binding
            Shiny.setInputValue('main_tabs', tab);
            // Also click the hidden nav links as fallback
            var hiddenLinks = document.querySelectorAll('[data-value]');
            hiddenLinks.forEach(function(hl) {
                if (hl.getAttribute('data-value') === tab) hl.click();
            });
        };
    });
});
"""

_NAV_ITEMS = [
    ("bi-plus-circle", "Create Model"),
    ("bi-map", "Setup"),
    ("bi-speedometer2", "Dashboard"),
    ("bi-arrow-left-right", "Movement"),
    ("bi-bar-chart-line", "Population"),
    ("bi-geo-alt", "Spatial"),
    ("bi-thermometer-half", "Environment"),
    ("bi-rulers", "Size Distribution"),
    ("bi-egg", "Redds"),
    ("bi-question-circle", "Help & Tests"),
]

_sidebar_nav_links = [
    ui.tags.a(
        {"class": f"sp-nav-link {'active' if i == 0 else ''}", "href": "#", "data-tab": label},
        ui.tags.i(class_=f"bi {icon}"),
        ui.tags.span(label, class_="sp-label"),
    )
    for i, (icon, label) in enumerate(_NAV_ITEMS)
]

_custom_sidebar = ui.tags.div(
    {"class": "sp-sidebar", "id": "sp-sidebar"},
    # Header
    ui.tags.div(
        {"class": "sp-header"},
        ui.tags.span("SalmoPy", class_="sp-header-title"),
        ui.tags.button(
            ui.tags.i(class_="bi bi-list"),
            id="sp-toggle", class_="sp-toggle", type="button",
        ),
    ),
    # Nav section
    ui.tags.div(
        {"class": "sp-section-title"}, "Views",
    ),
    ui.tags.div({"class": "sp-nav"}, *_sidebar_nav_links),
    # Config section
    ui.tags.div(
        {"class": "sp-section-title"}, "Simulation",
    ),
    ui.tags.div(
        {"class": "sp-config"},
        ui.tags.label("Configuration"),
        ui.input_select("config_file", None, choices=CONFIG_CHOICES, width="100%"),
        ui.input_action_button("load_config_btn", "Load Config", class_="btn-load-config"),
        ui.tags.label("Start Date"),
        ui.input_date("start_date", None, value="2011-04-01", width="100%"),
        ui.tags.label("End Date"),
        ui.input_date("end_date", None, value="2013-09-30", width="100%"),
        ui.tags.label("Backend"),
        ui.input_select("backend", None, choices=["numpy", "numba"], selected="numpy", width="100%"),
        ui.input_action_button("run_btn", "Run Simulation", class_="btn-run"),
        ui.tags.div(ui.output_text("progress_text"), class_="sp-progress"),
    ),
)

_WEBGL_FALLBACK_JS = """
(function() {
    var _msgStyle = 'padding:1.5rem 2rem; text-align:center; font:14px/1.6 sans-serif; border-radius:8px; margin:1rem;';

    var MSG_NO_WEBGL = '<div style="' + _msgStyle + 'background:#fff3cd; color:#856404; border:1px solid #ffeeba;">' +
        '<i class="bi bi-exclamation-triangle-fill" style="font-size:1.8rem; display:block; margin-bottom:.5rem;"></i>' +
        '<strong>WebGL Not Available</strong><br>' +
        'Your browser does not support WebGL, which is required for the interactive map.<br>' +
        '<small style="opacity:.8;">Try Chrome, Edge, or Firefox with hardware acceleration enabled.</small>' +
        '</div>';

    var MSG_GPU_BLOCKED = '<div style="' + _msgStyle + 'background:#f8d7da; color:#721c24; border:1px solid #f5c6cb;">' +
        '<i class="bi bi-shield-exclamation" style="font-size:1.8rem; display:block; margin-bottom:.5rem;"></i>' +
        '<strong>GPU Access Blocked</strong><br>' +
        'WebGL context creation failed &mdash; the GPU may be sandboxed or disabled by your browser.<br>' +
        '<small style="opacity:.8;">Check <code>chrome://gpu</code> or disable browser sandboxing. ' +
        'Headless browsers typically lack GPU support.</small>' +
        '</div>';

    var MSG_SOFTWARE = '<div style="' + _msgStyle + 'background:#cce5ff; color:#004085; border:1px solid #b8daff;">' +
        '<i class="bi bi-cpu" style="font-size:1.8rem; display:block; margin-bottom:.5rem;"></i>' +
        '<strong>Software Rendering Detected</strong><br>' +
        'Your browser is using a software renderer (no GPU acceleration).<br>' +
        'Maps are disabled to avoid poor performance.<br>' +
        '<small style="opacity:.8;">Enable hardware acceleration in browser settings for full map support.</small>' +
        '</div>';

    var MSG_INIT_FAILED = '<div style="' + _msgStyle + 'background:#f8d7da; color:#721c24; border:1px solid #f5c6cb;">' +
        '<i class="bi bi-x-circle" style="font-size:1.8rem; display:block; margin-bottom:.5rem;"></i>' +
        '<strong>Map Initialisation Failed</strong><br>' +
        'The map library encountered an error during setup.<br>' +
        '<small style="opacity:.8;">Check the browser console for details. Reloading the page may help.</small>' +
        '</div>';

    // Probe WebGL
    var canvas = document.createElement('canvas');
    canvas.width = 1; canvas.height = 1;
    var gl = null;
    var renderer = '';
    try {
        gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
            var dbg = gl.getExtension('WEBGL_debug_renderer_info');
            renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'unknown';
        }
    } catch(e) { gl = null; }

    // Determine reason for failure (if any)
    if (gl && /SwiftShader|llvmpipe/i.test(renderer)) {
        window._salmopyGpuReason = 'software';
        window._salmopyWebGL = false;  // software renderers too slow for maps
    } else if (gl) {
        window._salmopyGpuReason = null;
        window._salmopyWebGL = true;
    } else {
        window._salmopyGpuReason = 'none';
        window._salmopyWebGL = false;
    }
    console.info('[SalmoPy] WebGL probe:', window._salmopyWebGL, 'renderer:', renderer || 'n/a', 'reason:', window._salmopyGpuReason || 'ok');

    // Inject GPU badge into map-tab card headers
    if (window._salmopyWebGL) {
        var gpuLabel = renderer.replace('ANGLE (', '').split(',')[0].replace(')', '').trim() || 'GPU';
        var badgeHtml = '<span class="sp-gpu-badge" title="Rendering on: ' + renderer + '"><i class="bi bi-gpu-card"></i>WebGL \u2014 ' + gpuLabel + '</span>';
        function injectGpuBadges() {
            document.querySelectorAll('.card-header').forEach(function(hdr) {
                var txt = hdr.textContent || '';
                if ((/Spatial View|Live Movement|Setup Review|Create Model/i).test(txt) && !hdr.querySelector('.sp-gpu-badge')) {
                    hdr.insertAdjacentHTML('beforeend', badgeHtml);
                }
            });
        }
        // Poll briefly after page load — covers Shiny's async rendering
        var _badgeTimer = setInterval(function() {
            injectGpuBadges();
            if (document.querySelectorAll('.sp-gpu-badge').length >= 4) clearInterval(_badgeTimer);
        }, 400);
        // Stop polling after 15s regardless
        setTimeout(function() { clearInterval(_badgeTimer); }, 15000);
    }

    function patchWith(msg) {
        document.querySelectorAll('.deckgl-map').forEach(function(el) {
            if (!el._spPatched) { el._spPatched = true; el.innerHTML = msg; }
        });
    }

    if (!gl) {
        var earlyMsg = window._salmopyGpuReason === 'software' ? MSG_SOFTWARE : MSG_NO_WEBGL;
        var obs = new MutationObserver(function() { patchWith(earlyMsg); });
        document.addEventListener('DOMContentLoaded', function() {
            obs.observe(document.body, {childList: true, subtree: true});
        });
        document.addEventListener('shiny:connected', function() {
            patchWith(earlyMsg);
            setTimeout(function() { patchWith(earlyMsg); }, 1000);
            setTimeout(function() { patchWith(earlyMsg); }, 3000);
        });
    }

    // Catch runtime GPU sandbox / driver blocklist failures
    document.addEventListener('webglcontextcreationerror', function(e) {
        window._salmopyWebGL = false;
        window._salmopyGpuReason = 'blocked';
        patchWith(MSG_GPU_BLOCKED);
    }, true);

    // Poll for shiny_deckgl error divs and replace with specific messages
    document.addEventListener('shiny:connected', function() {
        function replaceErrors() {
            document.querySelectorAll('.deckgl-map').forEach(function(el) {
                if (el._spPatched) return;
                var txt = el.textContent || '';
                if (txt.indexOf('Map failed to initialise') >= 0) {
                    el._spPatched = true;
                    el.innerHTML = MSG_INIT_FAILED;
                } else if (txt.indexOf('Map libraries failed') >= 0) {
                    el._spPatched = true;
                    el.innerHTML = MSG_INIT_FAILED;
                } else if (el.children.length === 0 && el.innerHTML.trim() === '' && !window._salmopyWebGL) {
                    el._spPatched = true;
                    var reason = window._salmopyGpuReason;
                    el.innerHTML = reason === 'software' ? MSG_SOFTWARE :
                                   reason === 'blocked' ? MSG_GPU_BLOCKED : MSG_NO_WEBGL;
                }
            });
        }
        setTimeout(replaceErrors, 2000);
        setTimeout(replaceErrors, 5000);
        setTimeout(replaceErrors, 10000);
    });
})();
"""

app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.style(_SIDEBAR_CSS),
        ui.tags.script(_SIDEBAR_JS),
        ui.tags.script(_WEBGL_FALLBACK_JS),
        ui.include_css(Path(__file__).parent / "www" / "bootstrap-icons.min.css"),
        ui.tags.link(rel="icon", href="data:,"),
        ui.tags.script(
            src="https://cdn.plot.ly/plotly-2.35.2.min.js",
            charset="utf-8",
        ),
        ui.tags.script(DASHBOARD_JS),
    ),
    head_includes(),
    _custom_sidebar,
    ui.div(
        {"class": "sp-main-offset"},
        ui.navset_hidden(
            ui.nav_panel("Create Model", create_model_ui("create")),
            ui.nav_panel("Setup", setup_ui("setup")),
            ui.nav_panel("Dashboard", dashboard_ui("dash")),
            ui.nav_panel("Movement", movement_ui("movement")),
            ui.nav_panel("Population", population_ui("pop")),
            ui.nav_panel("Spatial", spatial_ui("spatial")),
            ui.nav_panel("Environment", environment_ui("env")),
            ui.nav_panel("Size Distribution", distribution_ui("dist")),
            ui.nav_panel("Redds", redd_ui("redds")),
            ui.nav_panel("Help & Tests", help_ui("help")),
            id="main_tabs",
        ),
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
        try:
            result = await loop.run_in_executor(
                None,
                lambda: run_simulation(
                    config_path, overrides, _progress_q, _metrics_q, data_dir
                ),
            )
            _progress_q.put(("__DONE__", result))
            return result
        except Exception as e:
            _progress_q.put(("__ERROR__", str(e)))
            raise

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
            # Build reach overrides (sliders may not be rendered yet)
            def _safe(getter, default):
                try:
                    return getter()
                except BaseException:
                    return default

            reach_overrides = {
                "drift_conc": 10 ** _safe(input.drift_conc, -9),
                "search_prod": 10 ** _safe(input.search_prod, -6),
                "shading": _safe(input.shading, 0.8),
                "fish_pred_min": _safe(input.fish_pred_min, 0.97),
                "terr_pred_min": _safe(input.terr_pred_min, 0.94),
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
            results_rv.set(None)  # Clear stale results from previous run
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
                item = _progress_q.get_nowait()
                if isinstance(item, tuple) and len(item) == 2 and item[0] == "__DONE__":
                    # Drain remaining dashboard metrics
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
                    results_rv.set(item[1])
                    ui.notification_show(
                        "Simulation complete!", type="message", duration=3
                    )
                    return
                if isinstance(item, tuple) and len(item) == 2 and item[0] == "__ERROR__":
                    _sim_state.set("error")
                    _active_task.set("none")
                    ui.notification_show(
                        "Simulation failed: {}".format(item[1]),
                        type="error",
                        duration=30,
                    )
                    return
                # Normal progress tuple (int, int)
                step, total = item
        except Exception:
            pass
        _latest_progress.set((step, total))

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
    create_model_server("create")
    setup_server("setup", config_file_rv=input.config_file, load_btn_rv=input.load_config_btn)
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
