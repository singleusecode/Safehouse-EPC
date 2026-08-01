# Safehouse-EPC
Dashboard built in Streamlit for residential energy analytics using smart meter and IoT environmental sensor data. Features HTC analysis, anomaly detection, mould risk assessment, CO₂ monitoring and interactive visualisations.

To Run the Application:
1. Install required packages:
pip install -r requirements.txt
2. Run the Streamlit dashboard:
python -m streamlit run 0_safehouse_EPC.py

List of Files
1. 0_Safehouse_EPC.py - 		Main Streamlit dashboard application (entry point)
2. 1_Safehouse Consent Manager - 	Additional web page that interacts with CGI WiseWatt API to download property energy consumption data from DCC. Not used as API is paid and Octopus API was used to download energy consumption data for one property.	
3. data_loader.py - 			Handles data ingestion, API integration, preprocessing, and alignment
4. htc_analysis.py - 			Contains analytical methods including:
						Heat Transfer Coefficient (HTC) estimation - Rolling HTC calculation
						Anomaly detection (Isolation Forest)
						Feature engineering
5. charts.py - 				Visualisation functions for energy, environment, and HTC plots
6. csv_data/ - 				Contains sample processed datasets:
						aligned_30min.csv
						final_results.csv
7. requirements.txt - 			List of required Python packages

Notes
1. API keys and live data access have been removed for submission.
2. Sample datasets are provided in the csv_data folder to allow the system to run.
