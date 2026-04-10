"""Population panel — fish alive count by species over time."""

from shiny import module, render, ui


@module.ui
def population_ui():
    return ui.card(
        ui.card_header("Population Over Time"),
        ui.output_ui("population_plot"),
    )


@module.server
def population_server(input, output, session, results_rv):
    @output
    @render.ui
    def population_plot():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")
        df = results["daily"]
        if df.empty:
            return ui.p("No daily data collected.")

        import plotly.express as px
        from shiny import ui as sui

        fig = px.line(
            df,
            x="date",
            y="alive",
            color="species",
            labels={"alive": "Fish Alive", "date": "Date", "species": "Species"},
            title="Fish Population Over Time",
        )
        fig.update_layout(template="plotly_white", hovermode="x unified")
        return sui.HTML(fig.to_html(full_html=False, include_plotlyjs=False))
