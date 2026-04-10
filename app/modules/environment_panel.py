"""Environment panel — temperature, flow, turbidity subplots."""

from shiny import module, render, ui


@module.ui
def environment_ui():
    return ui.card(
        ui.card_header("Environmental Conditions"),
        ui.output_ui("environment_plot"),
    )


@module.server
def environment_server(input, output, session, results_rv):
    @output
    @render.ui
    def environment_plot():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")
        df = results["environment"]
        if df.empty:
            return ui.p("No environment data available.")

        from plotly.subplots import make_subplots
        import plotly.graph_objects as go
        from shiny import ui as sui

        reaches = df["reach"].unique()
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            subplot_titles=("Temperature (°C)", "Flow (m³/s)", "Turbidity (NTU)"),
            vertical_spacing=0.08,
        )
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
        for i, rname in enumerate(reaches):
            rd = df[df["reach"] == rname]
            color = colors[i % len(colors)]
            fig.add_trace(
                go.Scatter(
                    x=rd["date"],
                    y=rd["temperature"],
                    name=rname,
                    legendgroup=rname,
                    line=dict(color=color),
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=rd["date"],
                    y=rd["flow"],
                    name=rname,
                    legendgroup=rname,
                    showlegend=False,
                    line=dict(color=color),
                ),
                row=2,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=rd["date"],
                    y=rd["turbidity"],
                    name=rname,
                    legendgroup=rname,
                    showlegend=False,
                    line=dict(color=color),
                ),
                row=3,
                col=1,
            )
        fig.update_layout(template="plotly_white", height=600)
        return sui.HTML(fig.to_html(full_html=False, include_plotlyjs=False))
