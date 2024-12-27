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
    """Geliştirilmiş başlangıç çözümü"""
    best_solution = None
    best_distance = float('inf')
    
    # Depo koordinatları
    depot = (
        instance[DEPART][COORDINATES][X_COORD],
        instance[DEPART][COORDINATES][Y_COORD]
    )
    
    # Önce tüm noktaların depoya olan uzaklıklarını hesapla
    distances_to_depot = {}
    for i in range(1, size + 1):
        point = (
            instance[f'C_{i}'][COORDINATES][X_COORD],
            instance[f'C_{i}'][COORDINATES][Y_COORD]
        )
        dist = map_handler.get_distance(depot, point)
        distances_to_depot[i] = dist
    
    # En yakın ve en uzak 3'er nokta + 2 rastgele nokta ile başla
    closest_points = sorted(distances_to_depot.items(), key=lambda x: x[1])[:3]
    farthest_points = sorted(distances_to_depot.items(), key=lambda x: x[1], reverse=True)[:3]
    start_points = [p[0] for p in closest_points + farthest_points]
    
    # Rastgele 2 nokta ekle
    remaining_points = set(range(1, size + 1)) - set(start_points)
    if remaining_points:
        start_points.extend(random.sample(list(remaining_points), min(2, len(remaining_points))))
    
    for start_point in start_points:
        for strategy in ['nearest', 'balanced', 'farthest']:
            solution = [start_point]
            unvisited = set(range(1, size + 1)) - {start_point}
            current_point = (
                instance[f'C_{start_point}'][COORDINATES][X_COORD],
                instance[f'C_{start_point}'][COORDINATES][Y_COORD]
            )
            
            while unvisited:
                distances = {
                    x: map_handler.get_distance(current_point, 
                        (instance[f'C_{x}'][COORDINATES][X_COORD],
                         instance[f'C_{x}'][COORDINATES][Y_COORD]))
                    for x in unvisited
                }
                
                # Strateji seçimi
                if strategy == 'nearest':
                    next_point = min(distances.items(), key=lambda x: x[1])[0]
                elif strategy == 'farthest':
                    valid_distances = {k:v for k,v in distances.items() if v != float('inf')}
                    next_point = max(valid_distances.items(), key=lambda x: x[1])[0] if valid_distances else min(distances.items(), key=lambda x: x[1])[0]
                else:  # balanced
                    # Hem mesafe hem depoya uzaklığı dengele
                    next_point = min(distances.items(), 
                                   key=lambda x: x[1] + distances_to_depot[x[0]])[0]
                
                solution.append(next_point)
                unvisited.remove(next_point)
                current_point = (
                    instance[f'C_{next_point}'][COORDINATES][X_COORD],
                    instance[f'C_{next_point}'][COORDINATES][Y_COORD]
                )
            
            # Daha agresif iyileştirme
            improved = k_opt_improvement(solution, instance, map_handler, k=2)
            improved = k_opt_improvement(improved, instance, map_handler, k=3)
            improved = k_opt_improvement(improved, instance, map_handler, k=2)
            
            # Toplam mesafeyi hesapla
            distance = evaluate_solution_with_real_distances(improved, instance, map_handler)
            if distance < best_distance:
                best_solution = improved
                best_distance = distance
    
    return best_solution

def run_tabu_search(
    instance_name,
    individual_size,
    pop_size,
    n_gen,
    tabu_size,
    plot=False,
    stagnation_limit=20,
    verbose=True,
    use_real_distances=True,
    early_stop_limit=60
):
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

    vehicle_capacity = float(instance.get('vehicle_capacity', 500))
    customers = [(i, float(instance[f'C_{i}']['demand'])) for i in range(1, individual_size + 1)]
    
    def split_into_routes(solution):
        """Çözümü araç kapasitesine göre rotalara böl"""
        routes = []
        current_route = []
        current_load = 0
        
        for customer_id in solution:
            customer_demand = next(demand for cid, demand in customers if cid == customer_id)
            
            if current_load + customer_demand > vehicle_capacity:
                if current_route:  # Mevcut rotayı ekle
                    routes.append(current_route)
                current_route = [customer_id]
                current_load = customer_demand
            else:
                current_route.append(customer_id)
                current_load += customer_demand
        
        if current_route:  # Son rotayı ekle
            routes.append(current_route)
        
        return routes

    def calculate_total_distance(routes):
        """Tüm rotaların toplam mesafesini hesapla"""
        total_distance = 0
        for route in routes:
            prev_point = (
                instance['depart']['coordinates']['x'],
                instance['depart']['coordinates']['y']
            )
            
            for customer_id in route:
                current_point = (
                    instance[f'C_{customer_id}']['coordinates']['x'],
                    instance[f'C_{customer_id}']['coordinates']['y']
                )
                total_distance += maps_handler.get_distance(prev_point, current_point)
                prev_point = current_point
            
            # Depoya dönüş
            depot_point = (
                instance['depart']['coordinates']['x'],
                instance['depart']['coordinates']['y']
            )
            total_distance += maps_handler.get_distance(prev_point, depot_point)
        
        return total_distance

    def evaluate_solution(solution):
        """Çözümü değerlendir - araç sayısı ve mesafe optimizasyonu"""
        routes = split_into_routes(solution)
        num_vehicles = len(routes)
        total_distance = calculate_total_distance(routes)
        
        # Araç sayısı ve mesafe için ağırlıklı değerlendirme
        # Araç sayısını minimize etmek öncelikli
        return num_vehicles * 10000 + total_distance

    best_solution = None
    best_fitness = float('inf')
    current_solution = list(range(1, individual_size + 1))
    random.shuffle(current_solution)
    
    tabu_list = AdaptiveTabuList(tabu_size, tabu_size * 2)
    stagnation_counter = 0
    no_improvement_counter = 0
    
    print("\nStarting optimization...")
    for iteration in range(n_gen):
        if verbose and iteration % 100 == 0:
            print(f"\nIteration {iteration}:")
        
        # Early stopping kontrolü
        if no_improvement_counter >= early_stop_limit:
            print(f"\nEarly stopping! No improvement for {early_stop_limit} iterations.")
            break
        
        # Komşu çözümler üret
        neighbors = generate_neighbors(current_solution, method="swap", num_neighbors=20)
        neighbors.extend(generate_neighbors(current_solution, method="2-opt", num_neighbors=20))
        
        # En iyi komşuyu bul
        best_neighbor = None
        best_neighbor_fitness = float('inf')
        
        for neighbor in neighbors:
            if not tabu_list.contains(neighbor):
                fitness = evaluate_solution(neighbor)
                if fitness < best_neighbor_fitness:
                    best_neighbor = neighbor
                    best_neighbor_fitness = fitness
        
        if best_neighbor is None:
            # Çeşitlilik ekle
            current_solution = diversify_solution(current_solution)
            stagnation_counter += 1
            continue
        
        # Çözümü güncelle
        current_solution = best_neighbor
        current_fitness = best_neighbor_fitness
        
        # En iyi çözümü güncelle
        if current_fitness < best_fitness:
            best_solution = current_solution.copy()
            best_fitness = current_fitness
            stagnation_counter = 0
            no_improvement_counter = 0
            if verbose:
                routes = split_into_routes(best_solution)
                print(f"New best solution found!")
                print(f"Number of vehicles: {len(routes)}")
                print(f"Total distance: {calculate_total_distance(routes):.2f} km")
        else:
            stagnation_counter += 1
            no_improvement_counter += 1
        
        # Tabu listesini güncelle
        tabu_list.add(current_solution)
        
        # Durağanlık kontrolü
        if stagnation_counter >= stagnation_limit:
            print("Stagnation detected! Diversifying solution...")
            current_solution = diversify_solution(current_solution)
            stagnation_counter = 0
    
    if best_solution is None:
        return None
    
    # En iyi çözümü rotalara böl
    final_routes = split_into_routes(best_solution)
    print("\nFinal Solution:")
    print(f"Number of vehicles: {len(final_routes)}")
    print(f"Total distance: {calculate_total_distance(final_routes):.2f} km")
    
    return final_routes

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