import os
import io
from datetime import datetime
import googlemaps
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

# Use a single BASE_DIR definition that works cross-platform
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

X_COORD = 'x'
Y_COORD = 'y'
COORDINATES = 'coordinates'
INSTANCE_NAME = 'instance_name'
MAX_VEHICLE_NUMBER = 'max_vehicle_number'
VEHICLE_CAPACITY = 'vehicle_capacity'
DEPART = 'depart'
DEMAND = 'demand'
READY_TIME = 'ready_time'
DUE_TIME = 'due_time'
SERVICE_TIME = 'service_time'
DISTANCE_MATRIX = 'distance_matrix'

class ProblemInstance:
    _instance = None
    _data = None
    
    def __new__(cls, problem_name=None, force_recalculate=False):
        if cls._instance is None:
            cls._instance = super(ProblemInstance, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, problem_name=None, force_recalculate=False):
        if self._data is None and problem_name:
            self._data = self._load_problem_instance(problem_name, force_recalculate)
    
    def get_data(self):
        return self._data
    
    def _load_problem_instance(self, problem_name, force_recalculate=False):
        """Load problem instance from file with caching"""
        cache_dir = os.path.join(BASE_DIR, 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f'{problem_name}_distances.pkl')
        
        cust_num = 0
        text_file = os.path.join(BASE_DIR, 'data', problem_name + '.txt')
        
        print(f"Looking for file: {text_file}")
        
        parsed_data = {
            DEPART: None,
            DISTANCE_MATRIX: None,
            MAX_VEHICLE_NUMBER: None,
            VEHICLE_CAPACITY: None,
            INSTANCE_NAME: None
        }

        try:
            with io.open(text_file, 'rt', encoding='utf-8', newline='') as fo:
                for line_count, line in enumerate(fo, start=1):
                    line = line.strip()
                    if not line or line.startswith(('CUSTOMER', 'VEHICLE', 'CUST NO.', '#')):
                        continue

                    values = line.split()
                    if len(values) == 0:
                        continue

                    if line_count == 1:
                        parsed_data[INSTANCE_NAME] = line
                    elif len(values) == 2 and values[1].isdigit():
                        parsed_data[MAX_VEHICLE_NUMBER] = int(values[0])
                        parsed_data[VEHICLE_CAPACITY] = float(values[1])
                    elif len(values) >= 7:
                        cust_id = int(values[0])
                        comment = ' '.join(values[7:]) if len(values) > 7 else ''
                        if cust_id == 0:
                            parsed_data[DEPART] = {
                                COORDINATES: {
                                    X_COORD: float(values[1]),
                                    Y_COORD: float(values[2]),
                                },
                                DEMAND: float(values[3]),
                                READY_TIME: float(values[4]),
                                DUE_TIME: float(values[5]),
                                SERVICE_TIME: float(values[6]),
                                'comment': comment.strip('# ')
                            }
                        else:
                            parsed_data[f'C_{cust_id}'] = {
                                COORDINATES: {
                                    X_COORD: float(values[1]),
                                    Y_COORD: float(values[2]),
                                },
                                DEMAND: float(values[3]),
                                READY_TIME: float(values[4]),
                                DUE_TIME: float(values[5]),
                                SERVICE_TIME: float(values[6]),
                                'comment': comment.strip('# ')
                            }
                            cust_num += 1

            if not force_recalculate and os.path.exists(cache_file):
                try:
                    with open(cache_file, 'rb') as f:
                        parsed_data[DISTANCE_MATRIX] = pickle.load(f)
                    print("Loaded distance matrix from cache")
                    return parsed_data
                except:
                    print("Failed to load cached distance matrix")
            
            return parsed_data

        except Exception as e:
            print(f"Error loading problem instance: {e}")
            traceback.print_exc()
            return None

class GoogleMapsHandler:
    def __init__(self, api_key):
        self.gmaps = googlemaps.Client(key=api_key)
        self.distance_cache = {}
        self.max_workers = 10  # Paralel istek sayısı
        self.chunk_size = 25   # Her chunk'taki istek sayısı
        
    def calculate_batch_distances(self, coordinate_pairs):
        """Calculate distances for multiple pairs in parallel"""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for origin, dest in coordinate_pairs:
                if (origin, dest) not in self.distance_cache:
                    futures.append(
                        executor.submit(self.calculate_single_distance, origin, dest)
                    )
            
            for future in as_completed(futures):
                origin, dest, result = future.result()
                if result:
                    self.distance_cache[(origin, dest)] = result
    
    def calculate_single_distance(self, origin, dest):
        """Calculate distance for a single pair"""
        try:
            result = self.gmaps.distance_matrix(
                origins=[f"{origin[0]},{origin[1]}"],
                destinations=[f"{dest[0]},{dest[1]}"],
                mode="driving",
                departure_time=datetime.now()
            )
            
            if result['rows'][0]['elements'][0]['status'] == 'OK':
                distance = result['rows'][0]['elements'][0]['distance']['value'] / 1000
                duration = result['rows'][0]['elements'][0]['duration']['value'] / 60
                return origin, dest, (distance, duration)
            return origin, dest, None
            
        except Exception as e:
            print(f"Error calculating distance: {e}")
            return origin, dest, None

def create_navigation_link(route, instance_data):
    """Create Google Maps navigation link for the route"""
    base_url = "https://www.google.com/maps/dir/"
    
    depot_coord = (
        instance_data[DEPART][COORDINATES][X_COORD],
        instance_data[DEPART][COORDINATES][Y_COORD]
    )
    waypoints = [f"{depot_coord[0]},{depot_coord[1]}"]
    
    for sub_route in route:
        for customer_id in sub_route:
            customer = instance_data[f'C_{customer_id}']
            coord = (
                customer[COORDINATES][X_COORD],
                customer[COORDINATES][Y_COORD]
            )
            waypoints.append(f"{coord[0]},{coord[1]}")
    
    waypoints.append(f"{depot_coord[0]},{depot_coord[1]}")
    
    nav_url = base_url + '/'.join(waypoints)
    return nav_url
