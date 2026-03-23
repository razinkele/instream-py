"""Spatial panel — cell polygon map using shiny_deckgl."""

from shiny import module, render, ui


COLORING_VARS = {
    "depth": "Depth (cm)",
    "velocity": "Velocity (cm/s)",
    "available_drift": "Drift Food Available",
    "available_search": "Search Food Available",
    "fish_count": "Fish Density",
    "frac_spawn": "Spawn Fraction",
}


@module.ui
def spatial_ui():
    return ui.card(
        ui.card_header("Spatial View"),
        ui.input_select("color_var", "Color by:", choices=COLORING_VARS),
        ui.output_ui("spatial_map"),
    )


@module.server
def spatial_server(input, output, session, results_rv):
    @output
    @render.ui
    def spatial_map():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")

        gdf = results["cells"]
        if gdf.empty:
            return ui.p("No spatial data available.")

        color_var = input.color_var()
        if color_var not in gdf.columns:
            return ui.p(f"Variable '{color_var}' not available.")

        # Use matplotlib for reliable rendering (shiny_deckgl integration
        # can be swapped in later for interactive maps)
        return _fallback_plot(gdf, color_var)


def _fallback_plot(gdf, color_var):
    """Fallback matplotlib plot if shiny_deckgl is not available."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import io
    import base64
    from shiny import ui as sui

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    gdf.plot(column=color_var, ax=ax, legend=True, cmap="viridis")
    ax.set_title(f"Cells colored by {COLORING_VARS.get(color_var, color_var)}")
    ax.set_aspect("equal")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode()
    return sui.HTML(
        f'<img src="data:image/png;base64,{img_b64}" style="max-width:100%">'
    )
