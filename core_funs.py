import random
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from process_data import *

def generate_neighbors(solution, method="swap", num_neighbors=5):
    """Geliştirilmiş komşu üretimi"""
    neighbors = []
    size = len(solution)
    
    if method == "swap":
        # Hem yakın hem uzak noktaları değiştir
        for i in range(size-1):
            # Yakın komşular
            for j in range(i+1, min(i+5, size)):
                neighbor = solution.copy()
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                neighbors.append(neighbor)
            # Uzak komşular (rastgele)
            for _ in range(2):
                j = random.randint(i+5, size-1) if i+5 < size else random.randint(0, i-1)
                neighbor = solution.copy()
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                neighbors.append(neighbor)
    
    elif method == "insert":
        for i in range(size):
            value = solution[i]
            # Yakın ve uzak noktalara taşıma
            possible_positions = (
                list(range(max(0, i-4), min(size, i+5))) +  # Yakın pozisyonlar
                random.sample(range(size), min(3, size))     # Rastgele pozisyonlar
            )
            for j in possible_positions:
                if i != j:
                    neighbor = solution.copy()
                    neighbor.pop(i)
                    neighbor.insert(j, value)
                    neighbors.append(neighbor)
    
    elif method == "reverse":
        # Farklı boyutlarda segmentler
        for i in range(size-2):
            for length in range(2, min(8, size-i)):  # Daha uzun segmentler
                neighbor = solution.copy()
                neighbor[i:i+length] = reversed(neighbor[i:i+length])
                neighbors.append(neighbor)
            # Rastgele uzun segment çevirme
            if i < size-8:
                length = random.randint(8, min(15, size-i))
                neighbor = solution.copy()
                neighbor[i:i+length] = reversed(neighbor[i:i+length])
                neighbors.append(neighbor)
    
    elif method == "2-opt":
        for i in range(1, size-2):
            # Yakın kenarlar
            for j in range(i+1, min(i+6, size-1)):
                neighbor = solution.copy()
                neighbor[i:j] = reversed(neighbor[i:j])
                neighbors.append(neighbor)
            # Uzak kenarlar
            for _ in range(2):
                j = random.randint(min(i+6, size-1), size-1)
                neighbor = solution.copy()
                neighbor[i:j] = reversed(neighbor[i:j])
                neighbors.append(neighbor)
    
    # Akıllı seçim stratejisi
    if len(neighbors) > num_neighbors:
        # En az bir tane her türden al
        selected = []
        chunk_size = num_neighbors // 4
        for i in range(0, len(neighbors), len(neighbors)//4):
            selected.extend(random.sample(neighbors[i:i+len(neighbors)//4], 
                                       min(chunk_size, len(neighbors[i:i+len(neighbors)//4]))))
        # Kalan slotları rastgele doldur
        while len(selected) < num_neighbors:
            selected.append(random.choice(neighbors))
        return selected
    
    return neighbors

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

def evaluate_neighbors_parallel(neighbors, instance, map_handler, batch_size=5):
    """Komşuları paralel değerlendir"""
    print(f"Starting parallel evaluation of {len(neighbors)} neighbors...")
    
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
    
    neighbor_distances = []
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
        
        time.sleep(0.1)
    
    print(f"Parallel evaluation completed. Found {len(neighbor_distances)} valid neighbors")
    return neighbor_distances

def diversify_solution(solution):
    """Çözümü çeşitlendir"""
    n = len(solution)
    
    strategies = [
        # Büyük segment ters çevirme
        lambda s: s[:i] + list(reversed(s[i:j])) + s[j:] 
        if (i := random.randint(0, n//3), j := random.randint(n*2//3, n))[0] >= 0 else s,
        
        # Çoklu nokta değişimi
        lambda s: [s[random.randint(0, n-1)] if random.random() < 0.3 else s[i] 
                  for i in range(n)],
        
        # Segment rotasyonu
        lambda s: s[k:] + s[:k] if (k := random.randint(n//4, n*3//4)) else s,
        
        # Rastgele segment karıştırma
        lambda s: (s[:i] + random.sample(s[i:j], j-i) + s[j:]) 
        if (i := random.randint(0, n//2), j := random.randint(i+2, n))[0] >= 0 else s,
        
        # Çoklu segment değişimi
        lambda s: s[k1:k2] + s[:k1] + s[k2:] 
        if (k1 := random.randint(0, n//2), k2 := random.randint(k1+1, n))[0] >= 0 else s,
        
        # Adaptif nokta değişimi
        lambda s: [s[random.randint(0, n-1)] if random.random() < min(0.4, i/n) else s[i] 
                  for i in range(n)],
        
        # Çoklu segment rotasyonu
        lambda s: s[k1:k2] + s[k2:k3] + s[:k1] + s[k3:]
        if (k1 := random.randint(0, n//3), 
            k2 := random.randint(k1+1, 2*n//3),
            k3 := random.randint(k2+1, n))[0] >= 0 else s,
    ]
    
    new_solution = solution.copy()
    for _ in range(random.randint(1, 3)):
        new_solution = random.choice(strategies)(new_solution)
    
    if len(set(new_solution)) != len(solution):
        return solution
    
    return new_solution
