import os
import io
from datetime import datetime
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import requests
import polyline
import time

# Gerekli kütüphanelerin import edilmesi
import os  # Dosya işlemleri için
import io  # Dosya okuma/yazma işlemleri için
from datetime import datetime  # Zaman işlemleri için
import pickle  # Cache verilerini kaydetmek/yüklemek için
from concurrent.futures import ThreadPoolExecutor, as_completed  # Paralel işlemler için
import traceback  # Hata ayıklama için
import requests  # HTTP istekleri için
import polyline  # OSRM rota kodlaması için
import time  # Zaman gecikmesi ve ölçümü için

# Proje kök dizininin belirlenmesi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Sabit değişkenlerin tanımlanması
X_COORD = 'x'  # X koordinatı için anahtar
Y_COORD = 'y'  # Y koordinatı için anahtar
COORDINATES = 'coordinates'  # Koordinatlar için anahtar
INSTANCE_NAME = 'instance_name'  # Problem örneği adı için anahtar
MAX_VEHICLE_NUMBER = 'max_vehicle_number'  # Maksimum araç sayısı için anahtar
VEHICLE_CAPACITY = 'vehicle_capacity'  # Araç kapasitesi için anahtar
DEPART = 'depart'  # Depo noktası için anahtar
DEMAND = 'demand'  # Talep miktarı için anahtar
READY_TIME = 'ready_time'  # Hazır olma zamanı için anahtar
DUE_TIME = 'due_time'  # Son teslim zamanı için anahtar
SERVICE_TIME = 'service_time'  # Servis süresi için anahtar
DISTANCE_MATRIX = 'distance_matrix'  # Mesafe matrisi için anahtar

class ProblemInstance:
    _instance = None  # Singleton pattern için instance değişkeni
    _data = None  # Problem verilerini tutacak değişken
    
    def __new__(cls, problem_name=None, force_recalculate=False):
        # Singleton pattern implementasyonu
        if cls._instance is None:
            cls._instance = super(ProblemInstance, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, problem_name=None, force_recalculate=False):
        # Problem verilerini yükleme
        if self._data is None and problem_name:
            self._data = self._load_problem_instance(problem_name, force_recalculate)
    
    def get_data(self):
        # Problem verilerini döndürme
        return self._data
    
    def _load_problem_instance(self, problem_name, force_recalculate=False):
        """Problem verilerini dosyadan yükleme"""
        cache_dir = os.path.join(BASE_DIR, 'cache')  # Cache dizini
        os.makedirs(cache_dir, exist_ok=True)  # Cache dizinini oluştur
        cache_file = os.path.join(cache_dir, f'{problem_name}_distances.pkl')  # Cache dosyası
        
        cust_num = 0  # Müşteri sayısı sayacı
        text_file = os.path.join(BASE_DIR, 'data', problem_name + '.txt')  # Veri dosyası
        
        print(f"Looking for file: {text_file}")
        
        parsed_data = {  # Ayrıştırılmış verileri tutacak sözlük
            DEPART: None,
            DISTANCE_MATRIX: None,
            MAX_VEHICLE_NUMBER: None,
            VEHICLE_CAPACITY: None,
            INSTANCE_NAME: None
        }

        try:
            # Veri dosyasını okuma ve ayrıştırma
            with io.open(text_file, 'rt', encoding='utf-8', newline='') as fo:
                for line_count, line in enumerate(fo, start=1):
                    line = line.strip()
                    if not line or line.startswith(('CUSTOMER', 'VEHICLE', 'CUST NO.', '#')):
                        continue

                    values = line.split()
                    if len(values) == 0:
                        continue

                    if line_count == 1:  # İlk satır: problem adı
                        parsed_data[INSTANCE_NAME] = line
                    elif len(values) == 2 and values[1].isdigit():  # Araç bilgileri
                        parsed_data[MAX_VEHICLE_NUMBER] = int(values[0])
                        parsed_data[VEHICLE_CAPACITY] = float(values[1])
                    elif len(values) >= 7:  # Müşteri/depo bilgileri
                        cust_id = int(values[0])
                        comment = ' '.join(values[7:]) if len(values) > 7 else ''
                        if cust_id == 0:  # Depo noktası
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
                        else:  # Müşteri noktası
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

            # Cache'den mesafe matrisini yükleme
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
        self.base_url = "http://router.project-osrm.org"  # OSRM API URL'i
        self.distance_matrix = {}  # Mesafe matrisini tutacak sözlük
        self.timeout = 30  # API istek zaman aşımı süresi
        self.max_retries = 3  # Maksimum yeniden deneme sayısı
        self._initialize_cache()  # Cache'i başlat
    
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
    
    def get_distance(self, origin, dest):
        """İki nokta arasındaki mesafeyi hesaplama"""
        key = (tuple(origin), tuple(dest))  # Cache anahtarı
        
        # Önce cache'e bak
        if key in self.distance_matrix:
            return self.distance_matrix[key]
        
        # Birden fazla deneme yap
        for attempt in range(self.max_retries):
            try:
                # OSRM API'sine istek at
                url = f"{self.base_url}/route/v1/driving/{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
                params = {
                    "overview": "false",  # Rota geometrisi istenmiyor
                    "alternatives": "false",  # Alternatif rotalar istenmiyor
                    "steps": "false"  # Adım adım talimatlar istenmiyor
                }
                
                response = requests.get(url, params=params, timeout=self.timeout)
                data = response.json()
                
                # Başarılı yanıt kontrolü
                if response.status_code == 200 and data.get("code") == "Ok" and "routes" in data and len(data["routes"]) > 0:
                    # Mesafeyi kilometre cinsine çevir
                    distance = data["routes"][0]["distance"] / 1000
                    self.distance_matrix[key] = distance
                    
                    # Ters yönü de cache'le
                    reverse_key = (tuple(dest), tuple(origin))
                    self.distance_matrix[reverse_key] = distance
                    
                    # Periyodik olarak cache'i kaydet
                    if len(self.distance_matrix) % 10 == 0:
                        self.save_cache()
                    
                    return distance
                
                print(f"Invalid response from OSRM (attempt {attempt + 1}/{self.max_retries}): {data}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)  # Yeniden denemeden önce bekle
            
            except requests.Timeout:
                print(f"Timeout error (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(1)
            except requests.RequestException as e:
                print(f"Network error (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)
            except Exception as e:
                print(f"Error calculating distance with OSRM: {str(e)}")
                break
        
        return float('inf')  # Başarısız olursa sonsuz mesafe döndür

def create_navigation_link(route, instance_data):
    """GraphHopper navigasyon linki oluşturma"""
    base_url = "https://graphhopper.com/maps/?"  # GraphHopper base URL
    
    # Depo koordinatları
    depot_coord = (
        instance_data[DEPART][COORDINATES][X_COORD],
        instance_data[DEPART][COORDINATES][Y_COORD]
    )
    
    # GraphHopper format: point=lat,lon&point=lat,lon...
    points = [f"point={depot_coord[0]},{depot_coord[1]}"]  # Başlangıç noktası
    
    # Rota üzerindeki noktaları ekle
    for sub_route in route:
        for customer_id in sub_route:
            customer = instance_data[f'C_{customer_id}']
            coord = (
                customer[COORDINATES][X_COORD],
                customer[COORDINATES][Y_COORD]
            )
            points.append(f"point={coord[0]},{coord[1]}")
    
    # Son nokta olarak depoya dönüş
    points.append(f"point={depot_coord[0]},{depot_coord[1]}")
    
    # GraphHopper parametreleri
    params = [
        "profile=car",  # Araç tipi
        "layer=OpenStreetMap"  # Harita katmanı
    ]
    
    # URL oluştur
    nav_url = base_url + "&".join(points + params)
    return nav_url
