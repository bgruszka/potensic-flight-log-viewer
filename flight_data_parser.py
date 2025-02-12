import struct
import math
import datetime
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from geopy.distance import geodesic

@dataclass
class FlightPoint:
    timestamp: datetime.datetime
    latitude: float
    longitude: float
    altitude: float
    speed: float
    battery_level: int
    satellites: int
    flight_mode: str
    distance_from_home: float

class FlightDataParser:
    def __init__(self):
        self.flight_points: List[FlightPoint] = []
        self.home_position: Optional[Tuple[float, float]] = None

    def _is_valid_coordinates(self, latitude: float, longitude: float) -> bool:
        """Validate GPS coordinates."""
        return -90 <= latitude <= 90 and -180 <= longitude <= 180

    def _is_valid_point_transition(self, prev_point: FlightPoint, current_point: FlightPoint) -> bool:
        """Check if the transition between two points is valid based on reasonable drone movement."""
        try:
            # First validate the coordinates
            if not self._is_valid_coordinates(current_point.latitude, current_point.longitude):
                return False
            
            # Calculate distance between points
            distance = geodesic(
                (prev_point.latitude, prev_point.longitude),
                (current_point.latitude, current_point.longitude)
            ).meters
            
            # Calculate time difference in seconds
            time_diff = (current_point.timestamp - prev_point.timestamp).total_seconds()
            
            if time_diff == 0 or distance == 0:
                return False
                
            # Calculate speed in m/s
            speed = distance / time_diff
            
            # Maximum reasonable speed for the drone (in m/s)
            MAX_SPEED = 30  # Adjust based on drone specifications
            
            # Allow stationary or slow-moving points, but filter out unreasonable speeds
            return speed <= MAX_SPEED
        except Exception:
            return False

    def _get_flight_mode(self, mode: int) -> str:
        """Convert flight mode number to string description."""
        # Flight mode mapping based on original parser
        modes = {
            7: 'VIDEO',
            8: 'NORMAL',
            9: 'SPORT'
        }
        return modes.get(mode, 'UNKNOWN')

    def parse_fc_record(self, record: bytes, base_timestamp: datetime.datetime) -> Optional[FlightPoint]:
        """Parse a single flight controller record."""
        try:
            # Check if we have enough data
            if len(record) < 512:
                return None

            # Parse the record header
            record_type = struct.unpack('<B', record[0:1])[0]
            # Check for valid record type and length
            if record_type != 0x55 or len(record) < 512:  # Magic number for valid records
                return None

            # Determine if this is a legacy log format
            is_legacy_log = struct.unpack('<B', record[509:510])[0] == 0 and \
                          struct.unpack('<B', record[510:511])[0] == 0 and \
                          struct.unpack('<B', record[511:512])[0] == 0
            
            # Apply offsets based on log format
            offset1 = 0 if is_legacy_log else -6
            offset2 = 0 if is_legacy_log else -10
            offset3 = 0 if is_legacy_log else -14

            # Parse GPS data with correct offsets
            latitude = struct.unpack('<i', record[53+offset1:57+offset1])[0] / 10000000  # Drone latitude
            longitude = struct.unpack('<i', record[57+offset1:61+offset1])[0] / 10000000  # Drone longitude
            altitude = struct.unpack('<f', record[243+offset2:247+offset2])[0]  # Relative height
            speed = struct.unpack('<f', record[327+offset2:331+offset2])[0]  # Horizontal speed

            # Validate GPS coordinates before proceeding
            if not self._is_valid_coordinates(latitude, longitude):
                return None

            # Parse flight status with correct offsets
            battery_level = struct.unpack('<B', record[481+offset3:482+offset3])[0]  # Battery level
            satellites = struct.unpack('<B', record[46:47])[0]  # Number of satellites
            flight_mode = struct.unpack('<B', record[448+offset2:449+offset2])[0]  # Flight mode

            # Parse timestamp offset (in milliseconds)
            time_offset = struct.unpack('<I', record[24:28])[0]
            timestamp = base_timestamp + datetime.timedelta(milliseconds=time_offset)

            # Store home position if not already set
            if not self.home_position and latitude != 0 and longitude != 0:
                self.home_position = (latitude, longitude)

            # Calculate distance from home
            distance_from_home = 0.0
            if self.home_position:
                home_coords = (self.home_position[0], self.home_position[1])
                point_coords = (latitude, longitude)
                try:
                    distance_from_home = geodesic(home_coords, point_coords).meters
                except Exception:
                    distance_from_home = 0.0

            return FlightPoint(
                timestamp=timestamp,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                speed=speed,
                battery_level=battery_level,
                satellites=satellites,
                flight_mode=self._get_flight_mode(flight_mode),
                distance_from_home=distance_from_home
            )

        except Exception:
            return None

    def parse_flight_data(self, fc_file_path: str) -> Dict:
        """Parse a complete flight controller file."""
        try:
            # Extract timestamp from filename
            base_timestamp = datetime.datetime.strptime(
                re.sub("-.*", "", fc_file_path.split('/')[-1]),
                '%Y%m%d%H%M%S'
            )

            with open(fc_file_path, 'rb') as fc_file:
                while True:
                    record = fc_file.read(512)
                    if len(record) < 512:
                        break

                    point = self.parse_fc_record(record, base_timestamp)
                    if point and point.latitude != 0 and point.longitude != 0 and point.satellites >= 4:
                        # Only add point if it's a reasonable distance from the previous point
                        if not self.flight_points or self._is_valid_point_transition(self.flight_points[-1], point):
                            self.flight_points.append(point)

            if not self.flight_points:
                return {
                    'status': 'error',
                    'message': 'No valid flight data points found'
                }

            return {
                'status': 'success',
                'points': [
                    {
                        'timestamp': p.timestamp.isoformat(),
                        'latitude': p.latitude,
                        'longitude': p.longitude,
                        'altitude': p.altitude,
                        'speed': p.speed,
                        'battery_level': p.battery_level,
                        'satellites': p.satellites,
                        'flight_mode': p.flight_mode,
                        'distance_from_home': p.distance_from_home
                    } for p in self.flight_points
                ],
                'home_position': self.home_position
            }

        except Exception as e:
            import traceback
            stack_trace = traceback.format_exc()
            return {
                'status': 'error',
                'message': f'Error parsing flight data: {str(e)}',
                'stack_trace': stack_trace
            }