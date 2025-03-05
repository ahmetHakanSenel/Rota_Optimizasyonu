import random
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from process_data import *

def generate_neighbors_optimized(solution, method="swap", num_neighbors=5):
    """Optimize edilmiş komşu üretimi"""
    neighbors = []
    size = len(solution)
    
    if method == "swap":
        # Sadece yakın komşular
        for i in range(size-1):
            for j in range(i+1, min(i+3, size)):
                neighbor = solution.copy()
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                neighbors.append(neighbor)
    
    elif method == "2-opt":
        for i in range(1, size-2):
            for j in range(i+1, min(i+4, size-1)):
                neighbor = solution.copy()
                neighbor[i:j] = reversed(neighbor[i:j])
                neighbors.append(neighbor)
    
    return neighbors[:num_neighbors] if len(neighbors) > num_neighbors else neighbors

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Çözümün gerçek mesafesini hesapla"""
    if solution is None:
        return float('inf')
        
    total_distance = 0
    previous_point = (
        instance[DEPART][COORDINATES][X_COORD],
        instance[DEPART][COORDINATES][Y_COORD]
    )
    
    try:
        for customer_id in solution:
            current_point = (
                instance[f'C_{customer_id}'][COORDINATES][X_COORD],
                instance[f'C_{customer_id}'][COORDINATES][Y_COORD]
            )
            
            leg_distance = map_handler.get_distance(previous_point, current_point)
            if leg_distance == float('inf'):
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
            return float('inf')
        
        total_distance += final_leg
        return total_distance
        
    except Exception as e:
        print(f"Error calculating route: {str(e)}")
        return float('inf')

def evaluate_neighbors_parallel_optimized(neighbors, instance, map_handler):
    """Optimize edilmiş paralel değerlendirme"""
    max_workers = max(2, multiprocessing.cpu_count() // 2)
    
    def evaluate_single_neighbor(neighbor):
        try:
            distance = evaluate_solution_with_real_distances(neighbor, instance, map_handler)
            return (neighbor, distance) if distance != float('inf') else None
        except Exception as e:
            print(f"Error evaluating neighbor: {str(e)}")
            return None
    
    neighbor_distances = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(evaluate_single_neighbor, n) for n in neighbors]
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    neighbor_distances.append(result)
            except Exception:
                continue
    
    return neighbor_distances

def diversify_solution_optimized(solution):
    """Optimize edilmiş çözüm çeşitlendirme"""
    n = len(solution)
    
    strategies = [
        # Segment ters çevirme
        lambda s: s[:i] + list(reversed(s[i:j])) + s[j:] 
        if (i := random.randint(0, n//2), j := random.randint(i+2, n))[0] >= 0 else s,
        
        # Segment rotasyonu
        lambda s: s[k:] + s[:k] if (k := random.randint(n//4, 3*n//4)) else s
    ]
    
    new_solution = solution.copy()
    new_solution = random.choice(strategies)(new_solution)
    
    return new_solution if len(set(new_solution)) == len(solution) else solution
