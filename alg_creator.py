from core_funs import *
import collections
import random
from process_data import OSRMHandler, ProblemInstance
from concurrent.futures import ThreadPoolExecutor, as_completed
import math

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
    """Geliştirilmiş k-opt iyileştirme"""
    improved = solution.copy()
    best_distance = evaluate_solution_with_real_distances(improved, instance, map_handler)
    improvement_found = True
    
    while improvement_found:
        improvement_found = False
        
        if k == 2:
            # 2-opt: Tüm olası kenar çiftlerini kontrol et
            for i in range(len(improved) - 2):
                for j in range(i + 2, len(improved)):
                    # Kenarları ters çevir
                    new_solution = improved[:i] + list(reversed(improved[i:j])) + improved[j:]
                    new_distance = evaluate_solution_with_real_distances(new_solution, instance, map_handler)
                    
                    if new_distance < best_distance:
                        improved = new_solution
                        best_distance = new_distance
                        improvement_found = True
                        break
                if improvement_found:
                    break
                    
        elif k == 3:
            # 3-opt: Üç kenarı değiştir
            for i in range(len(improved) - 4):
                for j in range(i + 2, len(improved) - 2):
                    for k in range(j + 2, len(improved)):
                        # Tüm olası 3-opt kombinasyonları
                        combinations = [
                            improved[:i] + improved[i:j][::-1] + improved[j:k][::-1] + improved[k:],
                            improved[:i] + improved[i:j] + improved[j:k][::-1] + improved[k:],
                            improved[:i] + improved[i:j][::-1] + improved[j:k] + improved[k:],
                            improved[:i] + list(reversed(improved[i:k])) + improved[k:]
                        ]
                        
                        for new_sol in combinations:
                            new_distance = evaluate_solution_with_real_distances(new_sol, instance, map_handler)
                            if new_distance < best_distance:
                                improved = new_sol
                                best_distance = new_distance
                                improvement_found = True
                                break
                        if improvement_found:
                            break
                    if improvement_found:
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
    
    # Tüm noktaların depoya olan uzaklıklarını hesapla
    distances_to_depot = {}
    for i in range(1, size + 1):
        point = (
            instance[f'C_{i}'][COORDINATES][X_COORD],
            instance[f'C_{i}'][COORDINATES][Y_COORD]
        )
        dist = map_handler.get_distance(depot, point)
        distances_to_depot[i] = dist
    
    # Farklı başlangıç stratejileri
    strategies = ['nearest', 'farthest', 'sweep', 'balanced']
    
    for strategy in strategies:
        if strategy == 'sweep':
            # Açısal tarama yöntemi
            angles = {}
            for i in range(1, size + 1):
                point = (
                    instance[f'C_{i}'][COORDINATES][X_COORD],
                    instance[f'C_{i}'][COORDINATES][Y_COORD]
                )
                angle = math.atan2(point[1] - depot[1], point[0] - depot[0])
                angles[i] = angle
            
            # Açıya göre sırala
            solution = sorted(range(1, size + 1), key=lambda x: angles[x])
            
        else:
            solution = []
            unvisited = set(range(1, size + 1))
            current_point = depot
            
            while unvisited:
                distances = {
                    x: map_handler.get_distance(current_point, 
                        (instance[f'C_{x}'][COORDINATES][X_COORD],
                         instance[f'C_{x}'][COORDINATES][Y_COORD]))
                    for x in unvisited
                }
                
                if strategy == 'nearest':
                    next_point = min(distances.items(), key=lambda x: x[1])[0]
                elif strategy == 'farthest':
                    next_point = max(distances.items(), key=lambda x: x[1])[0]
                else:  # balanced
                    # Mesafe ve depoya uzaklık dengesi
                    next_point = min(distances.items(), 
                                   key=lambda x: x[1] + distances_to_depot[x[0]])[0]
                
                solution.append(next_point)
                unvisited.remove(next_point)
                current_point = (
                    instance[f'C_{next_point}'][COORDINATES][X_COORD],
                    instance[f'C_{next_point}'][COORDINATES][Y_COORD]
                )
        
        # 2-opt ve 3-opt iyileştirmeleri
        improved = k_opt_improvement(solution, instance, map_handler, k=2)
        improved = k_opt_improvement(improved, instance, map_handler, k=3)
        
        # En iyi çözümü güncelle
        distance = evaluate_solution_with_real_distances(improved, instance, map_handler)
        if distance < best_distance:
            best_solution = improved
            best_distance = distance
    
    return best_solution

def run_tabu_search(
    instance_data,
    individual_size,
    n_gen,
    tabu_size,
    stagnation_limit=20,
    verbose=True,
    vehicle_capacity=None
):
    """Geliştirilmiş Tabu Arama algoritması"""
    random.seed(42)
    
    if instance_data is None:
        return None
    
    print("Initializing OSRM handler and precomputing distances...")
    maps_handler = OSRMHandler()
    if not maps_handler.precompute_distances(instance_data):
        print("Failed to precompute distances. Exiting...")
        return None

    # Ensure vehicle capacity is considered in the optimization
    if vehicle_capacity is None:
        raise ValueError('Vehicle capacity must be provided')
    
    # Calculate total demand
    total_demand = sum(float(instance_data[f'C_{i}']['demand']) for i in range(1, individual_size + 1))
    print(f"Total demand: {total_demand}, Vehicle capacity: {vehicle_capacity}")
    
    # Check if problem is solvable with given capacity
    if total_demand > vehicle_capacity * instance_data['max_vehicle_number']:
        print("Problem is unsolvable: Total demand exceeds maximum possible capacity")
        return None
    
    customers = [(i, float(instance_data[f'C_{i}']['demand'])) for i in range(1, individual_size + 1)]
    
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
        
        # Check if we exceed maximum vehicle number
        if len(routes) > instance_data['max_vehicle_number']:
            return None
        
        return routes

    def calculate_total_distance(routes):
        """Tüm rotaların toplam mesafesini hesapla"""
        total_distance = 0
        for route in routes:
            prev_point = (
                instance_data['depart']['coordinates']['x'],
                instance_data['depart']['coordinates']['y']
            )
            
            for customer_id in route:
                current_point = (
                    instance_data[f'C_{customer_id}']['coordinates']['x'],
                    instance_data[f'C_{customer_id}']['coordinates']['y']
                )
                total_distance += maps_handler.get_distance(prev_point, current_point)
                prev_point = current_point
            
            # Depoya dönüş
            depot_point = (
                instance_data['depart']['coordinates']['x'],
                instance_data['depart']['coordinates']['y']
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
    
    tabu_list = AdaptiveTabuList(tabu_size * 2, tabu_size * 4)
    diversification_threshold = stagnation_limit // 2
    stagnation_counter = 0
    no_improvement_counter = 0
    
    print("\nStarting optimization...")
    for iteration in range(n_gen):
        if verbose and iteration % 100 == 0:
            print(f"\nIteration {iteration}:")
        
        if no_improvement_counter >= stagnation_limit:
            print(f"\nEarly stopping! No improvement for {stagnation_limit} iterations.")
            break
        
        # Daha fazla komşu üret
        neighbors = []
        neighbors.extend(generate_neighbors(current_solution, method="swap", num_neighbors=30))
        neighbors.extend(generate_neighbors(current_solution, method="2-opt", num_neighbors=30))
        neighbors.extend(generate_neighbors(current_solution, method="insert", num_neighbors=20))
        
        best_neighbor = None
        best_neighbor_fitness = float('inf')
        
        for neighbor in neighbors:
            if not tabu_list.contains(neighbor, aspiration_value=evaluate_solution(neighbor)):
                fitness = evaluate_solution(neighbor)
                if fitness < best_neighbor_fitness:
                    best_neighbor = neighbor
                    best_neighbor_fitness = fitness
        
        if best_neighbor is None:
            current_solution = diversify_solution(current_solution)
            stagnation_counter += 1
            continue
        
        # Her 5 iterasyonda bir 2-opt iyileştirmesi uygula
        if iteration % 5 == 0:
            best_neighbor = k_opt_improvement(best_neighbor, instance_data, maps_handler, k=2)
        
        # Her 10 iterasyonda bir 3-opt iyileştirmesi uygula
        if iteration % 10 == 0:
            best_neighbor = k_opt_improvement(best_neighbor, instance_data, maps_handler, k=3)
        
        current_solution = best_neighbor
        current_fitness = best_neighbor_fitness
        
        if current_fitness < best_fitness:
            best_solution = current_solution.copy()
            best_fitness = current_fitness
            stagnation_counter = 0
            no_improvement_counter = 0
        else:
            stagnation_counter += 1
            no_improvement_counter += 1
        
        tabu_list.add(current_solution)
        
        # Daha agresif çeşitlendirme
        if stagnation_counter >= diversification_threshold:
            print("Diversifying solution...")
            current_solution = diversify_solution(current_solution)
            current_solution = k_opt_improvement(current_solution, instance_data, maps_handler, k=2)
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


def evaluate_neighbors_parallel(neighbors, instance, map_handler, max_workers=4):
    """Komşu çözümleri paralel olarak değerlendir"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_neighbor = {
            executor.submit(evaluate_solution_with_real_distances, n, instance, map_handler): n 
            for n in neighbors
        }
        
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
        for i in range(size-1):
            for j in range(i+1, min(i+5, size)):  
                neighbor = solution.copy()
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                neighbors.append(neighbor)
    
    elif method == "insert":
        for i in range(size):
            value = solution[i]
            for j in range(max(0, i-4), min(size, i+5)):
                if i != j:
                    neighbor = solution.copy()
                    neighbor.pop(i)
                    neighbor.insert(j, value)
                    neighbors.append(neighbor)
    
    elif method == "reverse":
        for i in range(size-2):
            for length in range(2, min(6, size-i)):  
                neighbor = solution.copy()
                neighbor[i:i+length] = reversed(neighbor[i:i+length])
                neighbors.append(neighbor)
    
    elif method == "2-opt":
        for i in range(1, size-2):
            for j in range(i+1, min(i+6, size-1)):
                neighbor = solution.copy()
                neighbor[i:j] = reversed(neighbor[i:j])
                neighbors.append(neighbor)
    
    if len(neighbors) > num_neighbors:
        selected = random.sample(neighbors, num_neighbors-1)
        selected.append(random.choice(neighbors))  
        return selected
    
    return neighbors