from geopy.distance import geodesic
from math import radians, atan2, degrees, cos, sin
import pandas as pd
import webbrowser

# Load FTTH databases
def load_database(file_path, sheet_name):
    print(f"Loading data from {sheet_name} in {file_path}...")
    try:
        data = pd.read_excel(file_path, sheet_name=sheet_name)
        print(f"Data loaded successfully from sheet '{sheet_name}'.")
        return data
    except Exception as e:
        raise ValueError(f"Error loading database: {e}")

# Validate input segment
def validate_segment(segment_data, segment_id):
    data = segment_data[segment_data['Segment_ID'] == segment_id]
    if data.empty:
        raise ValueError(f"Invalid Segment_ID: {segment_id}. Please check your input.")
    return data

# Predict cut location
def predict_cut_location(segment_poles, poles_data, distance_otdr, slack_ratio=1.1):
    """
    Predict the cut location based on OTDR distance.
    :param segment_poles: DataFrame of segment poles
    :param poles_data: DataFrame of poles data
    :param distance_otdr: Measured OTDR distance
    :param slack_ratio: Slack ratio for cable adjustment
    :return: Tuple of latitude and longitude for predicted cut location
    """
    # Tambahkan 20% pada jarak OTDR
    adjusted_otdr_distance = distance_otdr * 1.05
    print(f"Adjusted OTDR distance (with 20% increase): {adjusted_otdr_distance:.2f} meters")

    accumulated_distance = 0
    for idx, row in segment_poles.iterrows():
        pole_distance = row['Distance (m)']
        cable_adjustment = ((accumulated_distance + pole_distance) // 500) * 25 * slack_ratio
        effective_distance = adjusted_otdr_distance - cable_adjustment

        if accumulated_distance + pole_distance >= effective_distance:
            distance_within_segment = effective_distance - accumulated_distance
            start_coords = poles_data.loc[poles_data['Pole_ID'] == row['Pole_ID'], ['Latitude', 'Longitude']].values[0]
            end_coords = None
            if idx + 1 < len(segment_poles):
                next_pole_id = segment_poles.iloc[idx + 1]['Pole_ID']
                end_coords = poles_data.loc[poles_data['Pole_ID'] == next_pole_id, ['Latitude', 'Longitude']].values[0]
            if end_coords is None or distance_within_segment == 0:
                return start_coords
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

# Open Google Maps with the predicted location
def open_google_maps(lat, lon):
    url = f"https://www.google.com/maps?q={lat},{lon}"
    print(f"Opening Google Maps at: {url}")
    webbrowser.open(url)

# Main program
def main():
    file_path = "C:/Python/FTTH/FTTH_DB.xlsx"
    poles_sheet = "poles_db"
    segment_poles_sheet = "segments_db"
    olt_sheet = "olt_db"

    try:
        poles_data = load_database(file_path, poles_sheet)
        segment_poles_data = load_database(file_path, segment_poles_sheet)
        olt_data = load_database(file_path, olt_sheet)

        # Data cleanup
        for data in [poles_data, segment_poles_data, olt_data]:
            for col in ['Residences', 'OLT_ID', 'Segment_ID']:
                if col in data.columns:
                    data[col] = data[col].astype(str).str.strip()

        # Validate columns
        required_columns = {
            "poles_db": ['Pole_ID', 'Latitude', 'Longitude'],
            "segments_db": ['Residences', 'OLT_ID', 'Segment_ID', 'Pole_ID', 'Distance (m)'],
            "olt_db": ['Residences', 'OLT_ID']
        }
        for sheet_name, cols in required_columns.items():
            data = {"poles_db": poles_data, "segments_db": segment_poles_data, "olt_db": olt_data}[sheet_name]
            for col in cols:
                if col not in data.columns:
                    raise ValueError(f"Missing required column in {sheet_name}: {col}")

        # Step 1: Select City
        cities = olt_data['Residences'].unique()
        print(f"Available Cities: {', '.join(cities)}")
        city = input("Enter the City: ")
        if city not in cities:
            raise ValueError(f"Invalid City: {city}")

        # Step 2: Select OLT
        filtered_olt_data = olt_data[olt_data['Residences'] == city]
        olts = filtered_olt_data['OLT_ID'].unique()
        print(f"Available OLTs in {city}: {', '.join(olts)}")
        olt_id = input("Enter the OLT ID: ")
        if olt_id not in olts:
            raise ValueError(f"Invalid OLT ID: {olt_id}")

        # Step 3: Select Segment
        filtered_segments = segment_poles_data[
            (segment_poles_data['Residences'] == city) & 
            (segment_poles_data['OLT_ID'] == olt_id)
        ]
        segments = filtered_segments['Segment_ID'].unique()
        if len(segments) == 0:
            raise ValueError(f"No segments found for OLT {olt_id} in {city}.")
        print(f"Available Segments for {olt_id} in {city}: {', '.join(segments)}")
        segment_id = input("Enter the Segment ID: ")
        if segment_id not in segments:
            raise ValueError(f"Invalid Segment ID: {segment_id}")

        # Validate segment input
        segment_poles = validate_segment(filtered_segments, segment_id)

        # Step 4: Extract OTDR cut distance
        distance_otdr = float(input("Enter the OTDR cut distance (in meters): "))

        # Predict cut location
        slack_ratio = 1.1  # Adjust based on calibration
        cut_coords = predict_cut_location(segment_poles, poles_data, distance_otdr, slack_ratio=slack_ratio)
        print(f"Predicted cut location: Latitude={cut_coords[0]}, Longitude={cut_coords[1]}")

        # Open Google Maps with the predicted location
        open_google_maps(cut_coords[0], cut_coords[1])

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()