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
    vehicle_capacity = data[VEHICLE_CAPACITY]
    route = []
    sub_route = []
    vehicle_load = vehicle_capacity
    
    i = 0
    while i < len(individual):
        current_customer = individual[i]
        current_demand = data[F'C_{current_customer}'][DEMAND]
        

        if vehicle_load >= current_demand:

            if i + 1 < len(individual):
                next_customer = individual[i + 1]
                next_demand = data[F'C_{next_customer}'][DEMAND]
                remaining_after_current = vehicle_load - current_demand
                
                if remaining_after_current >= next_demand:

                    sub_route.append(current_customer)
                    vehicle_load -= current_demand
                    i += 1
                else:

                    sub_route.append(current_customer)
                    route.append(sub_route)
                    sub_route = []
                    vehicle_load = vehicle_capacity
                    i += 1
            else:

                sub_route.append(current_customer)
                route.append(sub_route)
                break
        else:

            if sub_route:
                route.append(sub_route)
                sub_route = []
            vehicle_load = vehicle_capacity

    

    if sub_route and sub_route not in route:
        route.append(sub_route)
        
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
    """Generate diverse neighbors using multiple methods"""
    neighbors = []
    size = len(solution)
    
    # Dinamik segment boyutları
    segment_size = max(2, size // 10)  # Çözüm boyutuna göre segment boyutu
    
    for _ in range(num_neighbors):
        # Yeni bir birey oluştur
        neighbor = solution.copy()
            
        # Farklı komşuluk yapıları
        if method == "swap":
            # Çoklu nokta değişimi
            num_swaps = random.randint(1, 3)  # 1-3 arası swap
            for _ in range(num_swaps):
                i, j = random.sample(range(size), 2)
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                
        elif method == "insert":
            # Çoklu nokta taşıma
            num_inserts = random.randint(1, 3)  # 1-3 arası insert
            for _ in range(num_inserts):
                i, j = random.sample(range(size), 2)
                value = neighbor.pop(i)
                neighbor.insert(j, value)
                
        elif method == "reverse":
            # Akıllı segment seçimi
            # Daha küçük segmentleri daha sık seç
            if random.random() < 0.7:  # %70 olasılıkla küçük segment
                max_segment = min(5, size // 4)
            else:  # %30 olasılıkla büyük segment
                max_segment = min(size // 2, 10)
                
            i = random.randint(0, size - max_segment)
            j = i + random.randint(2, max_segment)
            neighbor[i:j] = reversed(neighbor[i:j])
                
        elif method == "scramble":
            # Adaptif segment karıştırma
            if random.random() < 0.6:  # %60 olasılıkla küçük karıştırma
                seg_size = random.randint(2, min(5, size // 4))
            else:  # %40 olasılıkla büyük karıştırma
                seg_size = random.randint(size // 4, size // 2)
                
            i = random.randint(0, size - seg_size)
            sublist = neighbor[i:i + seg_size]
            random.shuffle(sublist)
            neighbor[i:i + seg_size] = sublist
            
        elif method == "block_move":
            # Blok taşıma operatörü
            block_size = random.randint(2, min(5, size // 4))
            i = random.randint(0, size - block_size)
            j = random.randint(0, size - block_size)
            
            if i != j:
                block = neighbor[i:i + block_size]
                del neighbor[i:i + block_size]
                neighbor[j:j] = block
                
        elif method == "cross":
            # Çapraz değişim operatörü
            if size >= 4:
                i = random.randint(0, size - 4)
                neighbor[i:i+2], neighbor[i+2:i+4] = neighbor[i+2:i+4], neighbor[i:i+2].copy()
            
        neighbors.append(neighbor)
            
    return neighbors

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Calculate total distance using real road network"""
    total_distance = 0
    previous_point = (
        instance[DEPART][COORDINATES][X_COORD],
        instance[DEPART][COORDINATES][Y_COORD]
    )
    
    try:
        # Calculate distances between consecutive points
        for customer_id in solution:
            current_point = (
                instance[f'C_{customer_id}'][COORDINATES][X_COORD],
                instance[f'C_{customer_id}'][COORDINATES][Y_COORD]
            )
            
            # Get distance from OSRM
            leg_distance = map_handler.get_distance(previous_point, current_point)
            if leg_distance == float('inf'):
                return float('inf')
            
            total_distance += leg_distance
            previous_point = current_point
        
        # Add return to depot
        depot_point = (
            instance[DEPART][COORDINATES][X_COORD],
            instance[DEPART][COORDINATES][Y_COORD]
        )
        final_leg = map_handler.get_distance(previous_point, depot_point)
        if final_leg == float('inf'):
            return float('inf')
        
        total_distance += final_leg
        return total_distance
        
    except Exception as e:
        print(f"Error calculating route: {str(e)}")
        return float('inf')

def evaluate_neighbors_parallel(neighbors, instance, map_handler, batch_size=5):
    """Komşuları paralel olarak değerlendir"""
    print(f"Starting parallel evaluation of {len(neighbors)} neighbors...")
    neighbor_distances = []
    
    # CPU sayısının yarısını kullan (diğer işlemler için CPU bırak)
    max_workers = max(2, multiprocessing.cpu_count() // 2)
    print(f"Using {max_workers} workers for parallel processing")
    
    def evaluate_single_neighbor(neighbor):
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
        
        # Her batch sonrası kısa bir bekleme
        time.sleep(0.1)
    
    print(f"Parallel evaluation completed. Found {len(neighbor_distances)} valid neighbors")
    return neighbor_distances

def diversify_solution(solution):
    """Çözümü çeşitlendirmek için geliştirilmiş fonksiyon"""
    n = len(solution)
    
    # Daha agresif çeşitlendirme stratejileri
    strategies = [
        # Büyük segment reverse
        lambda s: s[:i] + list(reversed(s[i:j])) + s[j:] 
        if (i := random.randint(0, n//3), j := random.randint(n*2//3, n))[0] >= 0 else s,
        
        # Multiple swap
        lambda s: [s[random.randint(0, n-1)] if random.random() < 0.3 else s[i] for i in range(n)],
        
        # Segment rotation
        lambda s: s[k:] + s[:k] if (k := random.randint(n//4, n*3//4)) else s,
        
        # Random shuffle of a segment
        lambda s: (s[:i] + random.sample(s[i:j], j-i) + s[j:]) 
        if (i := random.randint(0, n//2), j := random.randint(i+2, n))[0] >= 0 else s,
    ]
    
    # Birden fazla strateji uygula
    new_solution = solution.copy()
    for _ in range(random.randint(1, 3)):
        new_solution = random.choice(strategies)(new_solution)
    
    # Çözümün geçerliliğini kontrol et
    if len(set(new_solution)) != len(solution):
        return solution
    
    return new_solution
