from core_funs import *
import collections
import random
from process_data import GoogleMapsHandler, ProblemInstance

class AdaptiveTabuList:
    def __init__(self, initial_size, max_size):
        self.max_size = max_size
        self.list = collections.deque(maxlen=initial_size)
        self.frequency = {}
        self.current_size = initial_size
        self.best_known = float('inf')

    def add(self, solution):
        solution_tuple = tuple(solution)
        self.list.append(solution_tuple)
        # Frekans sayacını güncelle
        self.frequency[solution_tuple] = self.frequency.get(solution_tuple, 0) + 1
        
        # Tabu listesi boyutunu dinamik olarak ayarla
        if len(self.list) >= self.current_size:
            self.current_size = min(self.current_size + 1, self.max_size)

    def contains(self, solution, aspiration_value=None, current_best=float('inf')):
        solution_tuple = tuple(solution)
        
        # Hızlı aspiration kontrolü
        if aspiration_value is not None and aspiration_value < self.best_known:
            self.best_known = aspiration_value
            return False
        
        # Basit frekans kontrolü
        if self.frequency.get(solution_tuple, 0) > 2:
            return True
        
        return solution_tuple in self.list

    def clear(self):
        self.list.clear()
        self.frequency.clear()
        self.current_size = len(self.list)

def run_tabu_search(instance_name, individual_size, pop_size, n_gen, tabu_size, 
                    plot=False, stagnation_limit=50, verbose=True, 
                    use_real_distances=True, api_key=None):
    """Run optimized tabu search algorithm"""
    problem_instance = ProblemInstance(instance_name)
    instance = problem_instance.get_data()
    
    if instance is None:
        return None
    
    maps_handler = GoogleMapsHandler(api_key)
    
    best_solution = None
    best_distance = float('inf')
    tabu_list = AdaptiveTabuList(tabu_size, tabu_size * 2)
    stagnation_counter = 0
    
    current_solution = create_initial_solution(instance, individual_size)
    current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
    
    # Ana döngü
    for iteration in range(n_gen):
        if stagnation_counter >= 20:  # Daha erken çeşitlendirme
            current_solution = diversify_solution(current_solution)
            current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
            stagnation_counter = 0
            tabu_list.clear()
        
        neighbors = generate_neighbors(current_solution)  # Daha az komşu
        best_neighbor = None
        best_neighbor_distance = float('inf')
        
        # Komşuları değerlendir
        for neighbor in neighbors:
            distance = evaluate_solution_with_real_distances(neighbor, instance, maps_handler)
            if not tabu_list.contains(neighbor, distance, best_distance):
                if distance < best_neighbor_distance:
                    best_neighbor = neighbor
                    best_neighbor_distance = distance
        
        if best_neighbor is not None:
            current_solution = best_neighbor
            current_distance = best_neighbor_distance
            tabu_list.add(current_solution)
            
            if best_neighbor_distance < best_distance:
                best_solution = best_neighbor.copy()
                best_distance = best_neighbor_distance
                stagnation_counter = 0
            else:
                stagnation_counter += 1
        else:
            stagnation_counter += 1
        
        if verbose and iteration % 10 == 0:
            print(f"Iteration {iteration}, Best distance: {best_distance:.2f} km")
        
        if stagnation_counter >= stagnation_limit:
            break
    
    return decode_solution(best_solution, instance) if best_solution else None

def diversify_solution(solution):
    """Çözümü çeşitlendirmek için kullanılan fonksiyon"""
    n = len(solution)
    
    # Rastgele bir alt diziyi ters çevir
    i, j = sorted(random.sample(range(n), 2))
    solution[i:j+1] = reversed(solution[i:j+1])
    
    # Rastgele bir noktayı başka bir yere taşı
    if random.random() < 0.5:
        pos1, pos2 = random.sample(range(n), 2)
        value = solution.pop(pos1)
        solution.insert(pos2, value)
    
    return solution

def generate_neighbors(solution, max_neighbors=30):
    """Generate limited number of diverse neighbors"""
    neighbors = []
    n = len(solution)
    
    # Swap neighbors (daha az sayıda)
    num_swaps = min(15, n * (n-1) // 4)
    for _ in range(num_swaps):
        i, j = random.sample(range(n), 2)
        neighbor = solution.copy()
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
        neighbors.append(neighbor)
    
    # Insert neighbors (daha az sayıda)
    if len(neighbors) < max_neighbors:
        num_inserts = min(10, n)
        for _ in range(num_inserts):
            i, j = random.sample(range(n), 2)
            neighbor = solution.copy()
            value = neighbor.pop(i)
            neighbor.insert(j, value)
            neighbors.append(neighbor)
    
    # Reverse neighbors (sadece gerektiğinde)
    if len(neighbors) < max_neighbors and random.random() < 0.2:
        i, j = sorted(random.sample(range(n), 2))
        neighbor = solution.copy()
        neighbor[i:j+1] = reversed(neighbor[i:j+1])
        neighbors.append(neighbor)
    
    return neighbors

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Calculate total distance using real road network with caching"""
    solution_key = tuple(solution)
    if hasattr(map_handler, 'solution_cache') and solution_key in map_handler.solution_cache:
        return map_handler.solution_cache[solution_key]
    
    total_distance = 0
    points = []
    
    # Tüm noktaları topla
    depot = (instance[DEPART][COORDINATES][X_COORD], 
            instance[DEPART][COORDINATES][Y_COORD])
    points.append(depot)
    
    for customer_id in solution:
        points.append((
            instance[f'C_{customer_id}'][COORDINATES][X_COORD],
            instance[f'C_{customer_id}'][COORDINATES][Y_COORD]
        ))
    points.append(depot)
    
    # Mesafeleri toplu hesapla
    for i in range(len(points)-1):
        point1, point2 = points[i], points[i+1]
        # Simetrik mesafe kontrolü - (A,B) yoksa (B,A)'yı kontrol et
        cache_key = (point1, point2)
        reverse_key = (point2, point1)
        
        if cache_key in map_handler.distance_cache:
            distance = map_handler.distance_cache[cache_key][0]
        elif reverse_key in map_handler.distance_cache:
            # Simetrik mesafeyi kullan
            distance = map_handler.distance_cache[reverse_key][0]
            # Orijinal yönü de cache'e ekle
            map_handler.distance_cache[cache_key] = map_handler.distance_cache[reverse_key]
        else:
            # Her iki yön için de cache'de yoksa hesapla
            result = map_handler.calculate_single_distance(point1, point2)
            if result and result[2]:
                distance = result[2][0]
                # Her iki yön için de cache'e ekle
                map_handler.distance_cache[cache_key] = result[2]
                map_handler.distance_cache[reverse_key] = result[2]
            else:
                distance = float('inf')
        
        total_distance += distance
    
    # Çözümü cache'le
    if not hasattr(map_handler, 'solution_cache'):
        map_handler.solution_cache = {}
    map_handler.solution_cache[solution_key] = total_distance
    
    return total_distance

def create_initial_solution(instance, size):
    """Create initial random solution"""
    return list(range(1, size + 1))

def decode_solution(solution, instance):
    """Convert solution to route format"""
    return [solution]