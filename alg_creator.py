from core_funs import *
import collections
import random
from process_data import OSRMHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
import math

class AdaptiveTabuList:
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
    """Rastgele bir başlangıç çözümü oluşturur."""
    print("Generating a random initial solution...")
    
    # Müşteri ID'lerini içeren bir liste oluştur (1'den size'a kadar)
    solution = list(range(1, size + 1))
    
    # Listeyi rastgele karıştır
    random.shuffle(solution)
    
    print(f"Generated random solution with {len(solution)} customers.")
    return solution

def diversify_solution(solution):
    """
    Çözümü çeşitlendir.
    
    Args:
        solution: Mevcut çözüm
        
    Returns:
        Çeşitlendirilmiş yeni çözüm
    """
    n = len(solution)
    new_solution = solution.copy()
    
    # Rastgele bir strateji seç
    strategy = random.choice([
        'segment_reverse',
        'segment_rotate',
        'segment_shuffle',
        'full_shuffle'
    ])
    
    if strategy == 'segment_reverse':
        i = random.randint(0, n-3)
        j = random.randint(i+2, n)
        new_solution[i:j] = reversed(new_solution[i:j])
        
    elif strategy == 'segment_rotate':
        # Rastgele bir segment seç ve döndür
        segment_size = random.randint(2, n//2)
        start = random.randint(0, n-segment_size)
        segment = new_solution[start:start+segment_size]
        rotation = random.randint(1, segment_size-1)
        segment = segment[rotation:] + segment[:rotation]
        new_solution[start:start+segment_size] = segment
        
    elif strategy == 'segment_shuffle':
        # Rastgele bir segment seç ve karıştır
        segment_size = random.randint(3, n//2)
        start = random.randint(0, n-segment_size)
        segment = new_solution[start:start+segment_size]
        random.shuffle(segment)
        new_solution[start:start+segment_size] = segment
        
    else:  
        random.shuffle(new_solution)
    
    return new_solution

def split_into_routes(solution, customers, vehicle_capacity):
    """
    Çözümü araç kapasitesine göre rotalara böl
    
    Args:
        solution: Çözüm dizisi (müşteri id'leri)
        customers: (customer_id, demand) çiftlerinden oluşan liste
        vehicle_capacity: Araç kapasitesi
        
    Returns:
        Rotalar listesi veya geçersiz çözüm için None
    """
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

def evaluate_solution_cost(solution, instance_data, maps_handler, vehicle_capacity, distance_weight=1.0, energy_weight=0.5):
    """Çözümün ağırlıklı hibrit maliyetini (mesafe + enerji) hesaplar"""
    routes = split_into_routes(solution, [
        (i, float(instance_data[f'C_{i}']['demand']))
        for i in range(1, len(solution) + 1)
    ], vehicle_capacity)
    
    if not routes:
        return float('inf')
        
    total_energy_cost = 0
    total_distance = 0
    
    for route in routes:
        prev_point = (
            instance_data['depart']['coordinates']['x'],
            instance_data['depart']['coordinates']['y']
        )
        route_load = 0
        
        for customer_id in route:
            route_load += float(instance_data[f'C_{customer_id}']['demand'])
            curr_point = (
                instance_data[f'C_{customer_id}']['coordinates']['x'],
                instance_data[f'C_{customer_id}']['coordinates']['y']
            )
            
            # Mesafe
            segment_distance = maps_handler.get_distance(prev_point, curr_point)
            if segment_distance == float('inf'): return float('inf')
            total_distance += segment_distance

            # Enerji maliyeti (yük dahil)
            # Use get_route_cost which inherently includes distance and energy factors
            segment_energy_cost = maps_handler.get_route_cost(
                prev_point,
                curr_point,
                vehicle_mass=10000 + (route_load * 100) 
            )
            if segment_energy_cost == float('inf'): return float('inf')
            total_energy_cost += segment_energy_cost # Accumulate energy cost directly
            
            prev_point = curr_point
        
        # Depoya dönüş
        depot_point = (
            instance_data['depart']['coordinates']['x'],
            instance_data['depart']['coordinates']['y']
        )
        depot_return_distance = maps_handler.get_distance(prev_point, depot_point)
        depot_return_energy_cost = maps_handler.get_route_cost(
            prev_point, 
            depot_point,
            vehicle_mass=10000 + (route_load * 100) # Assume load affects return energy
        )
        
        if depot_return_distance == float('inf') or depot_return_energy_cost == float('inf'):
             return float('inf')
             
        total_distance += depot_return_distance
        total_energy_cost += depot_return_energy_cost
            
    # Hibrit maliyeti hesapla
    # Note: get_route_cost might already be a hybrid. Clarify calculation.
    # Assuming get_route_cost IS the energy cost component and we add weighted distance separately:
    hybrid_cost = (distance_weight * total_distance) + (energy_weight * total_energy_cost)
    # If get_route_cost is already hybrid, adjust weights or calculation.
    # For now, assume simple weighted sum as requested.
    return hybrid_cost

def run_tabu_search(
    instance_data,
    individual_size, 
    n_gen,
    tabu_size,
    stagnation_limit=15,
    verbose=True,
    vehicle_capacity=None,
    distance_weight=1.0, # Add weight parameters
    energy_weight=0.5    # Add weight parameters
):
    """Hibrit maliyet (mesafe + enerji) odaklı tek aşamalı tabu arama"""
    if instance_data is None or vehicle_capacity is None:
        return None
        
    print("\nStarting Hybrid Cost Focused Tabu Search...")
    print(f"Weights: Distance={distance_weight}, Energy={energy_weight}")
    maps_handler = OSRMHandler()
    
    print("Creating initial solution...")
    initial_solution = create_initial_solution(instance_data, individual_size, maps_handler)
    if not initial_solution:
        print("Failed to create initial solution")
        return None
    
    print(f"Initial solution created with {len(initial_solution)} customers")
    
    # Store the best hybrid cost and solution
    best_solution = initial_solution.copy()
    best_cost = evaluate_solution_cost( # Hybrid cost
        best_solution, instance_data, maps_handler, vehicle_capacity, 
        distance_weight, energy_weight
    )
    current_solution = initial_solution.copy()
    current_cost = best_cost
    
    tabu_list = AdaptiveTabuList(tabu_size, tabu_size * 2)
    stagnation_counter = 0
    
    print("\nStarting main Tabu Search loop...")
    print(f"Parameters: n_gen={n_gen}, tabu_size={tabu_size}, stagnation_limit={stagnation_limit}")
    print(f"Initial Hybrid Cost: {best_cost:.2f}")
    
    # Main tabu search loop
    iteration = 0 # Define iteration counter outside loop for final report
    for iteration in range(n_gen):
        if iteration % 10 == 0:  
            print(f"\nIteration {iteration}/{n_gen}")
            print(f"Current stagnation: {stagnation_counter}/{stagnation_limit}")
            print(f"Best hybrid cost so far: {best_cost:.2f}")
        
        if stagnation_counter >= stagnation_limit:
            print(f"\nEarly stopping! No improvement for {stagnation_limit} iterations.")
            break
        
        # Generate neighbors
        if iteration % 3 == 0:
            method = "swap"
        elif iteration % 3 == 1:
            method = "2-opt"
        else:
            method = "insert"
            
        neighbors = generate_neighbors(current_solution, method=method, num_neighbors=20)
        
        # Evaluate neighbors based on hybrid cost
        valid_neighbors = []
        for neighbor in neighbors:
            cost = evaluate_solution_cost( # Hybrid cost
                neighbor, instance_data, maps_handler, vehicle_capacity, 
                distance_weight, energy_weight
            )
            if cost != float('inf'):
                valid_neighbors.append((neighbor, cost))
        
        if not valid_neighbors:
            current_solution = diversify_solution(current_solution)
            stagnation_counter += 1
            continue
            
        # Select the best neighbor (based on hybrid cost)
        best_neighbor_solution, best_neighbor_cost = min(valid_neighbors, key=lambda x: x[1])
        
        # Update current solution
        current_solution = best_neighbor_solution
        current_cost = best_neighbor_cost
        
        # Update best solution (based on hybrid cost)
        if current_cost < best_cost:
            best_solution = current_solution.copy()
            best_cost = current_cost
            print(f"---> New best hybrid cost found: {best_cost:.2f} at iteration {iteration}")
            stagnation_counter = 0
        else:
            stagnation_counter += 1
            
        # Add to Tabu list
        tabu_list.add(current_solution)
            
    print(f"\nTabu Search completed after {iteration + 1} iterations")
    
    # Split the best solution into routes
    final_routes = split_into_routes(best_solution, [
        (i, float(instance_data[f'C_{i}']['demand']))
        for i in range(1, individual_size + 1)
    ], vehicle_capacity)
    
    if not final_routes:
        print("Failed to split the best solution into valid routes.")
        return None

    # Route quality analysis (remains the same)
    print("\nAnalyzing route quality...")
    problems = analyze_route_quality(final_routes, instance_data, maps_handler)
    
    print("\nRoute Quality Report:")
    print("-" * 80)
    if problems['crossings']:
        print(f"\nDetected {len(problems['crossings'])} crossing paths:")
        for cross in problems['crossings']:
            print(f"Route {cross['route']}: Segments {cross['segment1']} and {cross['segment2']} intersect")
    
    if problems['backtracking']:
        print(f"\nDetected {len(problems['backtracking'])} backtracking instances:")
        for back in problems['backtracking']:
            print(f"Route {back['route']}: At point {back['point']} (excess: {back['excess']:.2f}x)")
    
    if problems['long_segments']:
        print(f"\nDetected {len(problems['long_segments'])} long segments:")
        for seg in problems['long_segments']:
            print(f"Route {seg['route']}: Segment {seg['segment']} is {seg['distance']:.2f}km")
    
    if not any(problems.values()):
        print("\nNo route issues detected! The solution seems optimal based on hybrid cost.")
    else:
        print("\nWarning: The solution might have geometric inefficiencies.")
        print(f"Consider adjusting weights (current: D={distance_weight}, E={energy_weight}) or other parameters.")
        # ... (other parameter suggestions remain same) ...

    # Recalculate pure distance and energy cost for reporting
    final_total_distance = 0
    final_total_energy_cost = 0
    for route in final_routes:
        prev_point = (
            instance_data['depart']['coordinates']['x'],
            instance_data['depart']['coordinates']['y']
        )
        route_load = 0
        for customer_id in route:
            route_load += float(instance_data[f'C_{customer_id}']['demand'])
            curr_point = (
                instance_data[f'C_{customer_id}']['coordinates']['x'],
                instance_data[f'C_{customer_id}']['coordinates']['y']
            )
            final_total_distance += maps_handler.get_distance(prev_point, curr_point)
            # Use get_route_cost for final energy cost calculation as well
            final_total_energy_cost += maps_handler.get_route_cost(
                prev_point, curr_point, vehicle_mass=10000 + (route_load * 100)
            )
            prev_point = curr_point
            
        depot_point = (
            instance_data['depart']['coordinates']['x'],
            instance_data['depart']['coordinates']['y']
        )
        final_total_distance += maps_handler.get_distance(prev_point, depot_point)
        final_total_energy_cost += maps_handler.get_route_cost(
            prev_point, depot_point, vehicle_mass=10000 + (route_load * 100)
        )

    print("\nFinal Optimized Solution (Based on Hybrid Cost):")
    print(f"Number of routes: {len(final_routes)}")
    print(f"Optimized Hybrid Cost: {best_cost:.2f}")
    print(f"  - Calculated Total Distance: {final_total_distance:.2f} km")
    print(f"  - Calculated Total Energy Cost: {final_total_energy_cost:.2f}") # Use the recalculated energy cost
    
    return final_routes

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Gerçek yol mesafelerini ve yükseklik maliyetlerini kullanarak çözümü değerlendir"""
    if solution is None:
        return float('inf')
        
    total_cost = 0
    previous_point = (
        instance[DEPART][COORDINATES][X_COORD],
        instance[DEPART][COORDINATES][Y_COORD]
    )
    
    try:
        # Toplam yükü hesapla
        total_load = sum(float(instance[f'C_{customer_id}'][DEMAND]) for customer_id in solution)
        vehicle_mass = 10000 + (total_load * 100)  # Boş araç + yük (kg)
        
        # Ardışık noktalar arası maliyetleri hesapla
        for customer_id in solution:
            current_point = (
                instance[f'C_{customer_id}'][COORDINATES][X_COORD],
                instance[f'C_{customer_id}'][COORDINATES][Y_COORD]
            )
            
            # Mesafe ve yükseklik bazlı toplam maliyeti hesapla
            segment_cost = map_handler.get_route_cost(previous_point, current_point, vehicle_mass)
            if segment_cost == float('inf'):
                print(f"Warning: Could not calculate cost between {previous_point} and {current_point}")
                return float('inf')
            
            total_cost += segment_cost
            previous_point = current_point
        
        # Depoya dönüş
        depot_point = (
            instance[DEPART][COORDINATES][X_COORD],
            instance[DEPART][COORDINATES][Y_COORD]
        )
        final_cost = map_handler.get_route_cost(previous_point, depot_point, vehicle_mass)
        
        if final_cost == float('inf'):
            print(f"Warning: Could not calculate return cost to depot from {previous_point}")
            return float('inf')
        
        total_cost += final_cost
        return total_cost
        
    except Exception as e:
        print(f"Error calculating route cost: {str(e)}")
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

def generate_neighbors(solution, method="swap", num_neighbors=20):
    """Optimize edilmiş komşu üretimi"""
    neighbors = []
    size = len(solution)
    
    if method == "swap":
        # Akıllı swap: Yakın noktaları değiştir
        for i in range(size-1):
            for j in range(i+1, min(i+5, size)):  # Yakın noktalar
                neighbor = solution.copy()
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                neighbors.append(neighbor)
                
            # Birkaç uzak nokta ile de değişim yap
            for _ in range(2):
                j = random.randint(min(i+5, size-1), size-1)
                if j < size:  # Geçerlilik kontrolü
                    neighbor = solution.copy()
                    neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                    neighbors.append(neighbor)
    
    elif method == "2-opt":
        # 2-opt: Çapraz yolları düzelt
        for i in range(1, size-2):
            for j in range(i+2, size):
                if j - i <= 10:  # Çok uzun segmentlerden kaçın
                    neighbor = solution.copy()
                    neighbor[i:j] = reversed(neighbor[i:j])
                    neighbors.append(neighbor)
    
    elif method == "insert":
        # Akıllı insert: Noktaları mantıklı pozisyonlara taşı
        for i in range(size):
            # Yakın pozisyonlara taşı
            for offset in [-2, -1, 1, 2]:
                j = i + offset
                if 0 <= j < size:
                    neighbor = solution.copy()
                    value = neighbor.pop(i)
                    neighbor.insert(j, value)
                    neighbors.append(neighbor)
            
            # Birkaç uzak pozisyona taşı
            for _ in range(2):
                j = random.randint(0, size-1)
                if abs(i-j) > 3:
                    neighbor = solution.copy()
                    value = neighbor.pop(i)
                    neighbor.insert(j, value)
                    neighbors.append(neighbor)
    
    # Çözümleri filtrele ve en iyilerini seç
    if len(neighbors) > num_neighbors:
        return random.sample(neighbors, num_neighbors)
    return neighbors

def analyze_route_quality(routes, instance_data, maps_handler):
    """Rota kalitesini analiz et"""
    problems = {
        'crossings': [],  # Çapraz yollar
        'backtracking': [],  # Geri dönüşler
        'long_segments': []  # Uzun segmentler
    }
    
    for route_idx, route in enumerate(routes):
        points = []
        # Depo noktası
        points.append((
            instance_data['depart']['coordinates']['x'],
            instance_data['depart']['coordinates']['y']
        ))
        
        # Müşteri noktaları
        for customer_id in route:
            points.append((
                instance_data[f'C_{customer_id}']['coordinates']['x'],
                instance_data[f'C_{customer_id}']['coordinates']['y']
            ))
        
        # Depoya dönüş
        points.append(points[0])
        
        # Çapraz yol kontrolü
        for i in range(len(points)-1):
            for j in range(i+2, len(points)-1):
                if segments_intersect(points[i], points[i+1], points[j], points[j+1]):
                    problems['crossings'].append({
                        'route': route_idx,
                        'segment1': (i, i+1),
                        'segment2': (j, j+1)
                    })
        
        # Geri dönüş kontrolü
        for i in range(1, len(points)-1):
            prev_dist = maps_handler.get_distance(points[i-1], points[i])
            next_dist = maps_handler.get_distance(points[i], points[i+1])
            direct_dist = maps_handler.get_distance(points[i-1], points[i+1])
            
            if prev_dist + next_dist > direct_dist * 1.4:  # %40 sapma
                problems['backtracking'].append({
                    'route': route_idx,
                    'point': i,
                    'excess': (prev_dist + next_dist) / direct_dist
                })
        
        # Uzun segment kontrolü
        for i in range(len(points)-1):
            dist = maps_handler.get_distance(points[i], points[i+1])
            if dist > 20:  # 20km'den uzun segmentler
                problems['long_segments'].append({
                    'route': route_idx,
                    'segment': (i, i+1),
                    'distance': dist
                })
    
    return problems

def segments_intersect(p1, p2, p3, p4):
    """İki segment kesişiyor mu kontrol et"""
    def ccw(A, B, C):
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
    
    return ccw(p1,p3,p4) != ccw(p2,p3,p4) and ccw(p1,p2,p3) != ccw(p1,p2,p4)