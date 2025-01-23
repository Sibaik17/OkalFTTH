import streamlit as st
from geopy.distance import geodesic
from math import radians, atan2, degrees, cos, sin
import pandas as pd
import requests
from io import BytesIO

# Load FTTH database from GitHub
def load_database_from_github(url, sheet_name):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = pd.read_excel(BytesIO(response.content), sheet_name=sheet_name)
            return data
        else:
            st.error(f"Error fetching database from GitHub: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return None

# Validate input segment
def validate_segment(segment_data, segment_id):
    data = segment_data[segment_data['Segment_ID'] == segment_id]
    if data.empty:
        raise ValueError(f"Invalid Segment_ID: {segment_id}. Please check your input.")
    return data

# Predict cut location
def predict_cut_location(segment_poles, poles_data, distance_otdr, slack_ratio=1.05):
    adjusted_otdr_distance = distance_otdr * 1.005
    accumulated_distance = 0

    for idx, row in segment_poles.iterrows():
        pole_distance = row['Distance (m)']
        cable_adjustment = ((accumulated_distance + pole_distance) // 500) * 15 * slack_ratio
        effective_distance = adjusted_otdr_distance - cable_adjustment

        if accumulated_distance + pole_distance >= effective_distance:
            distance_within_segment = effective_distance - accumulated_distance
            start_coords = poles_data.loc[poles_data['Pole_ID'] == row['Pole_ID'], ['Latitude', 'Longitude']].values[0]
            end_coords = None
            if idx + 1 < len(segment_poles):
                next_pole_id = segment_poles.iloc[idx + 1]['Pole_ID']
                end_coords = poles_data.loc[poles_data['Pole_ID'] == next_pole_id, ['Latitude', 'Longitude']].values[0]
            if end_coords is None or distance_within_segment == 0:
                return tuple(start_coords)
            bearing = calculate_initial_bearing(tuple(start_coords), tuple(end_coords))
            cut_coords = geodesic(kilometers=distance_within_segment / 1000).destination(tuple(start_coords), bearing)
            return (cut_coords.latitude, cut_coords.longitude)

        accumulated_distance += pole_distance

    raise ValueError("OTDR distance exceeds total distance of the segment.")

# Calculate initial bearing between two points
def calculate_initial_bearing(start_coords, end_coords):
    lat1, lon1 = map(radians, start_coords)
    lat2, lon2 = map(radians, end_coords)
    delta_lon = lon2 - lon1
    x = sin(delta_lon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(delta_lon)
    bearing = atan2(x, y)
    return (degrees(bearing) + 360) % 360

# Streamlit app
def main():
    st.title("FTTH Cut Prediction System")
    st.sidebar.header("Input Parameters")

    # Step 1: Specify GitHub Raw URL
    github_url = st.sidebar.text_input(
        "Enter GitHub Raw URL for FTTH Database",
        value="FTTH_DB.xlsx"
    )
    if not github_url:
        st.warning("Please provide a valid GitHub Raw URL for the database.")
        return

    # Load database from GitHub
    poles_data = load_database_from_github(github_url, "poles_db")
    segment_poles_data = load_database_from_github(github_url, "segments_db")
    olt_data = load_database_from_github(github_url, "olt_db")
    if not (poles_data is not None and segment_poles_data is not None and olt_data is not None):
        return

    # Step 2: Select City
    cities = olt_data['Residences'].unique()
    city = st.selectbox("Select City", cities)

    # Step 3: Select OLT
    filtered_olt_data = olt_data[olt_data['Residences'] == city]
    olts = filtered_olt_data['OLT_Name'].unique()
    olt_name = st.selectbox("Select OLT Name", olts)

    # Step 4: Select Segment
    filtered_segments = segment_poles_data[
        (segment_poles_data['Residences'] == city) &
        (segment_poles_data['OLT_Name'] == olt_name)
    ]
    segments = filtered_segments['Segment_ID'].unique()
    segment_id = st.selectbox("Select Segment", segments)

    # Step 5: Enter OTDR cut distance
    distance_otdr = st.number_input("Enter OTDR Cut Distance (in meters):", min_value=0.0)

    # Prediction
    if st.button("Predict Cut Location"):
        try:
            segment_poles = validate_segment(filtered_segments, segment_id)
            slack_ratio = 1.1  # Adjust based on calibration
            cut_coords = predict_cut_location(segment_poles, poles_data, distance_otdr, slack_ratio=slack_ratio)
            st.success(f"Predicted Cut Location: Latitude={cut_coords[0]:.6f}, Longitude={cut_coords[1]:.6f}")

            # Display predicted location on map
            st.map(pd.DataFrame([{"lat": cut_coords[0], "lon": cut_coords[1]}]))

            # Generate Google Maps link
            google_maps_link = f"https://www.google.com/maps?q={cut_coords[0]},{cut_coords[1]}"
            st.markdown(f"[View Predicted Location on Google Maps]({google_maps_link})")

        except Exception as e:
            st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
