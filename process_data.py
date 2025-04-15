import os
import io
import pickle
import traceback
import requests
import time
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
                # OSRM koordinatları [lon, lat] formatında döndürür, [lat, lon] kullanıyoruz
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
        import math
        import numpy as np
        
        start_point = route_segment[0]
        end_point = route_segment[1]
        
        #mesafeyi kontrolü - çok kısa mesafeler için hesaplama yok
        distance = self.get_distance(start_point, end_point)
        if distance < 0.1:  
            return distance * 0.1 
        
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
        
        # Segmentlere bölünmüş yükseklik profilini kullan
        elevations = elevation_profile['elevations']
        
        # Temel araç ağırlığı ve yük hesaplaması
        base_vehicle_mass = 2000  # temel araç ağırlığı (kg)
        payload = max(0, vehicle_mass - base_vehicle_mass)  # kg cinsinden yük
        route_load = payload / 10  # desiye çevir (yaklaşık olarak)
        
        # Yük faktörü - Yük arttıkça enerji tüketimi artar
        load_factor = 1.0 + 0.4 * (route_load / 500) ** 1.15
        
        # Her segment için enerji maliyetini hesapla
        total_energy_cost = 0
        
        # Toplam mesafeyi segmentlere böl
        segment_distance = distance * 1000 / (len(elevations) - 1)  # metre cinsinden her segment için mesafe
        
        for i in range(len(elevations) - 1):
            # Segment yükseklik farkı (metre)
            elevation_diff = elevations[i+1] - elevations[i]
            
            # Segment eğimi (yüzde)
            gradient_percent = (elevation_diff / segment_distance) * 100
            
            # Segment için enerji faktörü hesapla
            segment_energy_factor = 0
            
            # Eğim faktörü
            if gradient_percent > 0:  # Yokuş yukarı
                
                # Üstel artış modeli (eğim arttıkça enerji tüketimi üstel olarak artıyor)
                base_gradient_effect = 0.09  # %1 eğim başına yaklaşık %9 artış 
                exp_factor = 1.3  # Üstel artışı kontrol eder 
                
                # Yük her %10 arttığında, yokuş yukarı yakıt tüketimi yaklaşık %8-12 daha fazla artıyor
                yuk_etkisi = 1.0 + (route_load / 500) * 0.3  # Yük etkisi faktörü
                
                # Üstel artış formülü
                gradient_etkisi = (gradient_percent ** exp_factor) * base_gradient_effect * yuk_etkisi
                
                # Eğim faktörü, artışı temsil eder
                gradient_factor = 1.0 + gradient_etkisi
                
                # Gerçekçi bir üst sınır
                gradient_factor = min(gradient_factor, 5.0)  # Maksimum 5 kat artış
                
                segment_energy_factor = gradient_factor
            else:  # Yokuş aşağı veya düz

                optimum_egim = 3.0  
                max_egim = 8.0  # Bu değerden sonra verimlilik azalır
                

                max_benefit = 0.5  # Maksimum %50 tasarruf 
                min_benefit = 0.1  # Çok dik inişlerde minimum tasarruf
                
                abs_gradient = abs(gradient_percent)
                
                # Yükün kazancı azaltıcı etkisi 
                yuk_tasarruf_azalma = (route_load / 500) * 0.1
                max_benefit = max(0.2, max_benefit - yuk_tasarruf_azalma)  # Yük arttıkça maksimum tasarruf azalır
                
                if abs_gradient < 0.5:  # Neredeyse düz
                    gradient_factor = 1.0
                elif abs_gradient <= optimum_egim:
                    # Optimum eğime kadar kazanç artar
                    benefit_ratio = (abs_gradient / optimum_egim) * max_benefit
                    gradient_factor = 1.0 - benefit_ratio
                else:
                    # Optimum eğimden sonra kazanç azalır
                    if abs_gradient >= max_egim:
                        # Çok dik inişlerde minimum kazanç
                        gradient_factor = 1.0 - min_benefit
                    else:
                        # Optimum ile max arasında kademeli azalma
                        progress = (abs_gradient - optimum_egim) / (max_egim - optimum_egim)
                        benefit = max_benefit - ((max_benefit - min_benefit) * progress)
                        gradient_factor = 1.0 - benefit
                
                segment_energy_factor = gradient_factor
            
            # Segment için toplam enerji faktörü (yük ve eğim etkisi)
            total_factor = segment_energy_factor * load_factor
            
            # Segment için enerji maliyeti (km başına)
            segment_energy_cost = (segment_distance / 1000) * total_factor
            
            # Toplam enerji maliyetine ekle
            total_energy_cost += segment_energy_cost
        
        # Sonucu önbelleğe al
        self.energy_cache[cache_key] = total_energy_cost
        
        return total_energy_cost

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

    def get_route_details(self, origin, dest):

        # Önbellekte bir anahtar oluştur
        cache_key = f"route_{tuple(origin)}_{tuple(dest)}"
        if hasattr(self, 'route_cache') and cache_key in self.route_cache:
            return self.route_cache[cache_key]
        
        # Önbellek yoksa oluştur
        if not hasattr(self, 'route_cache'):
            self.route_cache = {}
        
        # OSRM API'sine istek yap - tam rota verisini al
        try:
            # origin ve dest noktalarını lon,lat formatına çevir (OSRM için)
            origin_str = f"{origin[1]},{origin[0]}"
            dest_str = f"{dest[1]},{dest[0]}"
            
            # OSRM route API'sine istek yap
            url = f"{self.base_url}/route/v1/driving/{origin_str};{dest_str}"
            params = {
                "overview": "full",  # Tam rota geometrisi iste
                "geometries": "geojson",  # GeoJSON formatında geometri
                "steps": "true",  # Rota adımlarını dahil et
                "annotations": "true"  # Ekstra açıklamalar (mesafe, süre vs.)
            }
            
            print(f"Requesting route from OSRM: {url} with params: {params}")
            
            # 3 deneme yapacak şekilde retry logic ekle
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, params=params, timeout=self.timeout)
                    
                    # Log status code explicitly
                    print(f"OSRM Response Status (attempt {attempt+1}/{max_retries}): {response.status_code}")
                    
                    data = response.json()
                    
                    # Check response status code *before* checking data content
                    if response.status_code != 200:
                        error_msg = data.get("message", f"HTTP Status {response.status_code}")
                        print(f"OSRM API HTTP error (attempt {attempt+1}/{max_retries}): {error_msg}")
                        if attempt < max_retries - 1:
                            print(f"Retrying in 1 second...")
                            time.sleep(1)
                            continue
                        return None # Failed after retries

                    # Check OSRM-specific status code
                    if data.get("code") != "Ok":
                        error_msg = data.get("message", "Unknown OSRM error code")
                        print(f"OSRM API specific error (attempt {attempt+1}/{max_retries}): {error_msg} (Code: {data.get('code')})")
                        if attempt < max_retries - 1:
                            print(f"Retrying in 1 second...")
                            time.sleep(1)
                            continue
                        return None # Failed after retries
                    
                    # Rota bilgilerini çıkart
                    if "routes" in data and len(data["routes"]) > 0:
                        route = data["routes"][0]
                        
                        # GeoJSON geometrisi içinden koordinatları al
                        if "geometry" in route and "coordinates" in route["geometry"]:
                            coordinates = route["geometry"]["coordinates"]
                            distance = route["distance"] / 1000  # metre -> km
                            duration = route["duration"] / 60    # saniye -> dakika
                            
                            result = {
                                "coordinates": coordinates,  # [[lon, lat], [lon, lat], ...]
                                "distance": distance,        # km cinsinden
                                "duration": duration,        # dakika cinsinden
                                "success": True
                            }
                            
                            # Önbelleğe ekle
                            self.route_cache[cache_key] = result
                            print(f"Successfully got route with {len(coordinates)} points, distance: {distance:.2f} km")
                            return result
                        else:
                            print(f"No geometry found in OSRM response: {route.keys()}")
                    else:
                        print(f"No routes found in OSRM response: {data.keys()}")
                    
                    # Geçerli yanıt ama gerekli veriler yok
                    return None
                    
                except requests.RequestException as e:
                    print(f"Request error (attempt {attempt+1}/{max_retries}): {str(e)}")
                    if attempt < max_retries - 1:
                        print(f"Retrying in 1 second...")
                        time.sleep(1)
                    else:
                        return None
                except ValueError as e:
                    print(f"JSON parsing error: {str(e)}")
                    return None
                except Exception as e:
                    print(f"Unexpected error getting route details: {str(e)}")
                    return None
            
            # Tüm denemeler başarısız
            return None
        
        except Exception as e:
            print(f"Error in get_route_details: {str(e)}")
            traceback.print_exc()
            return None

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
