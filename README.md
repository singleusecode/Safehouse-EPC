# Safehouse-EPC

Safehouse-EPC is a Streamlit application developed as part of an MSc Data Science and Analytics project in collaboration with Safehouse Technology. It combines smart meter energy consumption data with indoor environmental sensor data to provide interactive analysis of residential energy performance, building efficiency, and indoor environmental quality.

## Features

- Interactive Streamlit dashboard
- Electricity and gas consumption
- Heat Transfer Coefficient (HTC) estimation
- Indoor temperature, humidity and CO₂ monitoring
- Mould risk assessment
- Anomaly detection using Isolation Forest
- Integration with CGI WiseWatt API

## Run the Application

To Run the Application:
1. Install required packages:
pip install -r requirements.txt
2. Run the Streamlit dashboard:
python -m streamlit run 0_safehouse_EPC.py

## Project Structure

`0_Safehouse_EPC.py` - Main Streamlit dashboard.
`pages/1_WiseWatt_API_Test.py` - WiseWatt API testing and Consent Manager page.
`pages/2_WiseWatt_Batch_Lookup.py` - Batch DCC smart meter energy data download tool.
`data_loader.py` - Data loading, preprocessing and alignment.
`htc_analysis.py` - HTC estimation, feature engineering and anomaly detection.
`charts.py` - Interactive visualisations with Plotly.
`constants.py` - Shared constants and configuration values.
`requirements.txt` - Python package dependencies.

## Data Source

The dashboard can:
- Lookup smartmeter inventory from CGI WiseWatt.
- Retrieve Smart meter electricity and gas data from Octopus API.
- Retrieve Smart meter electricity data from CGI Wisewatt (WIP).
- Retrieve Smart meter gas data from CGI Wisewatt (WIP).
- Indoor IoT environmental sensors data from Safehouse Viper API .

## Notes

- API keys and credentials have been removed.
- The dashboard can operate using local CSV files or live APIs.

## Licence

Released under the MIT License. See the `LICENSE` file for details.