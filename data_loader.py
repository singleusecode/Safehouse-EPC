import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta, timezone
import os
import time
from pathlib import Path
DEBUG = True
def debug_print(*args):
    if DEBUG:
        print(*args)

DATA_DIR = Path("csv_data")
DATA_DIR.mkdir(exist_ok=True)

def load_backup_data():
    df_raw = pd.read_csv(DATA_DIR / "aligned_30min.csv")
    df_display = pd.read_csv(DATA_DIR / "aligned_30min_display.csv")
    df_hourly = pd.read_csv(DATA_DIR / "aligned_hourly.csv")
    df_hourly_display = pd.read_csv(DATA_DIR / "aligned_hourly_display.csv")

    for df in [df_raw, df_display, df_hourly, df_hourly_display]:
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    return (
        df_raw,
        df_display,
        df_hourly,
        df_hourly_display,
        pd.DataFrame(),
        pd.DataFrame(),
        df_raw["timestamp"].max(),
        "BACKUP_CSV"
    )

def load_local_data():
    """
    Load previously saved processed CSV files only.

    This function never contacts Octopus, Viper or any other API.
    """
    required_files = [
        DATA_DIR / "aligned_30min.csv",
        DATA_DIR / "aligned_30min_display.csv",
        DATA_DIR / "aligned_hourly.csv",
        DATA_DIR / "aligned_hourly_display.csv",
    ]

    missing_files = [
        path.name
        for path in required_files
        if not path.exists()
    ]

    if missing_files:
        raise FileNotFoundError(
            "Missing local dashboard CSV files: "
            + ", ".join(missing_files)
        )

    return load_backup_data()


# -------------------------------------------------
# STREAMLIT SUPPORT
# -------------------------------------------------
try:
    import streamlit as st

    def cache_decorator(ttl=3600):
        return st.cache_data(ttl=ttl)

    def get_secret(key):
        try:
            return st.secrets[key]
        except Exception:
            return os.getenv(key)

except Exception:
    def cache_decorator(ttl=3600):
        def wrapper(func):
            return func
        return wrapper

    def get_secret(key):
        return os.getenv(key)


# -------------------------------------------------
# OCTOPUS DOWNLOAD
# -------------------------------------------------
def download_octopus(resource, mpxn, serial, start_date, end_date):

    endpoint = "electricity-meter-points" if resource == "electricity" else "gas-meter-points"

    base_url = f"https://api.octopus.energy/v1/{endpoint}/{mpxn}/meters/{serial}/consumption/"

    params = {
        "period_from": start_date,
        "period_to": end_date,
        "page_size": 25000,
        "order_by": "period"
    }

    url = base_url
    all_data = []

    while url:
        response = requests.get(
            url,
            auth=HTTPBasicAuth(get_secret("OCTOPUS_API_KEY"), ''),
            params=params if url == base_url else None
        )

        response.raise_for_status()
        data = response.json()

        all_data.extend(data.get("results", []))
        url = data.get("next")

    df = pd.DataFrame(all_data)
    df["timestamp"] = pd.to_datetime(df["interval_start"], utc=True)

    df = df.rename(columns={"consumption": f"consumption_{resource}"})

    return df[["timestamp", f"consumption_{resource}"]].sort_values("timestamp")


# -------------------------------------------------
# SENSOR DATA DOWNLOAD
# -------------------------------------------------
def download_viper_sensor_data(
    days=365,
    max_retries=3,
    retry_delay=2.0,
):
    """
    Download Viper sensor data with retries.

    The Viper API may occasionally return HTTP 200 but contain
    status='400' and api_data=null. Those responses are retried.
    """
    url = get_secret("SENSOR_API_URL")

    params = {
        "key": get_secret("SENSOR_API_KEY"),
        "method": "3001",
        "eui": get_secret("SENSOR_EUI"),
        "parameters": "temperature,humidity,co2",
        "sensorDescription": "Air Quality CO2",
        "technology_type": "lora",
        "token": get_secret("SENSOR_TOKEN"),
        "days": str(days),
    }

    last_error = "Unknown sensor API error"

    for attempt in range(1, max_retries + 1):
        try:
            debug_print(
                f"\n📡 SENSOR API REQUEST "
                f"(attempt {attempt}/{max_retries})"
            )

            debug_print(
                "REQUEST:",
                {
                    "parameters": params["parameters"],
                    "sensorDescription": params["sensorDescription"],
                    "technology_type": params["technology_type"],
                    "days": params["days"],
                },
            )

            response = requests.get(
                url,
                params=params,
                timeout=60,
            )

            debug_print("HTTP STATUS:", response.status_code)
            response.raise_for_status()

            data = response.json()

            api_status = str(data.get("status", ""))
            api_error = data.get("error")
            payload = data.get("api_data")

            if (
                api_status == "200"
                and isinstance(payload, list)
                and payload
            ):
                df = pd.DataFrame(payload)

                if "timestamp" not in df.columns:
                    raise ValueError(
                        "Sensor response has no timestamp column"
                    )

                df["timestamp"] = pd.to_datetime(
                    df["timestamp"],
                    utc=True,
                    errors="coerce",
                )

                df = df.dropna(subset=["timestamp"])

                if df.empty:
                    raise ValueError(
                        "Sensor response has no valid timestamps"
                    )

                return df.sort_values("timestamp")

            last_error = (
                f"Viper status={api_status}; "
                f"error={api_error}; "
                f"api_data type={type(payload).__name__}"
            )

            debug_print(
                "⚠ Invalid sensor response:",
                last_error,
            )

        except requests.exceptions.Timeout:
            last_error = "Sensor request timed out"

        except requests.exceptions.RequestException as exc:
            last_error = f"Sensor request failed: {exc}"

        except ValueError as exc:
            last_error = str(exc)

        if attempt < max_retries:
            delay = retry_delay * attempt
            debug_print(
                f"Retrying sensor request in {delay:.1f}s..."
            )
            time.sleep(delay)

    raise RuntimeError(
        f"Sensor API failed after {max_retries} attempts: "
        f"{last_error}"
    )


# -------------------------------------------------
# HOURLY AGGREGATION
# -------------------------------------------------
def create_hourly_dataset(df_combined):

    df = df_combined.copy().set_index("timestamp")

    df_energy = df[["consumption_electricity", "consumption_gas", "total_energy"]].resample("1h").sum()
    df_sensor = df[["outside_humidity","co2","temperature","outside_temp","humidity","outside_pressure"]].resample("1h").mean()

    return pd.concat([df_energy, df_sensor], axis=1).reset_index()


# -------------------------------------------------
# CORE PIPELINE
# -------------------------------------------------
def build_dataset(days=365, save_csv=True):

    now = datetime.now(timezone.utc)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=365)

    start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    energy_api_failed = False
    sensor_api_failed = False

    df_elec = pd.DataFrame()
    df_gas = pd.DataFrame()
    df_sensor = pd.DataFrame()
    
    try:
        df_elec = download_octopus(
            "electricity",
            get_secret("MPAN"),
            get_secret("ELEC_SERIAL"),
            start_str,
            end_str,
        )

        df_gas = download_octopus(
            "gas",
            get_secret("MPRN"),
            get_secret("GAS_SERIAL"),
            start_str,
            end_str,
        )

    except Exception as exc:
        energy_api_failed = True
        debug_print("⚠ Octopus API failed:", exc)

    # df_sensor = pd.DataFrame()
    # try:
    #     df_sensor = download_viper_sensor_data(days)
    #     df_sensor = df_sensor[
    #         (df_sensor["timestamp"] >= start) &
    #         (df_sensor["timestamp"] < end)
    #     ]
    # except Exception as e:
    #     debug_print("⚠ Sensor API failed:", e)
    #     api_failed = True

    try:
        df_sensor = download_viper_sensor_data(
            days=days,
            max_retries=3,
            retry_delay=2.0,
        )

        df_sensor = df_sensor[
            (df_sensor["timestamp"] >= start)
            & (df_sensor["timestamp"] < end)
        ]

    except Exception as exc:
        sensor_api_failed = True
        debug_print("⚠ Sensor API failed:", exc)

        raw_sensor_path = DATA_DIR / "raw_sensor.csv"

        if raw_sensor_path.exists():
            debug_print(
                "Using previously saved local sensor data."
            )

            df_sensor = pd.read_csv(raw_sensor_path)

            df_sensor["timestamp"] = pd.to_datetime(
                df_sensor["timestamp"],
                utc=True,
                errors="coerce",
            )

            df_sensor = df_sensor.dropna(
                subset=["timestamp"]
            )

            df_sensor = df_sensor[
                (df_sensor["timestamp"] >= start)
                & (df_sensor["timestamp"] < end)
            ]

        else:
            debug_print(
                "No local raw_sensor.csv is available."
            )
    
    
    # -------------------------------------------------
    # SENSOR DATA SUMMARY
    # -------------------------------------------------
    debug_print("\n📊 SENSOR DATA SUMMARY")
    debug_print("Rows:", len(df_sensor))
    debug_print("Columns:", list(df_sensor.columns))

    if not df_sensor.empty:
        debug_print("\nHEAD:")
        debug_print(df_sensor.head())
        debug_print(df_sensor.tail())
        debug_print("\nDATE RANGE:")
        debug_print("Start:", df_sensor["timestamp"].min())
        debug_print("End:", df_sensor["timestamp"].max())
    else:
        debug_print("⚠ Sensor dataset is EMPTY")
    
    
    
    
    # if api_failed:
    #     debug_print("⚠ API failed. Loading processed CSV backup instead.")
    #     return load_backup_data()

    if energy_api_failed:
        debug_print(
            "⚠ Energy API failed. "
            "Loading processed CSV backup instead."
        )
        return load_backup_data()

    if df_sensor.empty:
        debug_print(
            "⚠ Sensor data unavailable. "
            "Loading processed CSV backup instead."
        )
        return load_backup_data()
    
    
    if save_csv:
        df_elec.to_csv(DATA_DIR / "raw_electricity.csv", index=False)
        df_gas.to_csv(DATA_DIR / "raw_gas.csv", index=False)
        df_sensor.to_csv(DATA_DIR / "raw_sensor.csv", index=False)

    # SENSOR COVERAGE
    # -------------------------------------------------
    # SENSOR COVERAGE CHECK
    # -------------------------------------------------
    if not df_sensor.empty:

        actual_start = df_sensor["timestamp"].min()
        expected_start = start

        gap_days = (actual_start - expected_start).days

        if gap_days > 1:
            debug_print(f"⚠ Missing first {gap_days} days")

        expected_points = len(pd.date_range(start=start, end=end, freq="30min", inclusive="left"))
        actual_points = len(df_sensor)

        coverage = actual_points / expected_points

        debug_print(f"📊 Sensor coverage: {coverage:.2%}")

    else:
        debug_print("⚠ No sensor data available")

    # ENERGY ALIGNMENT
    common_end = min(df_elec["timestamp"].max(), df_gas["timestamp"].max())
    df_elec = df_elec[df_elec["timestamp"] <= common_end]
    df_gas = df_gas[df_gas["timestamp"] <= common_end]

    # -------------------------------------------------
    # ENERGY DATA SUMMARY
    # -------------------------------------------------
    debug_print("\n⚡ ENERGY DATA SUMMARY")

    debug_print("Electricity rows:", len(df_elec))
    debug_print("Gas rows:", len(df_gas))

    debug_print("Electricity range:", df_elec["timestamp"].min(), "→", df_elec["timestamp"].max())
    debug_print("Gas range:", df_gas["timestamp"].min(), "→", df_gas["timestamp"].max())
    
    
    # MASTER CLOCK
    full_range = pd.date_range(start=start, end=end, freq="30min", tz="UTC", inclusive="left")
    df_master = pd.DataFrame({"timestamp": full_range})

    df_elec = df_elec.set_index("timestamp").resample("30min").sum().reset_index()
    df_gas = df_gas.set_index("timestamp").resample("30min").sum().reset_index()

    df_master = df_master.merge(df_elec, on="timestamp", how="left").fillna(0)
    df_master = df_master.merge(df_gas, on="timestamp", how="left").fillna(0)

    # SENSOR CLEAN
    # df_sensor = df_sensor.rename(columns={
    # "temperature": "Indoor Temperature",
    # "humidity": "Indoor Humidity",
    # "co2": "CO2",
    # "outside_temp": "Outdoor Temperature",
    # "outside_humidity": "Outdoor Humidity",
    # "outside_pressure": "Outdoor Pressure"
    # })

    # sensor_cols = ["outside_humidity","co2","temperature","outside_temp","humidity","outside_pressure"]
    sensor_cols = ["temperature", "humidity", "co2"]

    optional_cols = ["outside_temp", "outside_humidity", "outside_pressure"]

    for col in optional_cols:
        if col in df_sensor.columns:
            sensor_cols.append(col)
        
    # WINDOW ALIGNMENT
    aligned_rows = []

    for t in df_master["timestamp"]:
        df_window = df_sensor[
            (df_sensor["timestamp"] >= t - pd.Timedelta("30min")) &
            (df_sensor["timestamp"] <= t + pd.Timedelta("30min"))
        ]

        row = {"timestamp": t}

        for col in sensor_cols:
            row[col] = df_window[col].mean() if not df_window.empty else None

        aligned_rows.append(row)

    df_sensor_aligned = pd.DataFrame(aligned_rows)

    df_combined = df_master.merge(df_sensor_aligned, on="timestamp", how="left")

    # TOTAL ENERGY
    df_combined["total_energy"] = (
        df_combined["consumption_electricity"] +
        df_combined["consumption_gas"]
    )

    # DISPLAY
    df_display = df_combined.rename(columns={    
        # "timestamp": "Timestamp",
        "consumption_electricity": "Electricity Consumption (kWh)",
        "consumption_gas": "Gas Consumption (kWh)",
        "total_energy": "Total Energy (kWh)",
        "temperature": "Indoor Temperature (°C)",
        "humidity": "Indoor Humidity (%)",
        "outside_temp": "Outdoor Temperature (°C)",
        "co2": "CO2 (ppm)",
        "outside_humidity": "Outdoor Humidity (%)",
        "outside_pressure": "Outdoor Pressure (hPa)"
    })

    # HOURLY
    df_hourly = create_hourly_dataset(df_combined)

    df_hourly_display = df_hourly.rename(columns={
        # "timestamp": "Timestamp",
        "consumption_electricity": "Electricity Consumption (kWh)",
        "consumption_gas": "Gas Consumption (kWh)",
        "total_energy": "Total Energy (kWh)",
        "temperature": "Indoor Temperature (°C)",
        "humidity": "Indoor Humidity (%)",
        "outside_temp": "Outdoor Temperature (°C)",
        "co2": "CO2 (ppm)",
        "outside_humidity": "Outdoor Humidity (%)",
        "outside_pressure": "Outdoor Pressure (hPa)"
    })

    if save_csv:
        df_combined.to_csv(DATA_DIR / "aligned_30min.csv", index=False, encoding="utf-8-sig")
        df_display.to_csv(DATA_DIR / "aligned_30min_display.csv", index=False, encoding="utf-8-sig")
        df_hourly.to_csv(DATA_DIR / "aligned_hourly.csv", index=False, encoding="utf-8-sig")
        df_hourly_display.to_csv(DATA_DIR / "aligned_hourly_display.csv", index=False, encoding="utf-8-sig")

    if save_csv:
        print("💾 Saving CSVs to:", DATA_DIR.resolve())
        
    # -------------------------------------------------
    # FINAL DATASET SUMMARY
    # -------------------------------------------------
    debug_print("\n📊 FINAL DATASET")

    debug_print("Rows:", len(df_combined))
    debug_print("Columns:", list(df_combined.columns))

    debug_print("Time range:",
                df_combined["timestamp"].min(),
                "→",
                df_combined["timestamp"].max())

    debug_print("Total energy:", df_combined["total_energy"].sum())
    if sensor_api_failed:
        source_label = "LIVE_ENERGY_LOCAL_SENSOR"
    else:
        source_label = "LIVE_API"

    return (
        df_combined,
        df_display,
        df_hourly,
        df_hourly_display,
        df_elec,
        df_gas,
        end,
        source_label,
)
    # return df_combined, df_display, df_hourly_display, df_elec, df_gas, end
    return (
    df_combined,
    df_display,
    df_hourly,
    df_hourly_display,
    df_elec,
    df_gas,
    end,
    source_label,
)
def load_data(
    days=365,
    refresh_key=0,
    use_api=False,
):
    """
    Load dashboard data without automatically contacting external APIs.

    Parameters
    ----------
    days:
        Number of days requested when refreshing API data.

    refresh_key:
        Retained for compatibility with the dashboard.

    use_api:
        When True, download fresh API data and save processed CSV files.
        When False, read existing local CSV files only.
    """
      
    return load_local_data()


if __name__ == "__main__":
    # Running data_loader.py directly is an explicit API refresh.
    df_raw, df_display, df_hourly, *_ = build_dataset(
        days=365,
        save_csv=True,
    )

    print("Total energy:", df_raw["total_energy"].sum())