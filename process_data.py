import os
import io
import pickle
import traceback
import requests
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Sabit değişkenler
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
        cache_dir = os.path.join(BASE_DIR, 'cache')  
        os.makedirs(cache_dir, exist_ok=True) 
        cache_file = os.path.join(cache_dir, f'{problem_name}_distances.pkl') 
        
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
                    if not values:
                        continue

                    if line_count == 1:  
                        parsed_data[INSTANCE_NAME] = line
                    elif len(values) == 2 and values[1].isdigit(): 
                        parsed_data[MAX_VEHICLE_NUMBER] = int(values[0])
                        parsed_data[VEHICLE_CAPACITY] = float(values[1])
                    elif len(values) >= 7:  
                        cust_id = int(values[0])
                        customer_data = {
                            COORDINATES: {
                                X_COORD: float(values[1]),
                                Y_COORD: float(values[2]),
                            },
                            DEMAND: float(values[3]),
                            READY_TIME: float(values[4]),
                            DUE_TIME: float(values[5]),
                            SERVICE_TIME: float(values[6]),
                            'comment': ' '.join(values[7:]).strip('# ') if len(values) > 7 else ''
                        }
                        
                        if cust_id == 0:
                            parsed_data[DEPART] = customer_data
                        else:
                            parsed_data[f'C_{cust_id}'] = customer_data

            if not force_recalculate and os.path.exists(cache_file):
                try:
                    with open(cache_file, 'rb') as f:
                        parsed_data[DISTANCE_MATRIX] = pickle.load(f)
                    print("Loaded distance matrix from cache")
                except:
                    print("Failed to load cached distance matrix")
            
            return parsed_data

        except Exception as e:
            print(f"Error loading problem instance: {e}")
            traceback.print_exc()
            return None

class OSRMHandler:
    def __init__(self):
        self.base_url = "http://router.project-osrm.org"
        self.distance_matrix = {}
        self.timeout = 60
        self.max_retries = 3
        self._initialize_cache()
    
    def _initialize_cache(self):
        cache_dir = os.path.join(BASE_DIR, 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, 'osrm_distance_matrix.pkl')
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    self.distance_matrix = pickle.load(f)
                print("Loaded distance matrix from cache")
            except Exception as e:
                print(f"Error loading cache: {e}")
                self.distance_matrix = {}
    
    def save_cache(self):
        cache_file = os.path.join(BASE_DIR, 'cache', 'osrm_distance_matrix.pkl')
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(self.distance_matrix, f)
            print("Saved distance matrix to cache")
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def get_distance(self, origin, dest):
        key = (tuple(origin), tuple(dest))
        reverse_key = (tuple(dest), tuple(origin))
        
        if key in self.distance_matrix:
            return self.distance_matrix[key]
        if reverse_key in self.distance_matrix:
            return self.distance_matrix[reverse_key]
        
        print(f"Warning: Distance not found in cache for {key}")
        return float('inf')
    
    def precompute_distances(self, instance):
        print("\nPrecomputing all distances using OSRM table service...")
        
        all_points = []
        depot = (instance[DEPART][COORDINATES][X_COORD], 
                instance[DEPART][COORDINATES][Y_COORD])
        all_points.append(depot)
        
        i = 1
        while True:
            customer_key = f'C_{i}'
            if customer_key not in instance:
                break
            customer = instance[customer_key]
            point = (customer[COORDINATES][X_COORD],
                    customer[COORDINATES][Y_COORD])
            all_points.append(point)
            i += 1
        
        print(f"Found {len(all_points)-1} customer points")
        coordinates = [f"{p[1]},{p[0]}" for p in all_points]
        
        for attempt in range(self.max_retries):
            try:
                url = f"{self.base_url}/table/v1/driving/{';'.join(coordinates)}"
                params = {
                    "annotations": "distance",
                    "sources": "all",
                    "destinations": "all"
                }
                
                print("Requesting distance matrix from OSRM...")
                response = requests.get(url, params=params, timeout=self.timeout)
                data = response.json()
                
                if response.status_code == 200 and "distances" in data:
                    print("Successfully received distance matrix")
                    
                    distances = data["distances"]
                    for i, origin in enumerate(all_points):
                        for j, dest in enumerate(all_points):
                            if i != j:
                                distance = distances[i][j] / 1000
                                self.distance_matrix[(tuple(origin), tuple(dest))] = distance
                    
                    print(f"Cached {len(self.distance_matrix)} distances")
                    self.save_cache()
                    return True
                
                print(f"Invalid response from OSRM (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            
            except requests.Timeout:
                print(f"Timeout error (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            except requests.RequestException as e:
                print(f"Network error (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            except Exception as e:
                print(f"Error calculating distance matrix: {str(e)}")
                break
        
        print("Failed to compute distance matrix")
        return False

def create_navigation_link(route, instance_data):
    base_url = "https://graphhopper.com/maps/?" 
    
    depot_coord = (
        instance_data[DEPART][COORDINATES][X_COORD],
        instance_data[DEPART][COORDINATES][Y_COORD]
    )
    
    points = [f"point={depot_coord[0]},{depot_coord[1]}"]
    
    for sub_route in route:
        for customer_id in sub_route:
            customer = instance_data[f'C_{customer_id}']
            coord = (
                customer[COORDINATES][X_COORD],
                customer[COORDINATES][Y_COORD]
            )
            points.append(f"point={coord[0]},{coord[1]}")
    
    points.append(f"point={depot_coord[0]},{depot_coord[1]}")
    
    params = [
        "profile=car",
        "layer=Omniscale"
    ]
    
    return base_url + "&".join(points + params)
