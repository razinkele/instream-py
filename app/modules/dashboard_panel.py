"""Dashboard panel — live simulation metrics with KPI cards and Plotly charts."""

from shiny import module, reactive, render, ui


def build_dashboard_payload(snapshots, start_idx, reset=False):
    """Build a payload dict for the JS dashboard_update handler.

    Parameters
    ----------
    snapshots : list[dict]
        Accumulated metrics snapshots from the simulation.
    start_idx : int
        Index of the first new snapshot to include in traces.
    reset : bool
        If True, include species list for Plotly.react(). If False, for extendTraces().
    """
    if not snapshots:
        return None

    new = snapshots[start_idx:]
    if not new:
        return None

    latest = new[-1]
    alive_total = sum(latest["alive"].values())
    denom = max(alive_total, 1)

    species = list(snapshots[0]["alive"].keys())
    n_species = len(species)

    dates = [s["date"] for s in new]

    pop_x = [list(dates) for _ in range(n_species)]
    pop_y = [[s["alive"].get(sp, 0) for s in new] for sp in species]

    mort_x = [list(dates)]
    mort_y = [[s["deaths_today"] for s in new]]

    feed_x = [list(dates) for _ in range(4)]
    feed_y = [
        [s["drift_count"] for s in new],
        [s["search_count"] for s in new],
        [s["hide_count"] for s in new],
        [s["other_count"] for s in new],
    ]

    redd_x = [list(dates)]
    redd_y = [[s["redd_count"] for s in new]]

    payload = {
        "kpi": {
            "alive": alive_total,
            "deaths": latest["deaths_today"],
            "drift_pct": int(latest["drift_count"] / denom * 100),
            "search_pct": int(latest["search_count"] / denom * 100),
            "other_pct": int(latest["other_count"] / denom * 100),
            "redds": latest["redd_count"],
            "eggs": latest["eggs_total"],
        },
        "reset": reset,
        "traces": {
            "population": {"x": pop_x, "y": pop_y},
            "mortality": {"x": mort_x, "y": mort_y},
            "feeding": {"x": feed_x, "y": feed_y},
            "redds": {"x": redd_x, "y": redd_y},
        },
    }
    if reset:
        payload["species"] = species

    return payload


DASHBOARD_JS = """
function safeExtend(divId, update, indices) {
    var div = document.getElementById(divId);
    if (!div || !div.data || div.data.length === 0) return;
    Plotly.extendTraces(divId, update, indices);
}

Shiny.addCustomMessageHandler('dashboard_update', function(msg) {
    var el;
    el = document.getElementById('kpi-alive');
    if (el) el.textContent = msg.kpi.alive;
    el = document.getElementById('kpi-deaths');
    if (el) el.textContent = msg.kpi.deaths;
    el = document.getElementById('kpi-feeding');
    if (el) el.textContent = 'drift ' + msg.kpi.drift_pct + '% / search ' + msg.kpi.search_pct + '%';
    el = document.getElementById('kpi-redds');
    if (el) el.textContent = msg.kpi.redds + ' (' + msg.kpi.eggs + ' eggs)';

    if (msg.reset) {
        var popTraces = msg.species.map(function(sp, i) {
            return {x: msg.traces.population.x[i], y: msg.traces.population.y[i],
                    name: sp, mode: 'lines'};
        });
        Plotly.react('dash-pop-chart', popTraces, {
            title: 'Population', template: 'plotly_white',
            margin: {t:30, b:30, l:50, r:20}, hovermode: 'x unified'
        });
        Plotly.react('dash-mort-chart',
            [{x: msg.traces.mortality.x[0], y: msg.traces.mortality.y[0],
              name: 'Deaths', mode: 'lines', line: {color: '#c64'}}],
            {title: 'Daily Mortality', template: 'plotly_white',
             margin: {t:30, b:30, l:50, r:20}});
        var feedNames = ['Drift', 'Search', 'Hide', 'Other'];
        var feedColors = ['#48c', '#8c4', '#999', '#888'];
        var feedTraces = feedNames.map(function(n, i) {
            return {x: msg.traces.feeding.x[i], y: msg.traces.feeding.y[i],
                    name: n, stackgroup: 'feed', line: {color: feedColors[i]}};
        });
        Plotly.react('dash-feed-chart', feedTraces, {
            title: 'Feeding Activity', template: 'plotly_white',
            margin: {t:30, b:30, l:50, r:20}});
        Plotly.react('dash-redd-chart',
            [{x: msg.traces.redds.x[0], y: msg.traces.redds.y[0],
              name: 'Active Redds', mode: 'lines', line: {color: '#a48'}}],
            {title: 'Redds', template: 'plotly_white',
             margin: {t:30, b:30, l:50, r:20}});
    } else {
        var popIdx = msg.traces.population.x.map(function(_, i) { return i; });
        safeExtend('dash-pop-chart', msg.traces.population, popIdx);
        safeExtend('dash-mort-chart', msg.traces.mortality, [0]);
        safeExtend('dash-feed-chart', msg.traces.feeding, [0, 1, 2, 3]);
        safeExtend('dash-redd-chart', msg.traces.redds, [0]);
    }
});
"""


@module.ui
def dashboard_ui():
    return ui.card(
        ui.card_header("Live Dashboard"),
        ui.layout_columns(
            ui.div(
                ui.tags.div(
                    "ALIVE", style="font-size:11px;color:#666;text-transform:uppercase;"
                ),
                ui.tags.div(
                    "—",
                    id="kpi-alive",
                    style="font-size:24px;font-weight:bold;color:#2a6;",
                ),
                style="background:#e8f4e8;border-radius:6px;padding:12px;text-align:center;",
            ),
            ui.div(
                ui.tags.div(
                    "DEATHS TODAY",
                    style="font-size:11px;color:#666;text-transform:uppercase;",
                ),
                ui.tags.div(
                    "—",
                    id="kpi-deaths",
                    style="font-size:24px;font-weight:bold;color:#c64;",
                ),
                style="background:#fef3e0;border-radius:6px;padding:12px;text-align:center;",
            ),
            ui.div(
                ui.tags.div(
                    "FEEDING",
                    style="font-size:11px;color:#666;text-transform:uppercase;",
                ),
                ui.tags.div(
                    "—",
                    id="kpi-feeding",
                    style="font-size:24px;font-weight:bold;color:#36a;",
                ),
                style="background:#e8eef8;border-radius:6px;padding:12px;text-align:center;",
            ),
            ui.div(
                ui.tags.div(
                    "REDDS", style="font-size:11px;color:#666;text-transform:uppercase;"
                ),
                ui.tags.div(
                    "—",
                    id="kpi-redds",
                    style="font-size:24px;font-weight:bold;color:#a48;",
                ),
                style="background:#f8e8f0;border-radius:6px;padding:12px;text-align:center;",
            ),
            col_widths=(3, 3, 3, 3),
        ),
        ui.tags.div(id="dash-pop-chart", style="width:100%;height:200px;"),
        ui.tags.div(id="dash-mort-chart", style="width:100%;height:150px;"),
        ui.tags.div(id="dash-feed-chart", style="width:100%;height:150px;"),
        ui.tags.div(id="dash-redd-chart", style="width:100%;height:150px;"),
        ui.output_ui("dash_status"),
    )


@module.server
def dashboard_server(input, output, session, dashboard_data_rv):
    _last_sent_idx = [0]

    @reactive.effect
    async def _push_updates():
        data = dashboard_data_rv()
        if not data:
            return

        current_len = len(data)
        if current_len < _last_sent_idx[0]:
            reset = True
            start = 0
        elif current_len > _last_sent_idx[0]:
            reset = _last_sent_idx[0] == 0
            start = _last_sent_idx[0]
        else:
            return

        payload = build_dashboard_payload(data, start, reset=reset)
        if payload is not None:
            await session.send_custom_message("dashboard_update", payload)
        _last_sent_idx[0] = current_len

    @output
    @render.ui
    def dash_status():
        data = dashboard_data_rv()
        if not data:
            return ui.p(
                "Run a simulation to see live metrics.",
                style="text-align:center;color:#888;padding:40px;",
            )
        return ui.TagList()
