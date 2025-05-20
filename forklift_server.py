#!/usr/bin/env python3
import socket
import threading
import json
import csv
import time
import os
from datetime import datetime
import math
import numpy as np

# Configuration
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 5000  # Port to use
DATA_DIR = "forklift_data"  # Directory for data

# Beacon positions (for indoor positioning)
BEACON_POSITIONS = {
    'beacon1': (0, 0),
    'beacon2': (25, 0),
    'beacon3': (25, 20),
    'beacon4': (0, 20)
}

# Create data directory with timestamp
def create_data_directory():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    folder_name = os.path.join(DATA_DIR, f"session_{timestamp}")
    
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
        print(f"Created data directory: {folder_name}")
    
    return folder_name

# Initialize CSV files for each forklift
def initialize_forklift_csv(folder_name, forklift_id):
    csv_path = os.path.join(folder_name, f'{forklift_id}_data.csv')
    
    headers = [
        'timestamp', 
        'forklift_id',
        'environment',
        'x_position', 
        'y_position', 
        'speed', 
        'max_speed',
        'avg_speed',
        'distance_traveled',
        'battery_level',
        'standing_still'
    ]
    
    # Add columns for indoor beacon readings
    for beacon_name in BEACON_POSITIONS.keys():
        headers.append(f'distance_{beacon_name}')
        headers.append(f'rssi_{beacon_name}')
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
    
    print(f"Initialized CSV file for {forklift_id}: {csv_path}")
    return csv_path

# Initialize impacts CSV file
def initialize_impacts_csv(folder_name):
    csv_path = os.path.join(folder_name, 'impacts.csv')
    
    headers = [
        'timestamp',
        'forklift_id',
        'magnitude',
        'x_position',
        'y_position'
    ]
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
    
    print(f"Initialized impacts CSV file: {csv_path}")
    return csv_path

# Update CSV with forklift data
def update_forklift_csv(csv_path, data):
    try:
        with open(csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            
            # Extract data
            timestamp = data.get('timestamp', datetime.now().isoformat())
            forklift_id = data.get('forklift_id', 'unknown')
            environment = data.get('environment', 'unknown')
            position = data.get('position', {'x': 0, 'y': 0})
            x_position = position.get('x', 0)
            y_position = position.get('y', 0)
            speed = data.get('speed', 0)
            max_speed = data.get('max_speed', 0)
            avg_speed = data.get('avg_speed', 0)
            distance_traveled = data.get('distance_traveled', 0)
            battery_level = data.get('battery_level', 0)
            standing_still = 1 if data.get('standing_still', False) else 0
            
            # Prepare row data
            row_data = [
                timestamp,
                forklift_id,
                environment,
                x_position,
                y_position,
                speed,
                max_speed,
                avg_speed, 
                distance_traveled,
                battery_level,
                standing_still
            ]
            
            # Add beacon readings if available
            beacon_readings = data.get('beacon_readings', {})
            for beacon_name in BEACON_POSITIONS.keys():
                if beacon_name in beacon_readings:
                    row_data.append(beacon_readings[beacon_name].get('distance', ''))
                    row_data.append(beacon_readings[beacon_name].get('rssi', ''))
                else:
                    row_data.append('')  # Distance
                    row_data.append('')  # RSSI
            
            writer.writerow(row_data)
    except Exception as e:
        print(f"Error writing to forklift CSV: {e}")

# Update impacts CSV with any impacts
def update_impacts_csv(csv_path, forklift_id, impacts):
    if not impacts:
        return
    
    try:
        with open(csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            
            for impact in impacts:
                timestamp = impact.get('timestamp', datetime.now().isoformat())
                magnitude = impact.get('magnitude', 0)
                position = impact.get('position', (0, 0))
                
                row_data = [
                    timestamp,
                    forklift_id,
                    magnitude,
                    position[0],
                    position[1]
                ]
                
                writer.writerow(row_data)
    except Exception as e:
        print(f"Error writing to impacts CSV: {e}")

# Process indoor positioning data using RSSI
def process_indoor_position(beacon_readings):
    """
    Calculate position using RSSI-based trilateration
    Returns estimated (x,y) position
    """
    # Implement a simple weighted centroid algorithm
    if not beacon_readings:
        return None, None
    
    total_weight = 0
    x_weighted_sum = 0
    y_weighted_sum = 0
    
    for beacon_id, data in beacon_readings.items():
        if beacon_id in BEACON_POSITIONS and 'rssi' in data:
            rssi = data['rssi']
            # Convert RSSI to weight (stronger signal = higher weight)
            # Normalize RSSI to positive value for weight calculation
            weight = 10 ** ((rssi + 100) / 20)  # Simple conversion to make stronger signals have higher weights
            
            beacon_x, beacon_y = BEACON_POSITIONS[beacon_id]
            x_weighted_sum += beacon_x * weight
            y_weighted_sum += beacon_y * weight
            total_weight += weight
    
    if total_weight > 0:
        return x_weighted_sum / total_weight, y_weighted_sum / total_weight
    
    return None, None

# Handle client connection from a forklift
def handle_client(client_socket, folder_name, csv_files, impacts_csv_path):
    try:
        # Receive data
        data_raw = client_socket.recv(4096)  # Increased buffer size for larger JSON
        if not data_raw:
            return
        
        # Decode JSON
        data = json.loads(data_raw.decode())
        
        # Extract forklift ID
        forklift_id = data.get('forklift_id')
        if not forklift_id:
            print("Received data without forklift ID")
            return
            
        # If this is the first time we've seen this forklift, initialize its CSV
        if forklift_id not in csv_files:
            csv_files[forklift_id] = initialize_forklift_csv(folder_name, forklift_id)
            
        # Process and improve indoor positioning if needed
        if data.get('environment') == 'indoor' and 'beacon_readings' in data:
            estimated_x, estimated_y = process_indoor_position(data['beacon_readings'])
            if estimated_x is not None and estimated_y is not None:
                # Add the processed indoor position as supplementary data
                data['processed_indoor_position'] = {
                    'x': round(estimated_x, 2),
                    'y': round(estimated_y, 2)
                }
                
                # We could optionally replace the original position with our processed one
                # data['position']['x'] = round(estimated_x, 2)
                # data['position']['y'] = round(estimated_y, 2)
        
        # Update CSV with forklift data
        update_forklift_csv(csv_files[forklift_id], data)
        
        # Process impacts if any
        if 'impacts' in data and data['impacts']:
            update_impacts_csv(impacts_csv_path, forklift_id, data['impacts'])
            
        # Print status update
        print(f"Processed data from {forklift_id}, environment: {data.get('environment')}, "
              f"battery: {data.get('battery_level')}%, total distance: {data.get('distance_traveled')}m")
            
    except Exception as e:
        print(f"Error handling client data: {e}")
    finally:
        client_socket.close()

# Start server
def start_server():
    # Create directory structure
    folder_name = create_data_directory()
    
    # Track CSV files for each forklift
    csv_files = {}
    
    # Initialize impacts CSV
    impacts_csv_path = initialize_impacts_csv(folder_name)
    
    # Write current session path to a file for the dashboard
    with open("current_session.txt", 'w') as f:
        f.write(folder_name)
    
    # Initialize server socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((HOST, PORT))
        server.listen(5)
        print(f"Forklift tracking server listening on {HOST}:{PORT}")
        print(f"Data being saved to {folder_name}")
        
        # Main loop to accept connections
        while True:
            client, addr = server.accept()
            # print(f"Connection accepted from {addr[0]}:{addr[1]}")
            
            # Handle client in separate thread
            client_thread = threading.Thread(
                target=handle_client, 
                args=(client, folder_name, csv_files, impacts_csv_path)
            )
            client_thread.daemon = True
            client_thread.start()
            
    except KeyboardInterrupt:
        print("Server terminated by user")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        server.close()

if __name__ == "__main__":
    print("Starting forklift tracking server...")
    start_server()
