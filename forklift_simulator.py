#!/usr/bin/env python3
import socket
import json
import time
import math
import random
import threading
import argparse
from datetime import datetime

# Configuration
DEFAULT_SERVER_IP = "127.0.0.1"
DEFAULT_SERVER_PORT = 5000

# Environment settings
ENVIRONMENT_SIZE = {
    "indoor": (25, 20),   # 500 m² underground area (25m x 20m)
    "outdoor": (1000, 1000)  # 1 km² outdoor yard
}

# Beacon/antenna positions for indoor positioning
BEACON_POSITIONS = {
    'beacon1': (0, 0),
    'beacon2': (25, 0),
    'beacon3': (25, 20),
    'beacon4': (0, 20)
}

# Charging station positions
CHARGING_STATIONS = {
    'indoor_charge1': (2, 2),
    'indoor_charge2': (23, 18),
    'outdoor_charge1': (100, 100),
    'outdoor_charge2': (900, 900)
}

# Signal parameters for simulation
RSSI_AT_1M = -60
PATH_LOSS_EXPONENT = 3.0
RSSI_NOISE_STD_DEV = 3.0  # Standard deviation for RSSI noise (dBm)

# Forklift parameters
MAX_SPEED_INDOOR = 2.0  # m/s (~7.2 km/h)
MAX_SPEED_OUTDOOR = 5.0  # m/s (~18 km/h)
ACCELERATION = 0.2  # m/s²
PROBABILITY_OF_STANDING_STILL = 0.15
PROBABILITY_OF_IMPACT = 0.01  # Low probability of impact

# Calculate distance between two points
def calculate_distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

# Calculate RSSI from distance with realistic noise (for indoor positioning)
def calculate_rssi_from_distance(distance):
    if distance <= 0:
        return RSSI_AT_1M
    
    # Calculate ideal RSSI
    ideal_rssi = RSSI_AT_1M - 10 * PATH_LOSS_EXPONENT * math.log10(distance)
    
    # Add realistic noise
    noise = random.gauss(0, RSSI_NOISE_STD_DEV)
    
    return round(ideal_rssi + noise)

# Simulate forklift movement and sensor data
class ForkliftSimulator:
    def __init__(self, forklift_id, environment="indoor", update_interval=1.0):
        self.forklift_id = forklift_id
        self.environment = environment
        self.update_interval = update_interval
        self.room_size = ENVIRONMENT_SIZE[environment]
        
        # Starting position (random within the environment)
        self.x = random.uniform(0, self.room_size[0])
        self.y = random.uniform(0, self.room_size[1])
        
        # Movement parameters
        self.speed = 0.0  # starting speed
        self.max_speed = MAX_SPEED_INDOOR if environment == "indoor" else MAX_SPEED_OUTDOOR
        self.direction = random.uniform(0, 2 * math.pi)  # random direction
        self.distance_traveled = 0.0  # total distance traveled
        self.standing_still = False
        self.battery_level = random.uniform(50, 100)  # starting battery level (%)
        self.impacts = []  # list to store impact events
        
        # Stats tracking
        self.max_recorded_speed = 0.0
        self.speed_readings = []
        self.start_time = time.time()
        
        # GPS accuracy depends on environment (indoor uses beacons instead)
        self.position_accuracy = 0.5 if environment == "outdoor" else 2.0
        
        # Start the simulation thread
        self.running = True
        self.thread = threading.Thread(target=self._simulation_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def _simulation_loop(self):
        last_update = time.time()
        
        while self.running:
            current_time = time.time()
            time_delta = current_time - last_update
            
            # Update battery level (slowly decrease)
            self.battery_level -= 0.01 * time_delta
            if self.battery_level < 0:
                self.battery_level = 0
            
            # Check if near charging station and recharge if battery is low
            if self.battery_level < 30:
                for station_id, pos in CHARGING_STATIONS.items():
                    if calculate_distance(self.x, self.y, pos[0], pos[1]) < 3:
                        self.speed = 0
                        self.standing_still = True
                        self.battery_level += 2 * time_delta  # Recharge rate
                        if self.battery_level > 100:
                            self.battery_level = 100
                        break
            
            # Randomly decide if standing still or moving
            if random.random() < PROBABILITY_OF_STANDING_STILL:
                self.standing_still = True
                # Slow down if standing still
                self.speed = max(0, self.speed - ACCELERATION * time_delta)
            else:
                self.standing_still = False
                
                # Randomly change direction occasionally
                if random.random() < 0.05:
                    self.direction = random.uniform(0, 2 * math.pi)
                
                # Accelerate/decelerate randomly
                if random.random() < 0.7:  # 70% chance to accelerate
                    self.speed = min(self.max_speed, self.speed + ACCELERATION * time_delta)
                else:
                    self.speed = max(0, self.speed - ACCELERATION * time_delta)
            
            # Move in the current direction
            distance = self.speed * time_delta
            new_x = self.x + distance * math.cos(self.direction)
            new_y = self.y + distance * math.sin(self.direction)
            
            # Check if new position is within bounds, otherwise bounce
            if new_x < 0 or new_x > self.room_size[0]:
                self.direction = math.pi - self.direction
                new_x = max(0, min(self.room_size[0], new_x))
            
            if new_y < 0 or new_y > self.room_size[1]:
                self.direction = 2 * math.pi - self.direction
                new_y = max(0, min(self.room_size[1], new_y))
            
            # Update position
            old_x, old_y = self.x, self.y
            self.x, self.y = new_x, new_y
            
            # Calculate distance traveled in this update
            step_distance = calculate_distance(old_x, old_y, new_x, new_y)
            self.distance_traveled += step_distance
            
            # Track speed statistics
            if self.speed > self.max_recorded_speed:
                self.max_recorded_speed = self.speed
            
            self.speed_readings.append(self.speed)
            if len(self.speed_readings) > 100:  # Keep only recent readings
                self.speed_readings = self.speed_readings[-100:]
            
            # Randomly generate impact events
            if not self.standing_still and random.random() < PROBABILITY_OF_IMPACT:
                impact_magnitude = random.uniform(0.5, 5.0)  # G-force
                self.impacts.append({
                    'timestamp': datetime.now().isoformat(),
                    'magnitude': impact_magnitude,
                    'position': (self.x, self.y)
                })
                print(f"Impact detected for forklift {self.forklift_id}! Magnitude: {impact_magnitude:.2f}G")
            
            last_update = current_time
            time.sleep(0.1)  # Update position 10 times per second
    
    def get_position(self):
        # Add some noise to position based on environment
        noise_x = random.gauss(0, self.position_accuracy)
        noise_y = random.gauss(0, self.position_accuracy)
        return (self.x + noise_x, self.y + noise_y)
    
    def get_average_speed(self):
        if not self.speed_readings:
            return 0.0
        return sum(self.speed_readings) / len(self.speed_readings)
    
    def get_telemetry(self):
        position = self.get_position()
        
        # Get beacon readings if indoor
        beacon_readings = {}
        if self.environment == "indoor":
            for beacon_id, beacon_pos in BEACON_POSITIONS.items():
                distance = calculate_distance(self.x, self.y, beacon_pos[0], beacon_pos[1])
                rssi = calculate_rssi_from_distance(distance)
                beacon_readings[beacon_id] = {
                    'distance': round(distance, 2),
                    'rssi': rssi
                }
        
        return {
            'timestamp': datetime.now().isoformat(),
            'forklift_id': self.forklift_id,
            'environment': self.environment,
            'position': {
                'x': round(position[0], 2),
                'y': round(position[1], 2)
            },
            'speed': round(self.speed, 2),
            'max_speed': round(self.max_recorded_speed, 2),
            'avg_speed': round(self.get_average_speed(), 2),
            'distance_traveled': round(self.distance_traveled, 2),
            'battery_level': round(self.battery_level, 2),
            'standing_still': self.standing_still,
            'beacon_readings': beacon_readings if self.environment == "indoor" else {},
            'impacts': self.impacts[-5:] if self.impacts else []  # Send only recent impacts
        }
    
    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

# Send telemetry data to server
class TelemetrySender:
    def __init__(self, forklift, server_ip, server_port, update_interval=1.0):
        self.forklift = forklift
        self.server_ip = server_ip
        self.server_port = server_port
        self.update_interval = update_interval
        
        # Start the sender thread
        self.running = True
        self.thread = threading.Thread(target=self._sender_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def _sender_loop(self):
        while self.running:
            try:
                # Get telemetry data
                telemetry = self.forklift.get_telemetry()
                
                # Send data to server
                self._send_data_to_server(telemetry)
                
                # Print summary
                print(f"Forklift {self.forklift.forklift_id} - "
                      f"Position: ({telemetry['position']['x']:.2f}, {telemetry['position']['y']:.2f}), "
                      f"Speed: {telemetry['speed']:.2f} m/s, "
                      f"Battery: {telemetry['battery_level']:.1f}%, "
                      f"Distance: {telemetry['distance_traveled']:.2f}m")
            
            except Exception as e:
                print(f"Error sending telemetry: {e}")
            
            time.sleep(self.update_interval)
    
    def _send_data_to_server(self, data):
        try:
            # Create a socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.server_ip, self.server_port))
            
            # Send JSON data
            sock.sendall(json.dumps(data).encode())
            
            # Close the socket
            sock.close()
        except Exception as e:
            print(f"Failed to send data to server: {e}")
    
    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

def main():
    parser = argparse.ArgumentParser(description='Forklift Tracking System Simulator')
    parser.add_argument('--server', default=DEFAULT_SERVER_IP, help='Server IP address')
    parser.add_argument('--port', type=int, default=DEFAULT_SERVER_PORT, help='Server port')
    parser.add_argument('--interval', type=float, default=1.0, help='Update interval in seconds')
    parser.add_argument('--forklifts', type=int, default=3, help='Number of forklifts to simulate')
    args = parser.parse_args()
    
    try:
        print(f"Starting Forklift Tracking System simulator...")
        print(f"Sending data to server at {args.server}:{args.port}")
        print(f"Update interval: {args.interval} seconds")
        print(f"Number of forklifts: {args.forklifts}")
        print("Press Ctrl+C to stop the simulation")
        
        # Create forklift simulators
        forklifts = []
        senders = []
        
        for i in range(1, args.forklifts + 1):
            # Randomly assign to indoor or outdoor
            environment = "indoor" if random.random() < 0.5 else "outdoor"
            
            # Create forklift simulator
            forklift = ForkliftSimulator(
                forklift_id=f"FL-{i:03d}",
                environment=environment,
                update_interval=args.interval
            )
            forklifts.append(forklift)
            
            # Create telemetry sender
            sender = TelemetrySender(
                forklift=forklift,
                server_ip=args.server,
                server_port=args.port,
                update_interval=args.interval
            )
            senders.append(sender)
        
        # Keep the main thread running
        while True:
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("\nStopping simulation...")
    finally:
        # Stop all simulators and senders
        for forklift in forklifts:
            forklift.stop()
        
        for sender in senders:
            sender.stop()
        
        print("Simulation stopped.")

if __name__ == "__main__":
    main()
