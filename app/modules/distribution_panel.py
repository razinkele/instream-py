"""Distribution panel — fish length/weight histograms at selected date."""

from shiny import module, reactive, render, ui


@module.ui
def distribution_ui():
    return ui.card(
        ui.card_header("Fish Size Distribution"),
        ui.input_select("snapshot_date", "Select Date", choices=[]),
        ui.output_ui("distribution_plot"),
    )


@module.server
def distribution_server(input, output, session, results_rv):
    @reactive.effect
    def _update_date_choices():
        results = results_rv()
        if results is None:
            return
        dates = sorted(results["snapshots"].keys())
        ui.update_select(
            "snapshot_date", choices=dates, selected=dates[-1] if dates else None
        )

    @output
    @render.ui
    def distribution_plot():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")
        snapshots = results["snapshots"]
        sel = input.snapshot_date()
        if not sel or sel not in snapshots:
            return ui.p("No snapshot available for selected date.")

        from plotly.subplots import make_subplots
        from shiny import ui as sui

        df = snapshots[sel]
        fig = make_subplots(
            rows=1, cols=2, subplot_titles=("Length (cm)", "Weight (g)")
        )
        for sp in df["species"].unique():
            sp_df = df[df["species"] == sp]
            import plotly.graph_objects as go

            fig.add_trace(
                go.Histogram(x=sp_df["length"], name=sp, legendgroup=sp, opacity=0.7),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Histogram(
                    x=sp_df["weight"],
                    name=sp,
                    legendgroup=sp,
                    showlegend=False,
                    opacity=0.7,
                ),
                row=1,
                col=2,
            )
        fig.update_layout(
            template="plotly_white",
            barmode="overlay",
            title=f"Fish Size Distribution — {sel}",
        )
        return sui.HTML(fig.to_html(full_html=False, include_plotlyjs=False))
