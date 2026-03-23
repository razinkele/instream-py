"""Redd panel — redd count timeline + details table."""

from shiny import module, render, ui


@module.ui
def redd_ui():
    return ui.card(
        ui.card_header("Redd Tracking"),
        ui.output_ui("redd_plot"),
        ui.card_header("Redd Details (End of Simulation)"),
        ui.output_table("redd_table"),
    )


@module.server
def redd_server(input, output, session, results_rv):
    @output
    @render.ui
    def redd_plot():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")
        df = results["daily"]
        if df.empty:
            return ui.p("No data available.")

        import plotly.graph_objects as go
        from shiny import ui as sui

        # Aggregate across species for redd metrics (same value per species per day)
        redd_df = df.groupby("date").first().reset_index()
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=redd_df["date"],
                y=redd_df["redd_count"],
                name="Active Redds",
                mode="lines",
            )
        )
        if "eggs_total" in redd_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=redd_df["date"],
                    y=redd_df["eggs_total"],
                    name="Total Eggs",
                    mode="lines",
                    yaxis="y2",
                )
            )
        fig.update_layout(
            template="plotly_white",
            title="Redd Activity Over Time",
            yaxis=dict(title="Count"),
            yaxis2=dict(title="Eggs", overlaying="y", side="right"),
        )
        return sui.HTML(fig.to_html(full_html=False, include_plotlyjs="cdn"))

    @output
    @render.table
    def redd_table():
        results = results_rv()
        if results is None:
            return None
        redds = results["redds"]
        if redds.empty:
            return None
        return redds.round(4)
