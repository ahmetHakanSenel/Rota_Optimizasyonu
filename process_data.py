import os
import io
import pickle
import traceback
import requests
import time
import numpy as np

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
DISTANCE_MATRIX = 'distance_matrix' 


class OSRMHandler:
    def __init__(self):
        self.base_url = "http://router.project-osrm.org"
        self.elevation_api_url = "https://api.open-elevation.com/api/v1/lookup"
        self.distance_matrix = {}
        self.elevation_cache = {}
        self.timeout = 60
        self.max_retries = 3
        self._initialize_cache()
    
    def _initialize_cache(self):
        cache_dir = os.path.join(BASE_DIR, 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, 'osrm_distance_matrix.pkl')
        elevation_cache_file = os.path.join(cache_dir, 'elevation_cache.pkl')
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    self.distance_matrix = pickle.load(f)
                print("Loaded distance matrix from cache")
            except Exception as e:
                print(f"Error loading cache: {e}")
                self.distance_matrix = {}
        
        if os.path.exists(elevation_cache_file):
            try:
                with open(elevation_cache_file, 'rb') as f:
                    self.elevation_cache = pickle.load(f)
                print("Loaded elevation cache")
            except Exception as e:
                print(f"Error loading elevation cache: {e}")
                self.elevation_cache = {}
    
    def save_cache(self):
        cache_dir = os.path.join(BASE_DIR, 'cache')
        cache_file = os.path.join(cache_dir, 'osrm_distance_matrix.pkl')
        elevation_cache_file = os.path.join(cache_dir, 'elevation_cache.pkl')
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(self.distance_matrix, f)
            with open(elevation_cache_file, 'wb') as f:
                pickle.dump(self.elevation_cache, f)
            print("Saved caches")
        except Exception as e:
            print(f"Error saving cache: {e}")

    def get_elevation_profile(self, start_point, end_point, distance_interval=30):
        key = (tuple(start_point), tuple(end_point))
        if key in self.elevation_cache:
            return self.elevation_cache[key]

        try:
            # OSRM route API'sini kullanarak sürüş için rota koordinatlarını alıyoruz
            url = f"{self.base_url}/route/v1/driving/{start_point[1]},{start_point[0]};{end_point[1]},{end_point[0]}"
            params = {
                "overview": "full",
                "geometries": "geojson",
                "steps": "true"
            }
            
            response = requests.get(url, params=params, timeout=self.timeout)
            data = response.json()
            
            if data.get("code") != "Ok" or not data.get("routes"):
                # OSRM başarısız olursa hata fırlat
                error_msg = f"OSRM API başarısız oldu: {data.get('message', 'Bilinmeyen hata')}"
                print(error_msg)
                raise Exception(error_msg)
            else:
                # OSRM'den gelen rota koordinatlarını kullan
                route = data["routes"][0]
                # OSRM koordinatları [lon, lat] formatında döndürür, biz [lat, lon] kullanıyoruz
                route_coords = [(coord[1], coord[0]) for coord in route["geometry"]["coordinates"]]
                total_distance = route["distance"]
                duration = route["duration"]
                
                if total_distance < distance_interval:
                    points = [route_coords[0], route_coords[-1]]
                else:
                    # Rota üzerinde belirli aralıklarla örnekleme yap
                    num_samples = max(2, int(total_distance / distance_interval) + 1)
                    # Eşit aralıklı indeksler oluştur
                    indices = np.linspace(0, len(route_coords) - 1, num_samples).astype(int)
                    points = [route_coords[i] for i in indices]
            
            # Yükseklik verilerini al
            locations = [{'latitude': lat, 'longitude': lon} for lat, lon in points]
            response = requests.post(
                self.elevation_api_url,
                json={'locations': locations},
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                elevations = [result['elevation'] for result in data['results']]
                
                # Yükseklik profilini hesapla
                total_ascent = 0
                total_descent = 0
                
                # Her noktanın bir sonraki noktayla arasındaki farkı hesapla
                for i in range(len(elevations) - 1):
                    diff = elevations[i+1] - elevations[i]
                    if diff > 0:
                        total_ascent += diff
                    else:
                        total_descent += abs(diff)

                profile = {
                    'elevations': elevations,
                    'total_ascent': total_ascent,
                    'total_descent': total_descent,
                    'max_elevation': max(elevations),
                    'min_elevation': min(elevations),
                    'avg_elevation': sum(elevations) / len(elevations),
                    'distance_interval': distance_interval,
                    'num_samples': len(points),
                    'total_distance': total_distance,
                    'duration': duration
                }

                self.elevation_cache[key] = profile
                return profile

        except Exception as e:
            print(f'Error getting elevation data: {e}')
            return None

    def calculate_energy_cost(self, route_segment, vehicle_mass=10000):
        start_point = route_segment[0]
        end_point = route_segment[1]
        
        # Önce mesafeyi kontrol et - çok kısa mesafeler için hesaplama yapma
        distance = self.get_distance(start_point, end_point)
        if distance < 0.1:  # 100 metre altındaki mesafeler için basitleştir
            return distance * 0.1  # Basit bir yaklaşım
        
        # Rota segmenti için önbellekte anahtar oluştur
        cache_key = (f"energy_{tuple(start_point)}_{tuple(end_point)}_{vehicle_mass}")
        if hasattr(self, 'energy_cache') and cache_key in self.energy_cache:
            return self.energy_cache[cache_key]
            
        # Enerji önbelleği yoksa oluştur
        if not hasattr(self, 'energy_cache'):
            self.energy_cache = {}
        
        # Yükseklik profilini al
        elevation_profile = self.get_elevation_profile(start_point, end_point)
        if not elevation_profile:
            return distance * 0.15  # Yükseklik verisi yoksa basit bir yaklaşım kullan
        
        # Temel değerler
        route_distance = elevation_profile["total_distance"] / 1000  # km 
        
        # Araç tipi ve ağırlığına göre temel yakıt tüketimi (litre/100km)
        if vehicle_mass <= 3500:  # Hafif ticari araç
            base_consumption_per_100km = 8.0
        elif vehicle_mass <= 7500:  # Orta ağırlıkta tivari
            base_consumption_per_100km = 15.0
        elif vehicle_mass <= 16000:  # Ağır ticari
            base_consumption_per_100km = 25.0
        else:  
            base_consumption_per_100km = 35.0
        
        base_consumption = base_consumption_per_100km / 100
        base_fuel = route_distance * base_consumption
        
        # Yükseklik verisi varsa ve yeterli sayıda nokta içeriyorsa
        if 'elevations' in elevation_profile and len(elevation_profile['elevations']) > 1:
            elevations = elevation_profile['elevations']
            total_segment_fuel = 0
            
            # Toplam mesafeyi segment sayısına bölerek yaklaşık segment mesafelerini hesapla
            num_segments = len(elevations) - 1
            if num_segments > 0:
                segment_distance = route_distance / num_segments
                
                # Optimizasyon: Çok fazla segment varsa örnekleme yap
                if num_segments > 10:
                    sample_indices = np.linspace(0, len(elevations)-1, 10, dtype=int)
                    elevations = [elevations[i] for i in sample_indices]
                    num_segments = len(elevations) - 1
                    segment_distance = route_distance / num_segments
                
                # Her segment için yakıt tüketimini hesapla
                for i in range(len(elevations) - 1):
                    segment_elevation_diff = elevations[i+1] - elevations[i]
                    
                    # Segment eğimini hesapla (m/km)
                    segment_gradient = abs(segment_elevation_diff) / segment_distance if segment_distance > 0 else 0
                    
                    # Segment için temel yakıt tüketimi
                    segment_base_fuel = segment_distance * base_consumption
                    
                    # Yokuş yukarı ek tüketim
                    if segment_elevation_diff > 0:  # Yokuş yukarı
                        # Eğim kategorilerini basitleştir
                        if segment_gradient <= 50:  # Hafif/orta yokuş
                            ascent_factor = 0.1 * (segment_gradient / 25)
                        else:  # Dik yokuş
                            ascent_factor = 0.2 + 0.1 * min(1, (segment_gradient - 50) / 50)
                        
                        # Ağırlık etkisi - basitleştirilmiş
                        weight_multiplier = max(1.0, vehicle_mass / 7500)
                        segment_fuel = segment_base_fuel * (1 + ascent_factor * weight_multiplier)
                    
                    # Yokuş aşağı yakıt tasarrufu
                    elif segment_elevation_diff < 0:  # Yokuş aşağı
                        # Basitleştirilmiş iniş faktörü
                        descent_factor = min(0.1, 0.05 * (segment_gradient / 40))
                        segment_fuel = segment_base_fuel * (1 - descent_factor)
                    
                    # Düz yol
                    else:
                        segment_fuel = segment_base_fuel
                    
                    total_segment_fuel += segment_fuel
                
                # Sonucu önbelleğe al
                result = max(total_segment_fuel, route_distance * (base_consumption * 0.5))
                self.energy_cache[cache_key] = result
                return result
        
        # Yükseklik verisi yoksa veya yetersizse basit hesaplama yap
        result = route_distance * base_consumption
        self.energy_cache[cache_key] = result
        return result

    def calculate_route_segment_cost(self, origin, dest, vehicle_mass=10000):
        # Mesafe maliyeti
        distance = self.get_distance(origin, dest)
        if distance == float('inf'):
            return float('inf')
        
        # Yakıt tüketimi (litre)
        fuel_consumption = self.calculate_energy_cost([origin, dest], vehicle_mass)
        if fuel_consumption == float('inf'):
            return float('inf')
        
        total_cost = distance + fuel_consumption
        return total_cost

    def get_distance(self, origin, dest):
        key = (tuple(origin), tuple(dest))
        reverse_key = (tuple(dest), tuple(origin))
        
        if key in self.distance_matrix:
            return self.distance_matrix[key]
        if reverse_key in self.distance_matrix:
            return self.distance_matrix[reverse_key]
        
        print(f"Warning: Distance not found in cache for {key}")
        return float('inf')
    
    def get_route_cost(self, origin, dest, vehicle_mass=10000):
        """
        İki nokta arasındaki toplam rota maliyetini hesaplar.
        Bu maliyet, mesafe ve yükseklik profiline dayalı enerji tüketimini içerir.
        
        Args:
            origin: Başlangıç noktası (lat, lon)
            dest: Varış noktası (lat, lon)
            vehicle_mass: Araç kütlesi (kg)
            
        Returns:
            Toplam rota maliyeti (mesafe + enerji maliyeti)
        """
        return self.calculate_route_segment_cost(origin, dest, vehicle_mass)
    
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
