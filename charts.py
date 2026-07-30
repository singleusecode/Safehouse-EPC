import plotly.express as px
import plotly.graph_objects as go

# -------------------------------------------------
# LABEL MAPPING (GLOBAL CONFIG)
# -------------------------------------------------
LABEL_MAP = {
    "consumption_gas": "Gas Consumption (kWh)",
    "consumption_electricity": "Electricity Consumption (kWh)"
}

# -------------------------------------------------
# SHARED STYLING FUNCTION
# -------------------------------------------------
def apply_clean_style(fig, y_title):

    fig.update_layout(
        plot_bgcolor="white",
        margin=dict(l=40, r=20, t=40, b=40),

        # KPI-style subtle axes (no heavy box)
        xaxis=dict(
            title="Time",
            showline=True,
            linewidth=1,
            linecolor="rgba(0,0,0,0.4)",
            mirror=False,
            tickangle=-45,
            tickformat="%b %d\n%H:%M"
        ),
        yaxis=dict(
            title=y_title,
            showline=True,
            linewidth=1,
            linecolor="rgba(0,0,0,0.4)",
            mirror=False,
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(0,0,0,0.1)"
        ),

        hovermode="x unified"
    )

    return fig


# -------------------------------------------------
# ENERGY BAR CHART
# -------------------------------------------------
# def energy_chart(df, y_col, color):

#     display_name = LABEL_MAP.get(y_col, y_col)

#     fig = px.bar(
#         df,
#         x="timestamp",
#         y=y_col,
#         labels={y_col: display_name, "timestamp": "Time"},
#         color_discrete_sequence=[color],
#         height=400
#     )

#     fig.update_layout(bargap=0.2)

#     # baseline
#     baseline = df[y_col].mean()

#     fig.add_trace(go.Scatter(
#         x=df["timestamp"],
#         y=[baseline] * len(df),
#         mode="lines",
#         name="Baseline",
#         line=dict(color=color, dash="dash", width=2)
#     ))

#     # annotation uses display name too
#     fig.add_annotation(
#         x=df["timestamp"].iloc[-1],
#         y=baseline,
#         text=f"Avg {display_name}: {baseline:.2f}",
#         showarrow=False,
#         xanchor="left"
#     )

#     fig.update_traces(
#         hovertemplate=f"%{{x}}<br>{display_name}: %{{y:.2f}}<extra></extra>"
#     )

#     fig = apply_clean_style(fig, display_name)
    
#     fig.update_xaxes(
#         range=[
#             df["timestamp"].min(),
#             df["timestamp"].max()
#         ]
#     )
    
#     return fig
# -------------------------------------------------
# ENERGY BAR CHART (FINAL VERSION)
# -------------------------------------------------
def energy_chart(df, y_col, color):

    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go

    display_name = LABEL_MAP.get(y_col, y_col)

    # Handle empty data safely
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available")
        return fig

    # -----------------------------
    # MAIN BAR CHART
    # -----------------------------
    fig = px.bar(
        df,
        x="timestamp",
        y=y_col,
        labels={y_col: display_name, "timestamp": "Time"},
        color_discrete_sequence=[color],
        height=400
    )

    # -----------------------------
    # BASELINE
    # -----------------------------
    baseline = df[y_col].mean()

    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=[baseline] * len(df),
        mode="lines",
        name="Baseline",
        line=dict(color=color, dash="dash", width=2)
    ))

    fig.add_annotation(
        x=df["timestamp"].iloc[-1],
        y=baseline,
        text=f"Avg {display_name}: {baseline:.2f}",
        showarrow=False,
        xanchor="left"
    )

    # -----------------------------
    # HOVER STYLE
    # -----------------------------
    fig.update_traces(
        hovertemplate=f"%{{x}}<br>{display_name}: %{{y:.2f}}<extra></extra>"
    )

    # -----------------------------
    # APPLY YOUR EXISTING STYLE
    # -----------------------------
    fig = apply_clean_style(fig, display_name)

    # -----------------------------
    # 🔥 CRITICAL FIX: REMOVE ALL PADDING
    # -----------------------------
    fig.update_layout(
        bargap=0.2,
        margin=dict(l=10, r=0, t=40, b=10),
        xaxis=dict(
            range=[
                df["timestamp"].min(),
                df["timestamp"].max()
            ],
            constrain="domain"
        )
    )

    return fig

# -------------------------------------------------
# ENVIRONMENT LINE CHART
# -------------------------------------------------
def environment_chart(df, metric, palette):

    plot_cols = [metric]

    if metric == "Indoor Temperature":
        plot_cols.append("Temperature Outside")

    if metric == "Indoor Humidity":
        plot_cols.append("Humidity Outside")

    fig = px.line(
        df,
        x="timestamp",
        y=plot_cols,
        height=400
    )

    # apply consistent colors
    for trace in fig.data:
        if trace.name in palette:
            trace.line.color = palette[trace.name]

    # baseline
    baseline = df[metric].mean()

    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=[baseline] * len(df),
        mode="lines",
        name="Baseline",
        line=dict(
            color=palette.get(metric),
            dash="dash",
            width=2
        )
    ))

    # baseline annotation
    fig.add_annotation(
        x=df["timestamp"].iloc[-1],
        y=baseline,
        text=f"Avg: {baseline:.1f}",
        showarrow=False,
        xanchor="left"
    )

    # improved hover
    fig.update_layout(hovermode="x unified")

    # apply shared styling
    fig = apply_clean_style(fig, metric)

    return fig

def htc_chart(df):

    fig = px.line(
        df,
        x="timestamp",
        y="HTC",
    )

    fig.update_traces(
        line=dict(width=3, color="#2563eb")  # blue
    )

    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis_title=None,
        yaxis_title="HTC (kWh/K)",
        font=dict(size=13),

        # Clean grid
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#e5e7eb"),
    )

    return fig