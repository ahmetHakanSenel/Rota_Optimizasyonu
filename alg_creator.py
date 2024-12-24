from core_funs import *
import collections
import random
from process_data import OSRMHandler, ProblemInstance
from concurrent.futures import ThreadPoolExecutor, as_completed

class AdaptiveTabuList:
    """Adaptif Tabu Listesi sınıfı"""
    def __init__(self, initial_size, max_size):
        self.max_size = max_size
        self.list = collections.deque(maxlen=initial_size)
        self.frequency = {}
        self.current_size = initial_size
        self.best_known = float('inf')
        self.elite_solutions = []
    
    def add(self, solution):
        solution_tuple = tuple(solution)
        self.list.append(solution_tuple)
        self.frequency[solution_tuple] = self.frequency.get(solution_tuple, 0) + 1
        
        if len(self.list) >= self.current_size:
            self.current_size = min(self.current_size + 1, self.max_size)
    
    def contains(self, solution, aspiration_value=None, current_best=float('inf')):
        solution_tuple = tuple(solution)
        
        if aspiration_value is not None and current_best != float('inf'):
            improvement = (current_best - aspiration_value) / current_best * 100
            if improvement > 5:
                self.best_known = min(self.best_known, aspiration_value)
                self.elite_solutions.append((solution_tuple, aspiration_value))
                return False
        
        freq = self.frequency.get(solution_tuple, 0)
        if freq > 0:
            threshold = max(0.4, 0.95 - (0.1 * freq))
            recent_solutions = list(self.list)[-5:]
            for recent in recent_solutions:
                if sum(a == b for a, b in zip(solution_tuple, recent)) / len(solution_tuple) > threshold:
                    return True
        
        return False
    
    def clear(self):
        self.list.clear()
        self.frequency.clear()
        self.current_size = len(self.list)
        
        if self.elite_solutions:
            self.best_known = min(self.elite_solutions, key=lambda x: x[1])[1]

def k_opt_improvement(solution, instance, map_handler, k=2):
    """Birleştirilmiş k-opt iyileştirme"""
    improved = solution.copy()
    best_distance = evaluate_solution_with_real_distances(improved, instance, map_handler)
    size = len(improved)
    
    while True:
        improvement_found = False
        
        if k == 2:
            for i in range(size - 1):
                for j in range(i + 2, size):
                    new_solution = improved[:i] + list(reversed(improved[i:j])) + improved[j:]
                    new_distance = evaluate_solution_with_real_distances(new_solution, instance, map_handler)
                    
                    if new_distance < best_distance:
                        improved = new_solution
                        best_distance = new_distance
                        improvement_found = True
                        break
        else:  # k == 3
            for i in range(size - 2):
                for j in range(i + 1, size - 1):
                    for k in range(j + 1, size):
                        combinations = [
                            improved[:i] + improved[i:j][::-1] + improved[j:k][::-1] + improved[k:],
                            improved[:i] + improved[i:j] + improved[j:k][::-1] + improved[k:],
                            improved[:i] + improved[i:j][::-1] + improved[j:k] + improved[k:]
                        ]
                        
                        for new_sol in combinations:
                            new_distance = evaluate_solution_with_real_distances(new_sol, instance, map_handler)
                            if new_distance < best_distance:
                                improved = new_sol
                                best_distance = new_distance
                                improvement_found = True
                                break
        
        if not improvement_found:
            break
    
    return improved

def create_initial_solution(instance, size, map_handler):
    """Daha iyi başlangıç çözümü"""
    # En yakın komşu + 2-opt + 3-opt yerine
    # Çoklu başlangıç noktası ve en iyi seçim
    best_solution = None
    best_distance = float('inf')
    
    for start_point in range(1, min(6, size+1)):  # İlk 5 noktayı dene
        solution = [start_point]
        unvisited = set(range(1, size + 1)) - {start_point}
        current_point = (
            instance[f'C_{start_point}'][COORDINATES][X_COORD],
            instance[f'C_{start_point}'][COORDINATES][Y_COORD]
        )
        
        while unvisited:
            next_point = min(unvisited, 
                           key=lambda x: map_handler.get_distance(current_point, 
                               (instance[f'C_{x}'][COORDINATES][X_COORD],
                                instance[f'C_{x}'][COORDINATES][Y_COORD])))
            solution.append(next_point)
            unvisited.remove(next_point)
            current_point = (
                instance[f'C_{next_point}'][COORDINATES][X_COORD],
                instance[f'C_{next_point}'][COORDINATES][Y_COORD]
            )
        
        # İyileştirmeler
        improved = k_opt_improvement(solution, instance, map_handler, k=2)
        improved = k_opt_improvement(improved, instance, map_handler, k=3)
        
        distance = evaluate_solution_with_real_distances(improved, instance, map_handler)
        if distance < best_distance:
            best_solution = improved
            best_distance = distance
    
    return best_solution

def run_tabu_search(instance_name, individual_size, pop_size, n_gen, tabu_size, 
                    plot=False, stagnation_limit=20, verbose=True, 
                    use_real_distances=True, early_stop_limit=60):
    """Geliştirilmiş Tabu Arama algoritması"""
    random.seed(42)
    
    # Problem verilerini yükle
    problem_instance = ProblemInstance(instance_name)
    instance = problem_instance.get_data()
    
    if instance is None:
        return None
    
    print("Initializing OSRM handler and precomputing distances...")
    maps_handler = OSRMHandler()
    if not maps_handler.precompute_distances(instance):
        print("Failed to precompute distances. Exiting...")
        return None
    
    best_solution = None  
    best_distance = float('inf')  # En iyi mesafe
    last_best_distance = float('inf')  # Son en iyi mesafe
    same_value_counter = 0  # Aynı değerde kalma sayacı
    no_improvement_counter = 0  # İyileştirme olmayan iterasyon sayacı
    
    # Başlangıç parametreleri
    current_tabu_size = tabu_size
    current_max_neighbors = 30  
    current_stagnation_limit = stagnation_limit
    
    # Komşuluk yöntemleri ve ağırlıkları
    neighborhood_methods = {
        "swap": 0.3,       # Basit değişimlere daha fazla ağırlık
        "insert": 0.2,     # Nokta taşımaya daha fazla ağırlık
        "reverse": 0.2,    # Segment çevirme
        "2-opt": 0.3      # 2-opt hareketi
    }
    
    # Tabu listesini başlat
    tabu_list = AdaptiveTabuList(current_tabu_size, current_tabu_size * 2)
    stagnation_counter = 0  # Durağanlık sayacı
    
    # Başlangıç çözümünü oluştur ve ilk en iyi çözüm olarak ata
    current_solution = create_initial_solution(instance, individual_size, maps_handler)
    current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
    
    # İlk çözümü en iyi çözüm olarak ata
    best_solution = current_solution.copy()
    best_distance = current_distance
    
    print(f"Initial solution distance: {best_distance:.2f} km")
    
    print("Starting Tabu Search optimization...")
    print(f"Parameters: generations={n_gen}, tabu_size={tabu_size}, "
          f"stagnation_limit={stagnation_limit}, early_stop_limit={early_stop_limit}")
    
    no_improvement_streak = 0
    
    # Ana döngü
    for iteration in range(n_gen):
        print(f"\nIteration {iteration}:")
        
        # Early stopping kontrolü
        if no_improvement_counter >= early_stop_limit:
            print(f"\nEarly stopping! No improvement for {early_stop_limit} iterations.")
            break
        
        # Durağanlık kontrolü
        if stagnation_counter >= current_stagnation_limit:
            print("Stagnation detected! Diversifying solution...")
            current_solution = diversify_solution(current_solution)
            current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
            print(f"New diversified solution distance: {current_distance:.2f} km")
            stagnation_counter = 0
            tabu_list.clear()
            
            # Komşuluk ağırlıklarını güncelle
            if iteration > n_gen // 2:  # İkinci yarıda daha agresif ol
                neighborhood_methods["reverse"] = 0.2
                neighborhood_methods["2-opt"] = 0.2
                neighborhood_methods["swap"] = 0.15
                neighborhood_methods["insert"] = 0.15
        
        print("Generating neighbors...")
        # Farklı komşuluk yöntemlerini ağırlıklarına göre kullan
        neighbors = []
        for method, weight in neighborhood_methods.items():
            num_neighbors = max(1, int(current_max_neighbors * weight))
            neighbors.extend(generate_neighbors(current_solution, method=method, num_neighbors=num_neighbors))
        print(f"Generated {len(neighbors)} neighbors")
        
        # Komşuları paralel olarak değerlendir
        print("Evaluating neighbors in parallel...")
        neighbor_distances = evaluate_neighbors_parallel(neighbors, instance, maps_handler)
        print(f"Found {len(neighbor_distances)} valid neighbors")
        
        if neighbor_distances:  # Geçerli komşular bulunduysa
            best_neighbor, best_neighbor_distance = min(neighbor_distances, key=lambda x: x[1])
            print(f"Best neighbor distance: {best_neighbor_distance:.2f} km")
            
            # Tabu kontrolü
            if not tabu_list.contains(best_neighbor, best_neighbor_distance, best_distance):
                print("Best neighbor accepted (not in tabu list)")
                current_solution = best_neighbor
                current_distance = best_neighbor_distance
                tabu_list.add(current_solution)
                
                # İyileştirme kontrolü
                if best_neighbor_distance < best_distance:
                    print(f"New best solution found! Improvement: {((best_distance - best_neighbor_distance) / best_distance) * 100:.2f}%")
                    best_solution = best_neighbor.copy()  # En iyi çözümü güncelle
                    best_distance = best_neighbor_distance  # En iyi mesafeyi güncelle
                    stagnation_counter = 0
                    no_improvement_counter = 0
                else:
                    print("No improvement in best solution")
                    stagnation_counter += 1
                    no_improvement_counter += 1
            else:
                print("Best neighbor rejected (in tabu list)")
                stagnation_counter += 1
                no_improvement_counter += 1
        else:
            print("No valid neighbors found")
            stagnation_counter += 1
            no_improvement_counter += 1
        
        if abs(best_distance - last_best_distance) < 0.01:
            same_value_counter += 1
            print(f"Solution unchanged for {same_value_counter} iterations")
        else:
            same_value_counter = 0
            last_best_distance = best_distance
        
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
        print(f"No improvement counter: {no_improvement_counter}")
        
        if no_improvement_streak >= early_stop_limit // 2:
            print("No significant improvement, stopping early...")
            break
    
    if no_improvement_counter >= early_stop_limit:
        print("\nOptimization stopped early due to no improvement")
    else:
        print("\nOptimization completed!")
        
    print(f"Final best distance: {best_distance:.2f} km")
    print(f"Final solution: {best_solution}")
    
    if best_solution is not None and best_distance != float('inf'):
        return decode_solution(best_solution, instance)
    else:
        print("Warning: No valid solution found!")
        return None

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Gerçek yol mesafelerini kullanarak çözümü değerlendir"""
    if solution is None:
        return float('inf')
        
    total_distance = 0
    previous_point = (
        instance[DEPART][COORDINATES][X_COORD],
        instance[DEPART][COORDINATES][Y_COORD]
    )
    
    try:
        # Ardışık noktalar arası mesafeleri hesapla
        for customer_id in solution:
            current_point = (
                instance[f'C_{customer_id}'][COORDINATES][X_COORD],
                instance[f'C_{customer_id}'][COORDINATES][Y_COORD]
            )
            
            leg_distance = map_handler.get_distance(previous_point, current_point)
            if leg_distance == float('inf'):
                print(f"Warning: Could not calculate distance between {previous_point} and {current_point}")
                return float('inf')
            
            total_distance += leg_distance
            previous_point = current_point
        
        # Depoya dönüş
        depot_point = (
            instance[DEPART][COORDINATES][X_COORD],
            instance[DEPART][COORDINATES][Y_COORD]
        )
        final_leg = map_handler.get_distance(previous_point, depot_point)
        
        if final_leg == float('inf'):
            print(f"Warning: Could not calculate return distance to depot from {previous_point}")
            return float('inf')
        
        total_distance += final_leg
        return total_distance
        
    except Exception as e:
        print(f"Error calculating route: {str(e)}")
        return float('inf')

def decode_solution(solution, instance):
    """Çözümü rota formatına dönüştür"""
    return [solution]  # Tek araçlı rota

def evaluate_neighbors_parallel(neighbors, instance, map_handler, max_workers=4):
    """Komşu çözümleri paralel olarak değerlendir"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Tüm komşuları aynı anda değerlendir
        future_to_neighbor = {
            executor.submit(evaluate_solution_with_real_distances, n, instance, map_handler): n 
            for n in neighbors
        }
        
        # Sonuçları topla
        valid_neighbors = []
        for future in as_completed(future_to_neighbor):
            neighbor = future_to_neighbor[future]
            try:
                distance = future.result()
                if distance != float('inf'):
                    valid_neighbors.append((neighbor, distance))
            except Exception as e:
                print(f"Error evaluating neighbor: {e}")
    
    return valid_neighbors

def generate_neighbors(solution, method="swap", num_neighbors=5):
    """Geliştirilmiş komşuluk üretimi"""
    neighbors = []
    size = len(solution)
    
    if method == "swap":
        # Sistematik değişimler
        for i in range(size-1):
            for j in range(i+1, min(i+5, size)):  # Yakın noktaları değiştir
                neighbor = solution.copy()
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                neighbors.append(neighbor)
    
    elif method == "insert":
        # Akıllı ekleme
        for i in range(size):
            value = solution[i]
            # Yakın konumlara taşı
            for j in range(max(0, i-4), min(size, i+5)):
                if i != j:
                    neighbor = solution.copy()
                    neighbor.pop(i)
                    neighbor.insert(j, value)
                    neighbors.append(neighbor)
    
    elif method == "reverse":
        # Segment çevirme
        for i in range(size-2):
            for length in range(2, min(6, size-i)):  # 2-5 uzunluğunda segmentler
                neighbor = solution.copy()
                neighbor[i:i+length] = reversed(neighbor[i:i+length])
                neighbors.append(neighbor)
    
    elif method == "2-opt":
        # 2-opt hareketi
        for i in range(1, size-2):
            for j in range(i+1, min(i+6, size-1)):
                neighbor = solution.copy()
                neighbor[i:j] = reversed(neighbor[i:j])
                neighbors.append(neighbor)
    
    # Rastgele seç ama en az bir tane her türden al
    if len(neighbors) > num_neighbors:
        selected = random.sample(neighbors, num_neighbors-1)
        selected.append(random.choice(neighbors))  # Ekstra şans
        return selected
    
    return neighbors