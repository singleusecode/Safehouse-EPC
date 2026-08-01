import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from data_loader import debug_print, load_data
from constants import PALETTE
from charts import energy_chart, environment_chart, htc_chart
import html
from sklearn.linear_model import LinearRegression
import numpy as np
from htc_analysis import (
    compute_htc_regression,
    compute_rolling_htc,
    compute_htc_kpi_from_series,
    plot_htc_regression,
    plot_htc_timeseries
)
from anomaly_detection import run_anomaly_pipeline

# if st.button("Clear session"):
#     st.session_state.clear()
#     st.rerun()

period_map = {
    "7D": 7,
    "30D": 30,
    "3M": 90
}

# -------------------------------------------------
# COLUMN SCHEMA MAPPING (RAW vs DISPLAY)
# -------------------------------------------------
RAW = {
    "temp": "temperature",
    "out_temp": "outside_temp",
    "energy": "total_energy"
}

DISPLAY = {
    "temp": "Indoor Temperature (°C)",
    "out_temp": "Outdoor Temperature (°C)",
    "energy": "Total Energy (kWh)"
}

# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0
    
if "energy_mode" not in st.session_state:
    st.session_state.energy_mode = "Electricity"

if "env_mode" not in st.session_state:
    st.session_state.env_mode = "Indoor Temperature"

if "active_range" not in st.session_state:
    st.session_state.active_range = "30D"

if "max_date_anchor" not in st.session_state:
    st.session_state.max_date_anchor = None

if "start_input" not in st.session_state:
    st.session_state.start_input = None

if "end_input" not in st.session_state:
    st.session_state.end_input = None

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Safehouse EPC+",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# -------------------------------------------------
# CSS STYLES
# -------------------------------------------------
st.markdown("""
<style>

/* Layout */
.block-container { padding-top: 1rem; }

/* KPI cards */
.stMetric {
    background: white;
    padding: 14px;
    border-radius: 8px;
    border: 1px solid #e1e4e8;
    transition: all 0.3s ease;
}

/* Buttons */
div[data-testid="stButton"] button {
    height: 42px;
    font-weight: 600;
    border-radius: 8px;
    transition: all 0.25s ease;
}

/* Selected buttons (RED) */
div[data-testid="stButton"] button[kind="primary"] {
    background-color: #ff4b4b !important;
    color: white !important;
    border: none !important;
}

/* Hover animation */
div[data-testid="stButton"] button:hover {
    transform: translateY(-1px);
}

/* Unselected */
div[data-testid="stButton"] button[kind="secondary"] {
    background-color: #f5f5f5 !important;
    color: #333 !important;
}

/* Chart animation */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

.chart-container {
    animation: fadeIn 0.4s ease-in-out;
}

</style>
""", unsafe_allow_html=True)

refresh_api_data = st.sidebar.button(
    "🔄 Download Latest API Data",
    type="primary",
    help="Downloads fresh data from Octopus and Viper, updates the local CSV files, and refreshes the dashboard."
)

df_raw, df_display, df_hourly, df_hourly_display, \
df_e_raw, df_g_raw, anchor_ts, data_source = load_data(
    days=365,
    refresh_key=st.session_state.refresh_key,
    use_api=refresh_api_data,
)

# -----------------------------
# ENSURE DATETIME
# -----------------------------
def ensure_datetime(df):
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df.dropna(subset=["timestamp"])

df_raw = ensure_datetime(df_raw)
df_hourly = ensure_datetime(df_hourly)

# -----------------------------
# RUN ML + MERGE
# -----------------------------
@st.cache_data(ttl=3600)
def run_ml(df, refresh_key):
    return run_anomaly_pipeline(df, run_shap=False)

# if st.button("🔄 Refresh ML"):
#     st.session_state.refresh_key += 1

# df_ml = run_ml(df_raw, st.session_state.refresh_key)

# -----------------------------
# ANOMALY ANALYSIS
# -----------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def run_ml(df, refresh_key):
    return run_anomaly_pipeline(
        df,
        run_shap=False,
    )


run_ml_analysis = st.sidebar.checkbox(
    "Run anomaly analysis",
    value=False,
    help=(
        "Anomaly detection can take several seconds. "
        "Leave disabled for faster dashboard loading."
    ),
)

if run_ml_analysis:
    with st.spinner("Running anomaly analysis..."):
        df_ml = run_ml(
            df_raw,
            st.session_state.refresh_key,
        )

        df_ml = ensure_datetime(df_ml)

        required_ml_columns = [
            "timestamp",
            "global_anomaly_flag",
            "mold_risk",
            "co2_risk",
            "condensation_risk",
        ]

        missing_ml_columns = [
            column
            for column in required_ml_columns
            if column not in df_ml.columns
        ]

        if missing_ml_columns:
            st.error(
                "Anomaly analysis did not return the required columns: "
                + ", ".join(missing_ml_columns)
            )
            st.stop()

        df_final = df_raw.merge(
            df_ml[required_ml_columns],
            on="timestamp",
            how="left",
        )

else:
    df_final = df_raw.copy()

    df_final["global_anomaly_flag"] = "Not calculated"
    df_final["mold_risk"] = "Not calculated"
    df_final["co2_risk"] = "Not calculated"
    df_final["condensation_risk"] = "Not calculated"

df_final = ensure_datetime(df_final)
# -----------------------------
# DATE CONTROL SETUP
# -----------------------------
anchor_ts = df_raw["timestamp"].max()
st.session_state.max_date_anchor = anchor_ts

range_days_map = {
    "7D": 7,
    "30D": 30,
    "3M": 90
}

if st.session_state.start_input is None or st.session_state.end_input is None:
    selected_days = range_days_map.get(st.session_state.active_range, 30)

    st.session_state.start_input = (anchor_ts - timedelta(days=selected_days)).date()
    st.session_state.end_input = anchor_ts.date()


def cb_manual_date():
    st.session_state.active_range = None


def cb_date(days, label):
    new_start = st.session_state.max_date_anchor - timedelta(days=days)
    st.session_state.start_input = new_start.date()
    st.session_state.end_input = st.session_state.max_date_anchor.date()
    st.session_state.active_range = label


def cb_env(mode):
    st.session_state.env_mode = mode


def cb_energy(mode):
    st.session_state.energy_mode = mode

# -----------------------------
# FILTER DATA BY DATE SELECTORS
# -----------------------------
start_dt = pd.Timestamp(st.session_state.start_input, tz="UTC")
end_dt = pd.Timestamp(st.session_state.end_input, tz="UTC") + pd.Timedelta(days=1)

df_kpi = df_final[
    (df_final["timestamp"] >= start_dt) &
    (df_final["timestamp"] < end_dt)
].copy()

df_chart = df_hourly[
    (df_hourly["timestamp"] >= start_dt) &
    (df_hourly["timestamp"] < end_dt)
].copy()

df_kpi["delta_temp"] = df_kpi["temperature"] - df_kpi["outside_temp"]

df_kpi = compute_rolling_htc(
    df_kpi,
    "temperature",
    "outside_temp",
    "total_energy"
)

df_chart = compute_rolling_htc(
    df_chart,
    "temperature",
    "outside_temp",
    "total_energy"
)



# # -----------------------------
# # LOAD DATA
# # -----------------------------
# df_raw, df_display, df_hourly, df_hourly_display, df_e_raw, df_g_raw, anchor_ts = load_data(
#     days=365,
#     refresh_key=st.session_state.refresh_key
# )

# # -------------------------------------------------
# # ANOMALY ANALYTTICS
# # -------------------------------------------------
# @st.cache_data(ttl=3600)
# def run_ml(df, refresh_key):
#     return run_anomaly_pipeline(df, run_shap=False)

# if st.button("🔄 Refresh ML"):
#     st.session_state.refresh_key += 1

# df_ml = run_ml(df_raw, st.session_state.refresh_key)
# df_ml = ensure_datetime(df_ml)

# df_final = df_raw.merge(
#     df_ml[[
#         "timestamp",
#         "global_anomaly_flag",
#         "mold_risk",
#         "co2_risk",
#         "condensation_risk"
#     ]],
#     on="timestamp",
#     how="left"
# )

# # -----------------------------
# # DATETIME
# # -----------------------------
# def ensure_datetime(df):
#     df = df.copy()
#     df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
#     return df.dropna(subset=["timestamp"])

# df_raw = ensure_datetime(df_raw)
# df_hourly = ensure_datetime(df_hourly)

# # -----------------------------
# # DATE RANGE
# # -----------------------------
# anchor_ts = df_raw["timestamp"].max()

# start_dt = pd.Timestamp(st.session_state.start_input, tz="UTC")
# end_dt = pd.Timestamp(st.session_state.end_input, tz="UTC") + pd.Timedelta(days=1)

# # range_days = period_map[st.session_state.active_range]

# # anchor_ts = df_raw["timestamp"].max()

# # end_dt = anchor_ts.replace(minute=0, second=0, microsecond=0)
# # start_dt = end_dt - pd.Timedelta(days=range_days)

# df_kpi = df_final[
#     (df_final["timestamp"] >= start_dt) &
#     (df_final["timestamp"] <= end_dt)
# ]
# df_kpi = df_kpi.copy()
# df_kpi.loc[:, "delta_temp"] = df_kpi["temperature"] - df_kpi["outside_temp"]

# df_kpi["delta_temp"] = df_kpi["temperature"] - df_kpi["outside_temp"]
# df_kpi = compute_rolling_htc(df_kpi, "temperature", "outside_temp", "total_energy")

# df_chart = df_hourly[
#     (df_hourly["timestamp"] >= start_dt) &
#     (df_hourly["timestamp"] <= end_dt)
# ]

# # -------------------------------------------------
# # HTC CALCULATION
# # -------------------------------------------------

# df_chart = compute_rolling_htc(
#     df_chart,
#     "temperature",
#     "outside_temp",
#     "total_energy"
# )

# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------

# Set anchor (always update)
st.session_state.max_date_anchor = anchor_ts

# Initialise date inputs only once
if st.session_state.start_input is None:
    st.session_state.start_input = (anchor_ts - timedelta(days=30)).date()

if st.session_state.end_input is None:
    st.session_state.end_input = anchor_ts.date()

# # -------------------------------------------------
# # CALLBACKS
# # -------------------------------------------------
# def cb_env(mode):
#     st.session_state.env_mode = mode

# def cb_date(days, label):
#     new_start = st.session_state.max_date_anchor - timedelta(days=days)
#     st.session_state.start_input = new_start.date()
#     st.session_state.end_input = st.session_state.max_date_anchor.date()
#     st.session_state.active_range = label

# def cb_energy(mode):
#     st.session_state.energy_mode = mode

# def cb_manual_date():
#     st.session_state.active_range = None

# -------------------------------------------------
# HEADER
# -------------------------------------------------
h_left, h_right = st.columns([2,1.5])

with h_left:
    st.title("Safehouse EPC+")
    st.markdown("##### 38 Mark Street, Cardiff")
    st.markdown("EPC Grade: D")
    st.caption(f"{df_raw['timestamp'].min().date()} to {anchor_ts.date()}")

if data_source == "LIVE_API":
    st.success("Data source: Live API")
else:
    st.warning("Data source: CSV backup")

with h_right:
    d1, d2 = st.columns(2)
    with d1:
        st.date_input(
            "Start Date",
            key="start_input",
            on_change=cb_manual_date
    )

    with d2:
        st.date_input(
            "End Date",
            key="end_input",
            on_change=cb_manual_date
        )
    
    # with d1: st.date_input("Start Date", key="start_input")
    # with d2: st.date_input("End Date", key="end_input")

    b1, b2, b3 = st.columns(3)

    with b1:
        st.button(
            "7D",
            on_click=cb_date,
            args=(7, "7D"),
            type="primary" if st.session_state.active_range == "7D" else "secondary",
            use_container_width=True
        )

    with b2:
        st.button(
            "30D",
            on_click=cb_date,
            args=(30, "30D"),
            type="primary" if st.session_state.active_range == "30D" else "secondary",
            use_container_width=True
        )

    with b3:
        st.button(
            "3M",
            on_click=cb_date,
            args=(90, "3M"),
            type="primary" if st.session_state.active_range == "3M" else "secondary",
            use_container_width=True
        )
# -------------------------------------------------
# KPI CALCULATIONS
# -------------------------------------------------

htc_value = compute_htc_kpi_from_series(df_kpi)

# -------------------------------------------------
# KPI DISPLAY
# -------------------------------------------------
total_energy = df_kpi["total_energy"].sum()
avg_humidity = df_kpi["humidity"].mean() if "humidity" in df_kpi.columns else 0
avg_co2 = df_kpi["co2"].mean() if "co2" in df_kpi.columns else 0

st.write("---")

k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "HTC (W/K)",
    "N/A" if htc_value is None or htc_value < 0.1 else f"{htc_value:.1f}"
)
k2.metric("Total Energy Consumption (kWh)", f"{total_energy:.0f}")
k3.metric("Avg Humidity (%)", f"{avg_humidity:.1f}")
k4.metric("Avg CO₂ (ppm)", f"{avg_co2:.0f}")

st.write("---")

# st.markdown("### Heat Transfer Coefficient (HTC) Trend")

# col_l, col_c, col_r = st.columns([1, 6, 1])

# with col_c:
#     st.plotly_chart(
#         plot_htc_timeseries(df_chart),
#         use_container_width=True
#     )

# st.markdown("### Energy vs Temperature Difference (HTC)")

# # col_l, col_c, col_r = st.columns([1, 6, 1])
# result = compute_htc_regression(
#     df_kpi,
#     "temperature",
#     "outside_temp",
#     "total_energy"
# )

# col_l, col_c, col_r = st.columns([1, 6, 1])

# st.plotly_chart(
#     plot_htc_regression(result),
#     width="stretch",   # also fixes warning
#     key="htc_regression_main"
# )

# col1, col2 = st.columns([1,4])

# with col1:
#     st.metric("HTC (W/K)", f"{result['htc_w']:.0f}")
#     st.metric("R²", f"{result['r2']:.2f}")
#     st.caption(f"{result['n']} samples")

# with col2:
#     st.plotly_chart(
#         plot_htc_regression(result),
#         use_container_width=True
#     )


# -------------------------------------------------
# CHARTS
# -------------------------------------------------
env_map = {
    "Indoor Temperature": "temperature",
    "Indoor Humidity": "humidity",
    "CO2": "co2"
}

energy_map = {
    "Electricity": "consumption_electricity",
    "Gas": "consumption_gas"
}

col_l, col_r = st.columns(2)

# =================================================
# ENERGY CHART
# =================================================
with col_l:
    st.subheader(f"Energy: {st.session_state.energy_mode}")

    e1, e2 = st.columns(2)

    with e1:
        st.button(
            "Electricity",
            key="btn_electricity",
            on_click=cb_energy,
            args=("Electricity",),
            type="primary" if st.session_state.energy_mode == "Electricity" else "secondary",
            use_container_width=True
        )

    with e2:
        st.button(
            "Gas",
            key="btn_gas",
            on_click=cb_energy,
            args=("Gas",),
            type="primary" if st.session_state.energy_mode == "Gas" else "secondary",
            use_container_width=True
        )

    if not df_chart.empty:
        y_col = energy_map[st.session_state.energy_mode]
        color = "#3b82f6" if st.session_state.energy_mode == "Electricity" else "#ff4b4b"

        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(
            energy_chart(df_chart, y_col, color),
            use_container_width=True
        )
        st.markdown('</div>', unsafe_allow_html=True)

# =================================================
# ENVIRONMENT CHART
# =================================================
with col_r:
    st.subheader(f"Environment: {st.session_state.env_mode}")

    m1, m2, m3 = st.columns(3)

    with m1:
        st.button(
            "Temp",
            key="btn_temp",
            on_click=cb_env,
            args=("Indoor Temperature",),
            type="primary" if st.session_state.env_mode == "Indoor Temperature" else "secondary",
            use_container_width=True
        )

    with m2:
        st.button(
            "Humidity",
            key="btn_humidity",
            on_click=cb_env,
            args=("Indoor Humidity",),
            type="primary" if st.session_state.env_mode == "Indoor Humidity" else "secondary",
            use_container_width=True
        )
        
        
    with m3:
        st.button(
            "🫧 CO2",
            key="btn_co2",
            on_click=cb_env,
            args=("CO2",),
            type="primary" if st.session_state.env_mode == "CO2" else "secondary",
            use_container_width=True
        )

    if not df_chart.empty:
        
        y_col = env_map[st.session_state.env_mode]

        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(
            environment_chart(df_chart, y_col, PALETTE),
            use_container_width=True
        )
        st.markdown('</div>', unsafe_allow_html=True)

st.subheader("Insights & Recommendations")

summary_lines = []
recommendations = []

# period_label = st.session_state.active_range

if st.session_state.active_range is not None:
    period_label = st.session_state.active_range
else:
    period_label = f"{st.session_state.start_input} to {st.session_state.end_input}"


# =================================================
#HTC REGRESSION (FOR FIGURE / DEBUG)
# =================================================

# if st.checkbox("Show HTC Regression (Analysis)"):

#     result = compute_htc_regression(
#         df_kpi,
#         "temperature",
#         "outside_temp",
#         "total_energy"
#     )

#     if result is not None:

#         st.plotly_chart(
#             plot_htc_regression(result),
#             use_container_width=True
#         )

#         col1, col2, col3 = st.columns(3)
#         col1.metric("HTC (kWh/K)", f"{result['htc']:.3f}")
#         col2.metric("R²", f"{result['r2']:.2f}")
#         col3.metric("Observations", f"{result['n']}")

# # =================================================
# # HTC TIMESERIES
# # =================================================
# if st.checkbox("Show HTC Trend"):

#     df_htc_series = compute_rolling_htc(
#         df_kpi,
#         "temperature",
#         "outside_temp",
#         "total_energy"
#     )

#     fig = plot_htc_timeseries(df_htc_series)
#     st.plotly_chart(fig, use_container_width=True)
    
# -------------------------------------------------
# 🔍 INTELLIGENT ANOMALY EXPLANATION FUNCTION
# -------------------------------------------------
def explain_anomaly(row, df_reference):
    explanations = []

    energy = row.get("total_energy")
    temp = row.get("temperature")
    out_temp = row.get("outside_temp")
    humidity = row.get("humidity")
    co2 = row.get("co2")

    delta_t = None
    if pd.notna(temp) and pd.notna(out_temp):
        delta_t = temp - out_temp

    # ================================
    # Efficiency logic
    # ================================
    if delta_t is not None and pd.notna(energy):

        high_energy_threshold = df_reference["total_energy"].quantile(0.75)

        if delta_t < 3 and energy > high_energy_threshold:
            explanations.append("⚠️ High energy despite low ΔT → possible inefficiency")

        elif delta_t > 10:
            explanations.append("🔥 High heating demand due to large temperature difference")

    # ================================
    # Ventilation
    # ================================
    if pd.notna(co2) and co2 > 1000:
        explanations.append("🌬️ Poor ventilation (high CO₂)")

    # ================================
    # Moisture / mould
    # ================================
    if pd.notna(humidity) and humidity > 70:
        explanations.append("💧 High humidity → potential mould risk")

    # ================================
    # Fallback
    # ================================
    if not explanations:
        explanations.append("ℹ️ Unusual combined energy and environmental behaviour")

    return " | ".join(explanations)


# -------------------------------------------------
# SUMMARY + KPI INSIGHTS
# -------------------------------------------------
if not df_kpi.empty:

    total_energy = df_kpi["total_energy"].sum()
    avg_energy = df_kpi["total_energy"].mean()

    summary_lines.append(
        f"• Total energy consumption ({period_label}): {total_energy:.1f} kWh"
    )

    if avg_energy > df_kpi["total_energy"].quantile(0.75):
        summary_lines.append("• Energy usage is above expected levels.")
        recommendations.append("Investigate heating efficiency and insulation performance.")
    else:
        summary_lines.append("• ✅ Energy usage within expected range.")

    # ================================
    # MOLD RISK
    # ================================
    if "mold_risk" in df_kpi.columns:
        mold_ratio = (df_kpi["mold_risk"] == "HIGH").mean()
        summary_lines.append(f"• Mold risk present {mold_ratio*100:.1f}% of time")

        if mold_ratio > 0.2:
            recommendations.append("Improve ventilation and reduce indoor humidity.")
        elif mold_ratio > 0:
            recommendations.append("Monitor humidity levels to prevent mold growth.")

    # ================================
    # CO2
    # ================================
    if "co2" in df_kpi.columns:
        co2_ratio = (df_kpi["co2"] > 1000).mean()
        summary_lines.append(f"• Elevated CO₂ levels {co2_ratio*100:.1f}% of time")

        if co2_ratio > 0.2:
            recommendations.append("Increase ventilation or reduce occupancy.")

    # ================================
    # ANOMALY SUMMARY
    # ================================
    # anomaly_ratio = 0  # safe default

    # if "global_anomaly_flag" in df_kpi.columns:
    #     anomaly_ratio = (df_kpi["global_anomaly_flag"] == "Anomaly").mean()

    #     summary_lines.append(
    #     f"• Anomalies detected **{anomaly_ratio*100:.1f}% of time**"
    # )

    # if anomaly_ratio > 0.05:
    #     recommendations.append(
    #         "Investigate abnormal energy patterns linked to heating inefficiency or ventilation issues."
    #     )

# -------------------------------------------------
# INTELLIGENT RECOMMENDATIONS
# -------------------------------------------------
if not df_kpi.empty:

    # Inefficiency detection
    if "delta_temp" in df_kpi.columns:
        inefficient = df_kpi[
            (df_kpi["delta_temp"] < 5) &
            (df_kpi["total_energy"] > df_kpi["total_energy"].quantile(0.75))
        ]

        if not inefficient.empty:
            recommendations.append(
                "Reduce unnecessary heating during mild outdoor conditions."
            )

    # Condensation
    if "condensation_risk" in df_kpi.columns:
        cond_ratio = (df_kpi["condensation_risk"] == "HIGH").mean()
        if cond_ratio > 0.1:
            recommendations.append(
                "Improve insulation and ventilation to reduce condensation risk."
            )


# -------------------------------------------------
# SUMMARY BOX
# -------------------------------------------------
st.markdown(
    f"""
    <div style="
        background-color:#e0f2fe;
        padding:18px;
        border-radius:12px;
        border:1px solid #bae6fd;
        font-size:15px;
        line-height:1.6;
        color:#1f2937;
    ">
        <b style="color:#0369a1;font-size:16px;">Summary</b><br><br>
        {"<br>".join(html.escape(l) for l in summary_lines)}
    </div>
    """,
    unsafe_allow_html=True
)
# -------------------------------------------------
# TOP ANOMALY PERIODS
# -------------------------------------------------
# if not df_kpi.empty and "global_anomaly_flag" in df_kpi.columns:

#     df_anom = df_kpi[df_kpi["global_anomaly_flag"] == "Anomaly"].copy()

#     if not df_anom.empty:

#         # Create severity score
#         df_anom["delta_temp"] = df_anom["temperature"] - df_anom["outside_temp"]

#         df_anom["severity"] = (
#             df_anom["total_energy"] * df_anom["delta_temp"].abs()
#         )

#         # Remove weak signals
#         df_anom = df_anom[df_anom["delta_temp"].abs() > 2]

#         top5 = df_anom.sort_values("severity", ascending=False).head(5)

#         anomaly_lines = []

#         for _, row in top5.iterrows():

#             ts = row["timestamp"].strftime("%d %b %H:%M")

#             explanation = explain_anomaly(row, df_kpi)

#             line = f"""
#             • <b>{ts}</b> | Energy: {row['total_energy']:.2f} kWh  
#             ΔT: {row['delta_temp']:.1f}°C  
#             <br><span style='color:#9a3412;'>{explanation}</span>
#             """

#             anomaly_lines.append(line)

#         st.markdown(
#             f"""
#             <div style="
#                 background-color:#fff7ed;
#                 padding:18px;
#                 border-radius:12px;
#                 border:1px solid #fed7aa;
#                 font-size:15px;
#                 line-height:1.6;
#                 color:#7c2d12;
#             ">
#                 <b style="color:#ea580c;font-size:16px;">
#                 Top Anomaly Periods (Highest Impact)
#                 </b><br><br>
#                 {"<br>".join(anomaly_lines)}
#             </div>
#             """,
#             unsafe_allow_html=True
#         )


# -------------------------------------------------
# RECOMMENDATIONS
# -------------------------------------------------
st.markdown("### Recommended Actions")

if recommendations:
    for rec in sorted(set(recommendations)):
        st.markdown(f"- {rec}")
else:
    st.markdown("No immediate action required.")