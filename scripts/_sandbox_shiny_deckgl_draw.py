"""Minimum-viable Shiny + shiny_deckgl drawing-app sandbox.

Run: micromamba run -n shiny shiny run scripts/_sandbox_shiny_deckgl_draw.py --port 8765

Click "Enable line draw" -> draw a line on the map -> click "Get features".
The features should appear in the right-hand panel. This validates the
correct sequence of API calls + the input-name pattern that Tasks A2/A3
will use.

Validated pattern (from plan + library inspection; empirical browser
verification deferred):
  1. await _widget.enable_draw(session, modes=["draw_line_string"|"draw_polygon"], default_mode=...)
  2. user draws on the map
  3. await _widget.get_drawn_features(session)  # side-effect TRIGGER, returns None
  4. features = getattr(input, _widget.drawn_features_input_id)()  # may be auto-pushed by JS
  5. await _widget.delete_drawn_features(session) + disable_draw(session) on completion

Notes (verified against shiny_deckgl 2026-04-25):
  * `enable_draw(session, *, modes=None, controls=None, default_mode='simple_select')`
     -> None. Takes `modes: list[str]` (NOT `mode: str`).
  * Mode names use the "draw_" prefix: "draw_line_string", "draw_polygon", "draw_point".
  * `get_drawn_features(session) -> None`: a trigger, not a getter. The reactive
    input `_widget.drawn_features_input_id` is what holds the actual GeoJSON
    feature list pushed by the JS-side draw layer.
  * For widget id "smap" (no module prefix), the auto-registered inputs are
    "smap_drawn_features", "smap_feature_click", "smap_click". With Shiny module
    prefixing, these become "<module_id>-<widget_id>_drawn_features", etc. —
    always read via `getattr(input, _widget.drawn_features_input_id)()`, never
    hardcode the string.
"""
from shiny import App, reactive, render, ui
from shiny_deckgl import MapWidget, head_includes

_widget = MapWidget(
    "smap",
    view_state={"longitude": 22.0, "latitude": 56.0, "zoom": 6},
    controls=[{"type": "navigation", "position": "top-right"}],
)

app_ui = ui.page_fluid(
    head_includes(),
    ui.h3("shiny_deckgl draw API sandbox"),
    ui.row(
        ui.column(
            4,
            ui.input_action_button("enable_line", "Enable line draw"),
            ui.input_action_button("enable_poly", "Enable polygon draw"),
            ui.input_action_button("disable", "Disable draw"),
            ui.input_action_button("get_feats", "Trigger get_drawn_features"),
            ui.input_action_button("delete_feats", "Delete drawn features"),
            ui.hr(),
            ui.h5("Reactive inputs:"),
            ui.output_text_verbatim("inputs_dump"),
        ),
        ui.column(8, _widget.ui(height="600px")),
    ),
)


def server(input, output, session):
    @reactive.effect
    @reactive.event(input.enable_line)
    async def _():
        await _widget.enable_draw(
            session, modes=["draw_line_string"], default_mode="draw_line_string",
        )

    @reactive.effect
    @reactive.event(input.enable_poly)
    async def _():
        await _widget.enable_draw(
            session, modes=["draw_polygon"], default_mode="draw_polygon",
        )

    @reactive.effect
    @reactive.event(input.disable)
    async def _():
        await _widget.disable_draw(session)

    @reactive.effect
    @reactive.event(input.get_feats)
    async def _():
        await _widget.get_drawn_features(session)

    @reactive.effect
    @reactive.event(input.delete_feats)
    async def _():
        await _widget.delete_drawn_features(session)

    @output
    @render.text
    def inputs_dump():
        out_lines = [
            f"_widget.drawn_features_input_id = {_widget.drawn_features_input_id!r}",
            f"_widget.feature_click_input_id  = {_widget.feature_click_input_id!r}",
            f"_widget.click_input_id          = {_widget.click_input_id!r}",
            "",
            "Reactive values (None if not yet pushed by JS):",
        ]
        for prop in ("drawn_features_input_id", "feature_click_input_id", "click_input_id"):
            name = getattr(_widget, prop)
            try:
                val = getattr(input, name)()
            except Exception as exc:
                val = f"<read error: {exc}>"
            out_lines.append(f"  input.{name}() = {val!r}")
        return "\n".join(out_lines)


app = App(app_ui, server)
