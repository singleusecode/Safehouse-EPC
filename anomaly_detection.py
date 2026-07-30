import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


def _first_existing_col(df, possible_cols):
    for col in possible_cols:
        if col in df.columns:
            return col
    return None


def run_anomaly_pipeline(df, run_shap=False):
    df = df.copy()

    # -----------------------------
    # Column detection
    # -----------------------------
    timestamp_col = _first_existing_col(df, ["timestamp", "Timestamp"])

    energy_col = _first_existing_col(df, [
        "total_energy",
        "Total Energy (kWh)",
    ])

    temp_col = _first_existing_col(df, [
        "temperature",
        "Indoor Temperature (°C)",
    ])

    humidity_col = _first_existing_col(df, [
        "humidity",
        "Indoor Humidity (%)",
    ])

    co2_col = _first_existing_col(df, [
        "co2",
        "CO2 (ppm)",
    ])

    feature_cols = [
        col for col in [energy_col, temp_col, humidity_col, co2_col]
        if col is not None
    ]

    # -----------------------------
    # Default output columns
    # -----------------------------
    df["global_anomaly_flag"] = 0
    df["anomaly_score"] = np.nan
    df["mold_risk"] = 0
    df["co2_risk"] = 0
    df["condensation_risk"] = 0
    df["anomaly_explanation"] = "Normal pattern"

    # -----------------------------
    # Rule-based risks
    # -----------------------------
    if humidity_col:
        humidity = pd.to_numeric(df[humidity_col], errors="coerce")
        df["mold_risk"] = (humidity > 70).fillna(False).astype(int)

    if co2_col:
        co2 = pd.to_numeric(df[co2_col], errors="coerce")
        df["co2_risk"] = (co2 > 1000).fillna(False).astype(int)

    if temp_col and humidity_col:
        temp = pd.to_numeric(df[temp_col], errors="coerce")
        humidity = pd.to_numeric(df[humidity_col], errors="coerce")
        df["condensation_risk"] = (
            (humidity > 75) & (temp < 18)
        ).fillna(False).astype(int)

    # -----------------------------
    # If not enough ML columns
    # -----------------------------
    if len(feature_cols) < 2:
        df["anomaly_explanation"] = "Not enough columns for anomaly detection."
        return df

    model_data = df[feature_cols].apply(pd.to_numeric, errors="coerce")
    valid_data = model_data.dropna()

    if len(valid_data) < 20:
        df["anomaly_explanation"] = "Not enough valid rows for anomaly detection."
        return df

    # -----------------------------
    # Isolation Forest
    # -----------------------------
    scaler = StandardScaler()
    X = scaler.fit_transform(valid_data)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.02,
        random_state=42,
    )

    predictions = model.fit_predict(X)
    scores = model.decision_function(X)

    anomaly_flags = (predictions == -1).astype(int)

    df.loc[valid_data.index, "global_anomaly_flag"] = anomaly_flags
    df.loc[valid_data.index, "anomaly_score"] = scores

    # -----------------------------
    # Simple explanation
    # -----------------------------
    means = model_data.mean(numeric_only=True)
    stds = model_data.std(numeric_only=True).replace(0, np.nan)

    def explain_row(row):
        if row["global_anomaly_flag"] != 1:
            return "Normal pattern"

        reasons = []

        for col in feature_cols:
            value = pd.to_numeric(row[col], errors="coerce")
            mean = means.get(col)
            std = stds.get(col)

            if pd.isna(value) or pd.isna(mean) or pd.isna(std):
                continue

            z = (value - mean) / std

            if z > 2:
                reasons.append(f"High {col}")
            elif z < -2:
                reasons.append(f"Low {col}")

        if row["mold_risk"] == 1:
            reasons.append("High humidity mold risk")

        if row["co2_risk"] == 1:
            reasons.append("High CO2 risk")

        if row["condensation_risk"] == 1:
            reasons.append("Condensation risk")

        return ", ".join(reasons) if reasons else "Unusual combined energy/environment pattern"

    df["anomaly_explanation"] = df.apply(explain_row, axis=1)

    # Keep timestamp if available
    if timestamp_col and timestamp_col != "timestamp":
        df["timestamp"] = df[timestamp_col]

    return df