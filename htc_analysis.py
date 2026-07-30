import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import plotly.graph_objects as go

# =================================================
# CONFIG
# =================================================
DELTA_T_THRESHOLD = 2      # Only use heating-relevant data
MIN_POINTS = 10           # Minimum points for regression

def plot_htc_regression(df, temp_col, out_temp_col, energy_col):
    df = df.copy()

    df = df.dropna(subset=[temp_col, out_temp_col, energy_col])
    df["delta_temp"] = df[temp_col] - df[out_temp_col]

    df = df[df["delta_temp"] > 2]

    if len(df) < 10:
        fig = go.Figure()
        fig.update_layout(title="Not enough data for HTC regression")
        return fig

    X = df["delta_temp"].values.reshape(-1, 1)
    y = df[energy_col].values

    model = LinearRegression()
    model.fit(X, y)

    slope = model.coef_[0]
    intercept = model.intercept_
    r2 = model.score(X, y)

    x_line = np.linspace(df["delta_temp"].min(), df["delta_temp"].max(), 100)
    y_line = slope * x_line + intercept

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["delta_temp"],
        y=y,
        mode="markers",
        name="Observed",
        marker=dict(size=6, opacity=0.6)
    ))

    fig.add_trace(go.Scatter(
        x=x_line,
        y=y_line,
        mode="lines",
        name="Regression",
        line=dict(width=3)
    ))

    fig.update_layout(
        title=f"Energy vs Temperature Difference (HTC) | R² = {r2:.2f}",
        xaxis_title="ΔT (Indoor − Outdoor) (°C)",
        yaxis_title="Energy (kWh)",
        template="plotly_white",
        height=420,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=1.05)
    )

    return fig





# =================================================
# 1. DATA PREPARATION
# =================================================
def prepare_data(df, temp_col, out_temp_col, energy_col):
    df = df.copy()

    # Drop missing values
    df = df.dropna(subset=[temp_col, out_temp_col, energy_col])

    # Compute temperature difference
    df["delta_temp"] = df[temp_col] - df[out_temp_col]

    return df


# =================================================
# 2. STATIC HTC REGRESSION (KPI / DISSERTATION)
# =================================================
def compute_htc_regression(df, temp_col, out_temp_col, energy_col):
    df = prepare_data(df, temp_col, out_temp_col, energy_col)

    # Focus on heating conditions
    df = df[df["delta_temp"] > DELTA_T_THRESHOLD]

    if len(df) < 20:
        return {
            "htc_kwh": 0,
            "htc_w": 0,
            "intercept": 0,
            "r2": 0,
            "n": len(df),
            "df_used": df,
            "message": "Insufficient data"
        }

    X = df["delta_temp"].values.reshape(-1, 1)
    y = df[energy_col].values

    model = LinearRegression()
    model.fit(X, y)

    htc_kwh = model.coef_[0]
    htc_w = htc_kwh * 1000  # convert to W/K

    return {
        "htc_kwh": htc_kwh,
        "htc_w": htc_w,
        "intercept": model.intercept_,
        "r2": model.score(X, y),
        "n": len(df),
        "df_used": df
    }


# =================================================
# 3. ROLLING HTC (TIME-VARYING)
# =================================================
def compute_rolling_htc(df, temp_col, out_temp_col, energy_col, window=24):
    """
    Computes time-varying HTC using rolling linear regression.

    Parameters:
    - df: dataframe with timestamped data
    - temp_col: indoor temperature column
    - out_temp_col: outdoor temperature column
    - energy_col: energy consumption column (kWh)
    - window: rolling window size (default = 24 hours)

    Returns:
    - df with HTC_WK and HTC_R2 columns
    """

    from sklearn.linear_model import LinearRegression
    import numpy as np

    df = df.copy()

    htc_vals = []
    r2_vals = []

    for i in range(len(df)):

        # Not enough data for rolling window
        if i < window:
            htc_vals.append(None)
            r2_vals.append(None)
            continue

        # -----------------------------------
        # 1. SELECT WINDOW
        # -----------------------------------
        window_df = df.iloc[i - window:i].copy()

        # -----------------------------------
        # 2. CLEAN DATA (CRITICAL)
        # -----------------------------------
        window_df = window_df.dropna(subset=[temp_col, out_temp_col, energy_col])

        if len(window_df) < 10:
            htc_vals.append(None)
            r2_vals.append(None)
            continue

        # -----------------------------------
        # 3. COMPUTE ΔT
        # -----------------------------------
        window_df["delta_temp"] = (
            window_df[temp_col] - window_df[out_temp_col]
        )

        # -----------------------------------
        # 4. HEATING FILTER (PHYSICS-BASED)
        # -----------------------------------
        window_df = window_df[window_df["delta_temp"] > 5]

        # Remove low-energy noise (appliances / standby)
        if not window_df.empty:
            energy_threshold = window_df[energy_col].median()
            window_df = window_df[
                window_df[energy_col] > energy_threshold
            ]

        if len(window_df) < 10:
            htc_vals.append(None)
            r2_vals.append(None)
            continue

        # -----------------------------------
        # 5. REGRESSION
        # -----------------------------------
        X = window_df["delta_temp"].values.reshape(-1, 1)
        y = window_df[energy_col].values

        model = LinearRegression()
        model.fit(X, y)

        # HTC in W/K
        htc = model.coef_[0] * 1000
        r2 = model.score(X, y)

        # -----------------------------------
        # 6. RELIABILITY FILTER
        # -----------------------------------
        if r2 < 0.2 or htc <= 0:
            htc_vals.append(None)
            r2_vals.append(r2)
        else:
            htc_vals.append(htc)
            r2_vals.append(r2)

    # -----------------------------------
    # 7. STORE RESULTS
    # -----------------------------------
    df["HTC_WK"] = htc_vals
    df["HTC_R2"] = r2_vals

    return df


# =================================================
# 4. KPI FROM ROLLING HTC
# =================================================
def compute_htc_kpi_from_series(df):
    htc_series = df["HTC_WK"].dropna()

    if htc_series.empty:
        return 0

    return htc_series.median()  # more robust than mean


# =================================================
# 5. REGRESSION SCATTER PLOT (DISSERTATION)
# =================================================
def plot_htc_regression(result, energy_col="total_energy"):
    df = result["df_used"]

    fig = go.Figure()

    # Scatter
    fig.add_trace(go.Scatter(
        x=df["delta_temp"],
        y=df[energy_col],
        mode="markers",
        name="Observed",
        marker=dict(size=5, opacity=0.5)
    ))

    # Line
    x_line = np.linspace(df["delta_temp"].min(), df["delta_temp"].max(), 100)
    y_line = result["htc_kwh"] * x_line + result["intercept"]

    fig.add_trace(go.Scatter(
        x=x_line,
        y=y_line,
        mode="lines",
        name="Regression"
    ))

    fig.update_layout(
        title=f"HTC Regression (R² = {result['r2']:.2f})",
        xaxis_title="ΔT (°C)",
        yaxis_title="Energy (kWh)",
        template="plotly_white"
    )

    return fig


# =================================================
# 6. HTC TIME SERIES PLOT
# =================================================
def plot_htc_timeseries(df, timestamp_col="timestamp"):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df[timestamp_col],
        y=df["HTC_WK"],
        mode="lines",
        name="HTC (W/K)"
    ))

    fig.update_layout(
        title="HTC Over Time (Rolling Regression)",
        xaxis_title="Time",
        yaxis_title="HTC (W/K)",
        template="plotly_white"
    )

    return fig


# =================================================
# 7. FILTER RELIABLE HTC (OPTIONAL)
# =================================================
def filter_reliable_htc(df, r2_threshold=0.2):
    return df[df["HTC_R2"] > r2_threshold]