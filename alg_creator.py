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
        self.elite_solutions = []  # En iyi çözümleri sakla
    
    def add(self, solution):
        solution_tuple = tuple(solution)
        self.list.append(solution_tuple)
        self.frequency[solution_tuple] = self.frequency.get(solution_tuple, 0) + 1
        
        if len(self.list) >= self.current_size:
            self.current_size = min(self.current_size + 1, self.max_size)
    
    def contains(self, solution, aspiration_value=None, current_best=float('inf')):
        solution_tuple = tuple(solution)
        
        # Aspiration kriteri - önemli iyileştirme varsa kabul et
        if aspiration_value is not None:
            if aspiration_value < self.best_known * 0.95:  # %5 iyileştirme
                self.best_known = aspiration_value
                self.elite_solutions.append((solution_tuple, aspiration_value))
                return False
            elif aspiration_value < current_best * 0.98:  # %2 iyileştirme
                return False
        
        # Çözüm frekansını kontrol et
        if self.frequency.get(solution_tuple, 0) > 3:
            return True
        
        # Son N çözümde varsa yasakla
        recent_solutions = list(self.list)[-5:]
        if solution_tuple in recent_solutions:
            return True
        
        return False
    
    def clear(self):
        """Tabu listesini temizle ama elit çözümleri koru"""
        self.list.clear()
        self.frequency.clear()
        self.current_size = len(self.list)
        
        # En iyi çözümleri geri yükle
        if self.elite_solutions:
            best_elite = min(self.elite_solutions, key=lambda x: x[1])
            self.best_known = best_elite[1]

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
    last_best_distance = float('inf')
    same_value_counter = 0
    
    # Başlangıç parametreleri
    current_tabu_size = tabu_size
    current_max_neighbors = 15
    current_stagnation_limit = stagnation_limit
    
    tabu_list = AdaptiveTabuList(current_tabu_size, current_tabu_size * 2)
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
    
    print("Starting Tabu Search optimization...")
    print(f"Parameters: generations={n_gen}, tabu_size={tabu_size}, stagnation_limit={stagnation_limit}")
    
    # Ana döngü
    for iteration in range(n_gen):
        print(f"\nIteration {iteration}:")
        
        if stagnation_counter >= current_stagnation_limit:
            print("Stagnation detected! Diversifying solution...")
            current_solution = diversify_solution(current_solution)
            current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
            print(f"New diversified solution distance: {current_distance:.2f} km")
            stagnation_counter = 0
            tabu_list.clear()
        
        print("Generating neighbors...")
        neighbors = generate_neighbors(current_solution, instance, maps_handler, max_neighbors=current_max_neighbors)
        print(f"Generated {len(neighbors)} neighbors")
        
        print("Evaluating neighbors in parallel...")
        neighbor_distances = evaluate_neighbors_parallel(neighbors, instance, maps_handler)
        print(f"Found {len(neighbor_distances)} valid neighbors")
        
        if neighbor_distances:
            best_neighbor, best_neighbor_distance = min(neighbor_distances, key=lambda x: x[1])
            print(f"Best neighbor distance: {best_neighbor_distance:.2f} km")
            
            if not tabu_list.contains(best_neighbor, best_neighbor_distance, best_distance):
                print("Best neighbor accepted (not in tabu list)")
                current_solution = best_neighbor
                current_distance = best_neighbor_distance
                tabu_list.add(current_solution)
                
                if best_neighbor_distance < best_distance:
                    improvement = ((best_distance - best_neighbor_distance) / best_distance) * 100
                    print(f"New best solution found! Improvement: {improvement:.2f}%")
                    best_solution = best_neighbor.copy()
                    best_distance = best_neighbor_distance
                    stagnation_counter = 0
                else:
                    print("No improvement in best solution")
                    stagnation_counter += 1
            else:
                print("Best neighbor rejected (in tabu list)")
                stagnation_counter += 1
        else:
            print("No valid neighbors found")
            stagnation_counter += 1
        
        # Aynı değerde kalma kontrolü
        if abs(best_distance - last_best_distance) < 0.01:
            same_value_counter += 1
            print(f"Solution unchanged for {same_value_counter} iterations")
        else:
            same_value_counter = 0
            last_best_distance = best_distance
        
        # Parametre ayarlama
        if same_value_counter >= 5:
            print("\nAdjusting parameters...")
            current_tabu_size = max(5, min(30, current_tabu_size + random.randint(-3, 5)))
            current_max_neighbors = max(10, min(30, current_max_neighbors + random.randint(-3, 5)))
            current_stagnation_limit = max(15, min(50, current_stagnation_limit + random.randint(-5, 8)))
            
            print(f"New parameters - Tabu size: {current_tabu_size}, "
                  f"Max neighbors: {current_max_neighbors}, "
                  f"Stagnation limit: {current_stagnation_limit}")
            
            tabu_list = AdaptiveTabuList(current_tabu_size, current_tabu_size * 2)
            same_value_counter = 0
        
        print(f"\nCurrent best distance: {best_distance:.2f} km")
        print(f"Stagnation counter: {stagnation_counter}")
    
    print("\nOptimization completed!")
    print(f"Final best distance: {best_distance:.2f} km")
    print(f"Final solution: {best_solution}")
    
    return decode_solution(best_solution, instance) if best_solution else None

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

def generate_neighbors(solution, instance, map_handler, max_neighbors=15):
    """Generate smarter neighbors"""
    neighbors = []
    n = len(solution)
    
    # 1. 2-opt moves with varying segment sizes
    segment_sizes = [(2,4), (3,6), (4,8)]  # Farklı segment boyutları
    for min_size, max_size in segment_sizes:
        for i in range(n-min_size):
            j = min(i + random.randint(min_size, max_size), n)
            new_sol = solution.copy()
            new_sol[i:j] = reversed(new_sol[i:j])
            neighbors.append(new_sol)
    
    # 2. Chain moves (3 noktayı birden değiştir)
    for i in range(n-2):
        new_sol = solution.copy()
        j, k = i+1, i+2
        new_sol[i], new_sol[j], new_sol[k] = new_sol[k], new_sol[i], new_sol[j]
        neighbors.append(new_sol)
    
    # 3. Block insertion (blok taşıma)
    block_sizes = [2, 3, 4]
    for size in block_sizes:
        if n > size * 2:
            for i in range(n - size):
                block = solution[i:i+size]
                for j in range(n - size):
                    if abs(i-j) > size:
                        new_sol = solution.copy()
                        del new_sol[i:i+size]
                        new_sol[j:j] = block
                        neighbors.append(new_sol)
    
    # Komşuları karıştır ve en iyilerini seç
    random.shuffle(neighbors)
    return neighbors[:max_neighbors]

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
    """Create simple initial solution"""
    print("\nCreating initial solution...")
    
    # Basit sıralı çözüm oluştur
    solution = list(range(1, size + 1))
    random.shuffle(solution)  # Rastgele karıştır
    
    print(f"Initial solution created: {solution}")
    initial_distance = evaluate_solution_with_real_distances(solution, instance, map_handler)
    print(f"Initial solution distance: {initial_distance:.2f} km\n")
    
    return solution

def decode_solution(solution, instance):
    """Convert solution to route format"""
    return [solution]

def evaluate_neighbors_parallel(neighbors, instance, map_handler, batch_size=5):
    """Komşuları paralel olarak değerlendir"""
    print(f"Starting parallel evaluation of {len(neighbors)} neighbors...")
    neighbor_distances = []
    
    # CPU sayısının yarısını kullan (diğer işlemler için CPU bırak)
    max_workers = max(2, multiprocessing.cpu_count() // 2)
    print(f"Using {max_workers} workers for parallel processing")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_neighbor = {
            executor.submit(evaluate_solution_with_real_distances, n, instance, map_handler): n 
            for n in neighbors
        }
        
        completed = 0
        for future in as_completed(future_to_neighbor):
            completed += 1
            if completed % 5 == 0:  # Her 5 değerlendirmede bir rapor ver
                print(f"Evaluated {completed}/{len(neighbors)} neighbors")
                
            neighbor = future_to_neighbor[future]
            try:
                distance = future.result()
                if distance != float('inf'):
                    neighbor_distances.append((neighbor, distance))
            except Exception as e:
                print(f"Error evaluating neighbor: {e}")
    
    print(f"Parallel evaluation completed. Found {len(neighbor_distances)} valid neighbors")
    return neighbor_distances