import os
import io
import pickle
import traceback
import requests
import time

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
        """Problem verilerini dosyadan yükleme"""
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

class OSRMHandler:
    def __init__(self):
        self.base_url = "http://router.project-osrm.org"
        self.distance_matrix = {}
        self.timeout = 60
        self.max_retries = 3
        self._initialize_cache()
    
    def _initialize_cache(self):
        """Cache dosyasını yükleme"""
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
        """Cache'i kaydetme"""
        cache_file = os.path.join(BASE_DIR, 'cache', 'osrm_distance_matrix.pkl')
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(self.distance_matrix, f)
            print("Saved distance matrix to cache")
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def precompute_distances(self, instance):
        """Tüm mesafeleri OSRM table servisi ile tek seferde hesapla"""
        print("\nPrecomputing all distances using OSRM table service...")
        
        # Tüm noktaları topla
        all_points = []
        # Önce depo noktası
        depot = (instance[DEPART][COORDINATES][X_COORD], 
                instance[DEPART][COORDINATES][Y_COORD])
        all_points.append(depot)
        
        # Müşteri noktaları
        customer_points = []
        i = 1
        while True:
            customer_key = f'C_{i}'
            if customer_key not in instance:
                break
            customer = instance[customer_key]
            point = (customer[COORDINATES][X_COORD],
                    customer[COORDINATES][Y_COORD])
            customer_points.append(point)
            all_points.append(point)
            i += 1
        
        print(f"Found {len(customer_points)} customer points")
        
        # OSRM table servisi için koordinatları hazırla
        coordinates = [f"{p[1]},{p[0]}" for p in all_points]  # OSRM lon,lat formatı
        
        # Table servisi için istek at
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
                    
                    # Mesafe matrisini işle ve cache'le
                    distances = data["distances"]
                    for i, origin in enumerate(all_points):
                        for j, dest in enumerate(all_points):
                            if i != j:  # Aynı nokta değilse
                                distance = distances[i][j] / 1000  # metre -> kilometre
                                self.distance_matrix[(tuple(origin), tuple(dest))] = distance
                    
                    print(f"Cached {len(self.distance_matrix)} distances")
                    self.save_cache()
                    return True
                
                print(f"Invalid response from OSRM (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2)  # Daha uzun bekleme süresi
            
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
    
    def get_distance(self, origin, dest):
        """Cache'den mesafe getir"""
        key = (tuple(origin), tuple(dest))
        reverse_key = (tuple(dest), tuple(origin))
        
        # Önce direkt keyi kontrol et
        if key in self.distance_matrix:
            return self.distance_matrix[key]
        # Sonra ters keyi kontrol et
        if reverse_key in self.distance_matrix:
            return self.distance_matrix[reverse_key]
        
        print(f"Warning: Distance not found in cache for {key}")
        return float('inf')

def create_navigation_link(route, instance_data):
    """GraphHopper navigasyon linki oluşturma"""
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
    
    # URL oluştur
    nav_url = base_url + "&".join(points + params)
    return nav_url
