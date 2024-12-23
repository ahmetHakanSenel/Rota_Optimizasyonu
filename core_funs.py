import random
import operator
import math
import collections
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from deap import base, creator, tools # type: ignore
from process_data import *


def create_route_from_ind(individual, data):
    """Bireyi araç rotalarına dönüştürme"""
    vehicle_capacity = data[VEHICLE_CAPACITY]  # Araç kapasitesi
    route = []  # Tüm rotaları tutacak liste
    sub_route = []  # Tek bir aracın rotası
    vehicle_load = vehicle_capacity  # Mevcut araç yükü
    
    i = 0
    while i < len(individual):
        current_customer = individual[i]  # Mevcut müşteri
        current_demand = data[F'C_{current_customer}'][DEMAND]  # Müşterinin talebi
        
        if vehicle_load >= current_demand:  # Araç kapasitesi yeterliyse
            if i + 1 < len(individual):  # Sonraki müşteri varsa
                next_customer = individual[i + 1]  # Sonraki müşteri
                next_demand = data[F'C_{next_customer}'][DEMAND]  # Sonraki müşterinin talebi
                remaining_after_current = vehicle_load - current_demand  # Kalan kapasite
                
                if remaining_after_current >= next_demand:  # Sonraki müşteri için de yer varsa
                    sub_route.append(current_customer)  # Müşteriyi rotaya ekle
                    vehicle_load -= current_demand  # Kapasiteyi güncelle
                    i += 1
                else:  # Sonraki müşteri için yer yoksa
                    sub_route.append(current_customer)  # Son müşteriyi ekle
                    route.append(sub_route)  # Alt rotayı tamamla
                    sub_route = []  # Yeni alt rota başlat
                    vehicle_load = vehicle_capacity  # Kapasiteyi sıfırla
                    i += 1
            else:  # Son müşteriyse
                sub_route.append(current_customer)  # Müşteriyi ekle
                route.append(sub_route)  # Alt rotayı tamamla
                break
        else:  # Araç kapasitesi yetersizse
            if sub_route:  # Mevcut alt rota varsa
                route.append(sub_route)  # Alt rotayı tamamla
                sub_route = []  # Yeni alt rota başlat
            vehicle_load = vehicle_capacity  # Kapasiteyi sıfırla

    if sub_route and sub_route not in route:  # Kalan müşteriler varsa
        route.append(sub_route)  # Son alt rotayı ekle
        
    return route


def calculate_fitness(individual, data):
    transport_cost = 8.0  
    vehicle_setup_cost = 50.0 

    route = create_route_from_ind(individual, data)
    total_cost = 999999
    fitness = 0
    max_vehicles_count = data[MAX_VEHICLE_NUMBER]

    # checking if we have enough vehicles
    if len(route) <= max_vehicles_count:
        total_cost = 0
        for sub_route in route:
            sub_route_distance = 0
            previous_cust_id = 0
            for cust_id in sub_route:
                # Calculate section distance
                distance = data[DISTANCE_MATRIX][previous_cust_id][cust_id]
                # Update sub-route distance
                sub_route_distance += distance

                # Update last customer ID
                previous_cust_id = cust_id

            # Calculate transport cost
            distance_depot = data[DISTANCE_MATRIX][previous_cust_id][0]
            sub_route_distance += distance_depot
            sub_route_transport_cost = vehicle_setup_cost + transport_cost * sub_route_distance
            # Obtain sub-route cost
            sub_route_cost = sub_route_transport_cost
            # Update total cost
            total_cost += sub_route_cost

    # Handle the case where total_cost is zero
    if total_cost == 0:
        fitness = 0  # or some other appropriate value
    else:
        fitness = 100000.0 / total_cost  # Ensure fitness is inversely related to cost

    return fitness, total_cost


# The initialization consist in generating a random position and a random speed for a particle.
# The next function creates a particle and initializes its attributes,
# except for the attribute best, which will be set only after evaluation
def generate_particle(size, s_min, s_max):
    """Generate a particle with speed limits"""
    # Create initial position
    position = random.sample(range(1, size + 1), size)
    part = creator.Particle(position)
    
    # Initialize speed
    part.speed = [random.uniform(s_min, s_max) for _ in range(size)]
    part.smin = s_min
    part.smax = s_max
    
    # Initialize best position
    part.best = creator.Particle(position[:])  # Create a copy of current position
    
    return part


def remove_duplicates(vals):
    duplic = [item for item, count in collections.Counter(vals).items() if count > 1]
    uniq_part = []
    offset = 0.001
    count = [1] * len(duplic)
    for val in vals:
        if val in duplic:
            ind = duplic.index(val)
            val += offset * count[ind]
            count[ind] += 1
        uniq_part.append(val)

    return uniq_part


# Change floats to integers and deal with duplicates
def validate_particle(particle):
    unique_part = remove_duplicates(particle)
    sorted_asc = sorted(unique_part, key=float)
    validated_part = []

    if len(sorted_asc) > len(set(sorted_asc)):
        print("problem")

    for val in unique_part:
        index = sorted_asc.index(val)
        validated_part.append((index + 1))

    return validated_part



def update_particle(part, best, phi1, phi2):
    """Update particle position and speed"""
    # Initialize best if not already set
    if part.best is None:
        part.best = creator.Particle(part[:])
        part.best.fitness = part.fitness
    
    u1 = (random.uniform(0, phi1) for _ in range(len(part)))
    u2 = (random.uniform(0, phi2) for _ in range(len(part)))
    
    v_u1 = map(operator.mul, u1, map(operator.sub, part.best, part))
    v_u2 = map(operator.mul, u2, map(operator.sub, best, part))
    
    part.speed = list(map(operator.add, part.speed, map(operator.add, v_u1, v_u2)))
    
    # Apply speed limits
    for i, speed in enumerate(part.speed):
        if abs(speed) < part.smin:
            part.speed[i] = math.copysign(part.smin, speed)
        elif abs(speed) > part.smax:
            part.speed[i] = math.copysign(part.smax, speed)
    
    # Update position
    position = list(map(operator.add, part, part.speed))
    part[:] = validate_particle(position)

class TabuList:
    def __init__(self, max_size=50):
        self.max_size = max_size
        self.list = collections.deque(maxlen=max_size)
        self.frequency = {}  # Çözüm frekansını takip et
        self.aspiration_criteria = float('-inf')  # En iyi çözümün fitness değeri
        
    def add(self, solution, fitness=None):
        """Add solution to tabu list with its fitness"""
        solution_tuple = tuple(solution)
        self.list.append(solution_tuple)
        self.frequency[solution_tuple] = self.frequency.get(solution_tuple, 0) + 1
        
        # Aspiration kriterini güncelle
        if fitness and fitness > self.aspiration_criteria:
            self.aspiration_criteria = fitness
        
    def contains(self, solution, fitness=None):
        """Check if solution is in tabu list with aspiration criteria"""
        solution_tuple = tuple(solution)
        
        # Aspiration kriteri: Eğer çözüm şimdiye kadarki en iyiden daha iyiyse, 
        # tabu listesinde olsa bile kabul et
        if fitness and fitness > self.aspiration_criteria:
            return False
            
        # Frekansa dayalı dinamik threshold
        threshold = 0.95 - (0.05 * self.frequency.get(solution_tuple, 0))
        threshold = max(0.7, threshold)  # Alt limit
        
        return any(self._similar_solutions(solution, tabu_sol, threshold) 
                  for tabu_sol in self.list)
    
    def clear(self):
        """Clear the tabu list"""
        self.list.clear()
        self.frequency.clear()
    
    def _similar_solutions(self, sol1, sol2, threshold):
        """Check if solutions are similar"""
        if isinstance(sol2, tuple):
            sol2 = list(sol2)
        return sum(a == b for a, b in zip(sol1, sol2)) / len(sol1) > threshold

def generate_neighbors(solution, method="swap", num_neighbors=5):
    """İyileştirilmiş komşu üretimi"""
    neighbors = []
    size = len(solution)
    
    # Dinamik segment boyutları
    segment_size = max(2, min(5, size // 8))
    
    for _ in range(num_neighbors):
        neighbor = solution.copy()
        
        if method == "swap":
            # Akıllı nokta seçimi - yakın noktaları tercih et
            points = random.sample(range(size), min(4, size))
            points.sort()  # Noktaları sırala
            for i in range(len(points)-1):
                neighbor[points[i]], neighbor[points[i+1]] = neighbor[points[i+1]], neighbor[points[i]]
                
        elif method == "insert":
            # Blok taşıma - ardışık noktaları birlikte taşı
            block_size = random.randint(1, 3)
            i = random.randint(0, size - block_size)
            j = random.randint(0, size - block_size)
            block = neighbor[i:i+block_size]
            del neighbor[i:i+block_size]
            neighbor[j:j] = block
            
        # ... diğer metodlar benzer şekilde iyileştirilebilir
        
        neighbors.append(neighbor)
    
    return neighbors

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Gerçek yol mesafelerini kullanarak çözümü değerlendir"""
    total_distance = 0  # Toplam mesafe
    previous_point = (  # Başlangıç noktası (depo)
        instance[DEPART][COORDINATES][X_COORD],
        instance[DEPART][COORDINATES][Y_COORD]
    )
    
    try:
        # Ardışık noktalar arası mesafeleri hesapla
        for customer_id in solution:
            current_point = (  # Mevcut müşteri koordinatları
                instance[f'C_{customer_id}'][COORDINATES][X_COORD],
                instance[f'C_{customer_id}'][COORDINATES][Y_COORD]
            )
            
            # OSRM'den mesafeyi al
            leg_distance = map_handler.get_distance(previous_point, current_point)
            if leg_distance == float('inf'):  # Mesafe hesaplanamazsa
                return float('inf')
            
            total_distance += leg_distance  # Toplam mesafeye ekle
            previous_point = current_point  # Sonraki hesaplama için güncelle
        
        # Depoya dönüş mesafesini ekle
        depot_point = (  # Depo koordinatları
            instance[DEPART][COORDINATES][X_COORD],
            instance[DEPART][COORDINATES][Y_COORD]
        )
        final_leg = map_handler.get_distance(previous_point, depot_point)  # Son mesafe
        if final_leg == float('inf'):  # Mesafe hesaplanamazsa
            return float('inf')
        
        total_distance += final_leg  # Toplam mesafeye ekle
        return total_distance
        
    except Exception as e:
        print(f"Error calculating route: {str(e)}")
        return float('inf')

def evaluate_neighbors_parallel(neighbors, instance, map_handler, batch_size=5):
    """Komşu çözümleri paralel olarak değerlendir"""
    print(f"Starting parallel evaluation of {len(neighbors)} neighbors...")
    neighbor_distances = []  # Değerlendirme sonuçları
    
    # CPU kullanımını optimize et
    max_workers = max(2, multiprocessing.cpu_count() // 2)
    print(f"Using {max_workers} workers for parallel processing")
    
    def evaluate_single_neighbor(neighbor):
        """Tek bir komşu çözümü değerlendir"""
        try:
            distance = evaluate_solution_with_real_distances(neighbor, instance, map_handler)
            if distance != float('inf'):
                return neighbor, distance
            return None
        except Exception as e:
            print(f"Error evaluating neighbor: {str(e)}")
            return None
    
    # Komşuları gruplara böl
    batch_size = min(batch_size, len(neighbors))
    neighbor_batches = [neighbors[i:i + batch_size] for i in range(0, len(neighbors), batch_size)]
    
    # Her grubu paralel değerlendir
    for batch in neighbor_batches:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(evaluate_single_neighbor, n) for n in batch]
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        neighbor_distances.append(result)
                except Exception as e:
                    print(f"Error processing neighbor result: {str(e)}")
        
        # Yoğunluğu azaltmak için kısa bekleme
        time.sleep(0.1)
    
    print(f"Parallel evaluation completed. Found {len(neighbor_distances)} valid neighbors")
    return neighbor_distances

def diversify_solution(solution):
    """Çözümü çeşitlendirme stratejileri"""
    n = len(solution)  # Çözüm boyutu
    
    # Çeşitlendirme stratejileri
    strategies = [
        # Büyük segment ters çevirme
        lambda s: s[:i] + list(reversed(s[i:j])) + s[j:] 
        if (i := random.randint(0, n//3), j := random.randint(n*2//3, n))[0] >= 0 else s,
        
        # Çoklu nokta değişimi
        lambda s: [s[random.randint(0, n-1)] if random.random() < 0.3 else s[i] for i in range(n)],
        
        # Segment rotasyonu
        lambda s: s[k:] + s[:k] if (k := random.randint(n//4, n*3//4)) else s,
        
        # Rastgele segment karıştırma
        lambda s: (s[:i] + random.sample(s[i:j], j-i) + s[j:]) 
        if (i := random.randint(0, n//2), j := random.randint(i+2, n))[0] >= 0 else s,
    ]
    
    # Birden fazla strateji uygula
    new_solution = solution.copy()  # Çözümü kopyala
    for _ in range(random.randint(1, 3)):  # 1-3 arası strateji
        new_solution = random.choice(strategies)(new_solution)  # Rastgele strateji uygula
    
    # Çözümün geçerliliğini kontrol et
    if len(set(new_solution)) != len(solution):  # Tekrar eden nokta varsa
        return solution  # Orijinal çözümü döndür
    
    return new_solution
