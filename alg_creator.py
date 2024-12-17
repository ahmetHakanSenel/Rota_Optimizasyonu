from core_funs import *
import collections
import random
from process_data import GoogleMapsHandler, ProblemInstance
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

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
        self.frequency[solution_tuple] = self.frequency.get(solution_tuple, 0) + 1
        
        if len(self.list) >= self.current_size:
            self.current_size = min(self.current_size + 1, self.max_size)
    
    def contains(self, solution, aspiration_value=None, current_best=float('inf')):
        solution_tuple = tuple(solution)
        
        # Aspiration kriteri - önemli iyileştirme varsa kabul et
        if aspiration_value is not None and aspiration_value < self.best_known * 0.95:
            self.best_known = aspiration_value
            return False
        
        # Çözüm frekansını kontrol et
        if self.frequency.get(solution_tuple, 0) > 3:
            return True
        
        # Son N çözümde varsa yasakla
        recent_solutions = list(self.list)[-5:]  # Son 5 çözüm
        if solution_tuple in recent_solutions:
            return True
        
        return False
    
    def clear(self):
        """Tabu listesini ve frekans sayacını temizle"""
        self.list.clear()
        self.frequency.clear()
        self.current_size = len(self.list)
        self.best_known = float('inf')

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
    
    current_solution = create_initial_solution(instance, individual_size, maps_handler)
    current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
    
    def check_route_validity(route, instance):
        """Rotanın geçerliliğini kontrol et"""
        total_demand = 0
        visited = set()
        
        for customer_id in route:
            if customer_id in visited:
                return False  # Müşteri tekrarı
            visited.add(customer_id)
            
            customer = instance[f'C_{customer_id}']
            total_demand += customer[DEMAND]
            
            if total_demand > instance[VEHICLE_CAPACITY]:
                return False  # Kapasite aşımı
        
        return True
    
    def optimize_route_segments(route, instance, maps_handler):
        """Rota segmentlerini optimize et"""
        optimized = route.copy()
        improved = True
        while improved:
            improved = False
            for i in range(len(optimized) - 2):
                # 2-opt swap
                new_route = optimized.copy()
                new_route[i+1], new_route[i+2] = new_route[i+2], new_route[i+1]
                
                if check_route_validity(new_route, instance):
                    old_distance = evaluate_solution_with_real_distances(optimized, instance, maps_handler)
                    new_distance = evaluate_solution_with_real_distances(new_route, instance, maps_handler)
                    
                    if new_distance < old_distance:
                        optimized = new_route
                        improved = True
        
        return optimized
    
    # Ana döngü
    for iteration in range(n_gen):
        if stagnation_counter >= 20:
            current_solution = diversify_solution(current_solution)
            current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
            stagnation_counter = 0
            tabu_list.clear()
        
        # Komşuları üret ve paralel değerlendir
        neighbors = generate_neighbors(current_solution, instance, maps_handler)
        neighbor_distances = evaluate_neighbors_parallel(neighbors, instance, maps_handler)
        
        # En iyi komşuyu seç
        if neighbor_distances:
            best_neighbor, best_neighbor_distance = min(neighbor_distances, key=lambda x: x[1])
            
            if not tabu_list.contains(best_neighbor, best_neighbor_distance, best_distance):
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
        else:
            stagnation_counter += 1
        
        if verbose and iteration % 10 == 0:
            print(f"Iteration {iteration}, Best distance: {best_distance:.2f} km")
        
        if stagnation_counter >= stagnation_limit:
            break
    
    return decode_solution(best_solution, instance) if best_solution else None

def diversify_solution(solution):
    """Çözümü çeşitlendirmek için geliştirilmiş fonksiyon"""
    n = len(solution)
    
    # Farklı çeşitlendirme stratejileri
    strategies = [
        # Rastgele alt diziyi ters çevir
        lambda s: s[:i] + list(reversed(s[i:j])) + s[j:] if (i := random.randint(0, n-2), j := random.randint(i+1, n))[0] >= 0 else s,
        
        # Block relocation
        lambda s: s[k:] + s[:k] if (k := random.randint(1, n-1)) else s,
        
        # Rastgele swap operations
        lambda s: [s[j] if i == k else s[k] if i == j else s[i] for i in range(n)] 
        if (j := random.randint(0, n-1), k := random.randint(0, n-1))[0] >= 0 else s,
    ]
    
    # Rastgele bir strateji seç ve uygula
    new_solution = random.choice(strategies)(solution.copy())
    
    # Çözümün geçerliliğini kontrol et
    if len(set(new_solution)) != len(solution):
        return solution  # Geçersizse orijinal çözümü döndür
    
    return new_solution

def generate_neighbors(solution, instance, map_handler, max_neighbors=15):
    """Generate neighbors focusing on route optimization"""
    neighbors = []
    n = len(solution)
    
    # 1. 2-opt moves
    for i in range(n-1):
        for j in range(i+1, n):
            new_sol = solution.copy()
            new_sol[i:j+1] = reversed(new_sol[i:j+1])
            neighbors.append(new_sol)
            
            if len(neighbors) >= max_neighbors:
                return neighbors
    
    # 2. Swap moves
    for i in range(n):
        for j in range(i+1, n):
            new_sol = solution.copy()
            new_sol[i], new_sol[j] = new_sol[j], new_sol[i]
            neighbors.append(new_sol)
            
            if len(neighbors) >= max_neighbors:
                return neighbors
    
    return neighbors

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Calculate total distance using real road network"""
    solution_key = tuple(solution)
    
    if solution_key in map_handler.solution_cache:
        return map_handler.solution_cache[solution_key]
    
    # Tüm rotayı tek seferde hesapla
    points = []
    
    # Depo başlangıç
    depot = (instance[DEPART][COORDINATES][X_COORD], 
            instance[DEPART][COORDINATES][Y_COORD])
    points.append(f"{depot[0]},{depot[1]}")
    
    # Müşteri noktaları
    for customer_id in solution:
        coord = (
            instance[f'C_{customer_id}'][COORDINATES][X_COORD],
            instance[f'C_{customer_id}'][COORDINATES][Y_COORD]
        )
        points.append(f"{coord[0]},{coord[1]}")
    
    # Depoya dönüş
    points.append(f"{depot[0]},{depot[1]}")
    
    try:
        # Tüm rotayı tek seferde hesapla
        result = map_handler.gmaps.directions(
            origin=points[0],
            destination=points[-1],
            waypoints=points[1:-1],
            optimize_waypoints=False,  # Sırayı korumak için False
            mode="driving"
        )
        
        if result and len(result) > 0:
            # Toplam mesafeyi metre->km çevir
            total_distance = sum(leg['distance']['value'] for leg in result[0]['legs']) / 1000
            map_handler.solution_cache[solution_key] = total_distance
            return total_distance
        
        return float('inf')
        
    except Exception as e:
        print(f"Error calculating route: {e}")
        return float('inf')

def create_initial_solution(instance, size, map_handler):
    """Create initial solution using nearest neighbor"""
    solution = []
    available = set(range(1, size + 1))
    
    # Depodan başla
    depot = (instance[DEPART][COORDINATES][X_COORD],
             instance[DEPART][COORDINATES][Y_COORD])
    
    current = depot
    while available:
        # En yakın müşteriyi bul
        min_dist = float('inf')
        next_customer = None
        
        for customer_id in available:
            next_point = (instance[f'C_{customer_id}'][COORDINATES][X_COORD],
                         instance[f'C_{customer_id}'][COORDINATES][Y_COORD])
            
            # Gerçek yol mesafesini kullan
            result = map_handler.calculate_single_distance(current, next_point)
            if result and result[2]:
                dist = result[2][0]
                if dist < min_dist:
                    min_dist = dist
                    next_customer = customer_id
        
        if next_customer:
            solution.append(next_customer)
            available.remove(next_customer)
            current = (instance[f'C_{next_customer}'][COORDINATES][X_COORD],
                      instance[f'C_{next_customer}'][COORDINATES][Y_COORD])
        else:
            # Eğer mesafe hesaplanamadıysa kalan noktaları ekle
            solution.extend(available)
            break
    
    return solution

def decode_solution(solution, instance):
    """Convert solution to route format"""
    return [solution]

def evaluate_neighbors_parallel(neighbors, instance, map_handler, batch_size=5):
    """Komşuları paralel olarak değerlendir"""
    neighbor_distances = []
    
    with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        future_to_neighbor = {
            executor.submit(evaluate_solution_with_real_distances, n, instance, map_handler): n 
            for n in neighbors
        }
        
        for future in as_completed(future_to_neighbor):
            neighbor = future_to_neighbor[future]
            try:
                distance = future.result()
                if distance != float('inf'):
                    neighbor_distances.append((neighbor, distance))
            except Exception as e:
                print(f"Error evaluating neighbor: {e}")
    
    return neighbor_distances