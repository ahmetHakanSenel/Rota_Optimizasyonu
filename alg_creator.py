from core_funs import *
import collections
import random
from process_data import OSRMHandler
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
        'segment_reverse',  # Bir segmenti ters çevir
        'segment_rotate',   # Bir segmenti döndür
        'segment_shuffle',  # Bir segmenti karıştır
        'full_shuffle'      # Tüm çözümü karıştır
    ])
    
    if strategy == 'segment_reverse':
        # Rastgele bir segment seç ve ters çevir
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
        
    else:  # full_shuffle
        # Tüm çözümü karıştır
        random.shuffle(new_solution)
    
    return new_solution

def run_tabu_search(
    instance_data,
    individual_size,
    n_gen,
    tabu_size,
    stagnation_limit=20,
    verbose=True,
    vehicle_capacity=None
):
    """Optimize edilmiş Tabu Arama algoritması"""
    random.seed(42)
    
    if instance_data is None:
        return None
    
    print("Initializing optimization...")
    maps_handler = OSRMHandler()
    
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
    
    # Önbellek oluştur - aynı çözümleri tekrar tekrar değerlendirmemek için
    solution_cache = {}
    
    def split_into_routes(solution):
        """Çözümü araç kapasitesine göre rotalara böl"""
        # Önbellekte var mı kontrol et
        solution_tuple = tuple(solution)
        if solution_tuple in solution_cache and 'routes' in solution_cache[solution_tuple]:
            return solution_cache[solution_tuple]['routes']
            
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
        
        # Önbelleğe ekle
        if solution_tuple not in solution_cache:
            solution_cache[solution_tuple] = {}
        solution_cache[solution_tuple]['routes'] = routes
        
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
        """Çözümü değerlendir - araç sayısı, mesafe ve yükseklik optimizasyonu"""
        # Önbellekte var mı kontrol et
        solution_tuple = tuple(solution)
        if solution_tuple in solution_cache and 'fitness' in solution_cache[solution_tuple]:
            return solution_cache[solution_tuple]['fitness']
            
        routes = split_into_routes(solution)
        if routes is None:
            return float('inf')
            
        num_vehicles = len(routes)
        
        # Optimizasyon: Araç sayısı çok fazlaysa erken çık
        if num_vehicles > instance_data['max_vehicle_number']:
            return float('inf')
        
        # Yükseklik verilerini de içeren toplam maliyet hesaplaması
        total_cost = 0
        for route in routes:
            # Rota başlangıcı (depo)
            prev_point = (
                instance_data['depart']['coordinates']['x'],
                instance_data['depart']['coordinates']['y']
            )
            
            # Rota üzerindeki her müşteri için
            route_load = 0
            for customer_id in route:
                # Müşteri yükünü ekle
                route_load += float(instance_data[f'C_{customer_id}']['demand'])
                
                # Müşteri konumu
                current_point = (
                    instance_data[f'C_{customer_id}']['coordinates']['x'],
                    instance_data[f'C_{customer_id}']['coordinates']['y']
                )
                
                # Araç kütlesi (boş araç + yük)
                vehicle_mass = 10000 + (route_load * 100)  # kg
                
                # Yükseklik verilerini içeren rota maliyeti
                segment_cost = maps_handler.get_route_cost(prev_point, current_point, vehicle_mass)
                total_cost += segment_cost
                
                prev_point = current_point
            
            # Depoya dönüş
            depot_point = (
                instance_data['depart']['coordinates']['x'],
                instance_data['depart']['coordinates']['y']
            )
            
            # Depoya dönüş maliyeti
            return_cost = maps_handler.get_route_cost(prev_point, depot_point, vehicle_mass)
            total_cost += return_cost
        
        # Araç sayısı ve toplam maliyet için ağırlıklı değerlendirme
        # Araç sayısını minimize etmek öncelikli
        fitness = num_vehicles * 10000 + total_cost
        
        # Önbelleğe ekle
        if solution_tuple not in solution_cache:
            solution_cache[solution_tuple] = {}
        solution_cache[solution_tuple]['fitness'] = fitness
        
        return fitness

    # Başlangıç çözümünü oluştur
    print("Creating initial solution...")
    initial_solution = create_initial_solution(instance_data, individual_size, maps_handler)
    if initial_solution is None:
        print("Failed to create initial solution")
        # Rastgele bir çözüm oluştur
        initial_solution = list(range(1, individual_size + 1))
        random.shuffle(initial_solution)
    
    best_solution = initial_solution.copy()
    best_fitness = evaluate_solution(best_solution)
    current_solution = initial_solution.copy()
    current_fitness = best_fitness
    
    tabu_list = AdaptiveTabuList(tabu_size, tabu_size * 2)
    diversification_threshold = stagnation_limit // 2
    stagnation_counter = 0
    no_improvement_counter = 0
    
    print("\nStarting optimization...")
    
    # Optimizasyon: Maksimum iterasyon sayısını problem boyutuna göre ayarla
    max_iterations = min(n_gen, 200 + individual_size * 10)
    
    for iteration in range(max_iterations):
        if verbose and iteration % 100 == 0:
            print(f"\nIteration {iteration}:")
        
        if no_improvement_counter >= stagnation_limit:
            print(f"\nEarly stopping! No improvement for {stagnation_limit} iterations.")
            break
        
        # Optimizasyon: Daha az komşu üret
        neighbors = []
        
        # İlk iterasyonlarda daha fazla komşu üret, sonra azalt
        neighbor_count = max(10, 40 - iteration // 50)
        
        # Farklı komşuluk yapılarını kullan
        if iteration % 3 == 0:
            neighbors.extend(generate_neighbors(current_solution, method="swap", num_neighbors=neighbor_count))
        elif iteration % 3 == 1:
            neighbors.extend(generate_neighbors(current_solution, method="2-opt", num_neighbors=neighbor_count))
        else:
            neighbors.extend(generate_neighbors(current_solution, method="insert", num_neighbors=neighbor_count))
        
        # Optimizasyon: Komşuları paralel değerlendir
        valid_neighbors = []
        for neighbor in neighbors:
            fitness = evaluate_solution(neighbor)
            if fitness != float('inf'):
                valid_neighbors.append((neighbor, fitness))
        
        if not valid_neighbors:
            print("No valid neighbors found. Diversifying...")
            current_solution = diversify_solution(current_solution)
            stagnation_counter += 1
            continue
        
        # Tabu olmayan en iyi komşuyu seç
        best_neighbor = None
        best_neighbor_fitness = float('inf')
        
        for neighbor, fitness in valid_neighbors:
            if not tabu_list.contains(neighbor, aspiration_value=fitness, current_best=best_fitness):
                if fitness < best_neighbor_fitness:
                    best_neighbor = neighbor
                    best_neighbor_fitness = fitness
        
        if best_neighbor is None:
            # Tabu olmayan komşu bulunamadı, en iyi komşuyu seç
            best_neighbor, best_neighbor_fitness = min(valid_neighbors, key=lambda x: x[1])
        
        # Optimizasyon: k-opt iyileştirmesini daha az sıklıkla uygula
        if iteration % 10 == 0:
            best_neighbor = k_opt_improvement(best_neighbor, instance_data, maps_handler, k=2)
            best_neighbor_fitness = evaluate_solution(best_neighbor)
        
        # Çözümü güncelle
        current_solution = best_neighbor
        current_fitness = best_neighbor_fitness
        tabu_list.add(current_solution)
        
        # En iyi çözümü güncelle
        if current_fitness < best_fitness:
            best_solution = current_solution.copy()
            best_fitness = current_fitness
            no_improvement_counter = 0
            if verbose:
                print(f"New best solution found! Fitness: {best_fitness}")
                routes = split_into_routes(best_solution)
                print(f"Vehicles: {len(routes)}, Total distance: {calculate_total_distance(routes):.2f} km")
        else:
            no_improvement_counter += 1
        
        # Çeşitlendirme stratejisi
        if no_improvement_counter >= diversification_threshold:
            if verbose:
                print(f"Diversifying after {no_improvement_counter} iterations without improvement")
            
            # Mevcut çözümü çeşitlendir
            if random.random() < 0.5:
                # Rastgele segmentleri ters çevir
                for _ in range(3):
                    i = random.randint(0, len(current_solution) - 3)
                    j = random.randint(i + 2, len(current_solution))
                    current_solution[i:j] = reversed(current_solution[i:j])
            else:
                # Rastgele karıştır
                random.shuffle(current_solution)
            
            current_fitness = evaluate_solution(current_solution)
            tabu_list.clear()
            no_improvement_counter = 0
    
    # Son çözümü iyileştir
    print("\nFinal solution improvement...")
    best_solution = k_opt_improvement(best_solution, instance_data, maps_handler, k=2)
    
    # Sonuçları raporla
    final_routes = split_into_routes(best_solution)
    if final_routes is None:
        print("Failed to split solution into valid routes")
        return None
    
    print(f"\nOptimization completed!")
    
    # Toplam mesafe ve yükseklik bazlı maliyet hesaplaması
    total_distance = calculate_total_distance(final_routes)
    
    # Yükseklik bazlı toplam maliyet
    total_elevation_cost = 0
    for route in final_routes:
        prev_point = (
            instance_data['depart']['coordinates']['x'],
            instance_data['depart']['coordinates']['y']
        )
        
        route_load = 0
        for customer_id in route:
            route_load += float(instance_data[f'C_{customer_id}']['demand'])
            current_point = (
                instance_data[f'C_{customer_id}']['coordinates']['x'],
                instance_data[f'C_{customer_id}']['coordinates']['y']
            )
            
            vehicle_mass = 10000 + (route_load * 100)
            segment_cost = maps_handler.get_route_cost(prev_point, current_point, vehicle_mass)
            if segment_cost != float('inf'):
                total_elevation_cost += segment_cost
            
            prev_point = current_point
        
        # Depoya dönüş
        depot_point = (
            instance_data['depart']['coordinates']['x'],
            instance_data['depart']['coordinates']['y']
        )
        return_cost = maps_handler.get_route_cost(prev_point, depot_point, vehicle_mass)
        if return_cost != float('inf'):
            total_elevation_cost += return_cost
    
    print(f"Final solution: {len(final_routes)} vehicles")
    print(f"Total distance: {total_distance:.2f} km")
    print(f"Total elevation-based cost: {total_elevation_cost:.2f}")
    
    # Önbelleği temizle
    solution_cache.clear()
    
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

def generate_neighbors(solution, method="swap", num_neighbors=5):
    """Optimize edilmiş komşuluk üretimi"""
    neighbors = []
    size = len(solution)
    
    if method == "swap":
        # Daha az ve daha etkili komşular üret
        # Yakın noktaları değiştirmeye öncelik ver
        pairs = []
        
        # Yakın komşular (daha etkili)
        for i in range(size-1):
            for j in range(i+1, min(i+5, size)):
                pairs.append((i, j))
        
        # Birkaç rastgele uzak komşu
        for _ in range(min(5, size // 2)):
            i = random.randint(0, size-2)
            j = random.randint(i+5, size-1) if i+5 < size else random.randint(0, max(0, i-1))
            pairs.append((i, j))
        
        # Karıştır ve sınırla
        random.shuffle(pairs)
        for i, j in pairs[:num_neighbors]:
            neighbor = solution.copy()
            neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
            neighbors.append(neighbor)
    
    elif method == "insert":
        # Daha az ve daha etkili ekleme komşuları
        moves = []
        
        # Yakın taşıma işlemleri
        for i in range(size):
            # Yakın pozisyonlara taşı
            for offset in [-2, -1, 1, 2]:
                j = i + offset
                if 0 <= j < size and i != j:
                    moves.append((i, j))
        
        # Birkaç rastgele uzak taşıma
        for _ in range(min(5, size // 2)):
            i = random.randint(0, size-1)
            j = random.randint(0, size-1)
            if abs(i-j) > 3 and i != j:
                moves.append((i, j))
        
        # Karıştır ve sınırla
        random.shuffle(moves)
        for i, j in moves[:num_neighbors]:
            neighbor = solution.copy()
            value = neighbor.pop(i)
            neighbor.insert(j if j < i else j-1, value)
            neighbors.append(neighbor)
    
    elif method == "2-opt":
        # Daha az ve daha etkili 2-opt komşuları
        segments = []
        
        # Kısa segmentler (daha etkili)
        for i in range(1, size-2):
            for length in range(2, min(5, size-i)):
                segments.append((i, i+length))
        
        # Birkaç rastgele uzun segment
        for _ in range(min(3, size // 3)):
            i = random.randint(1, size-5)
            length = random.randint(5, min(10, size-i))
            segments.append((i, i+length))
        
        # Karıştır ve sınırla
        random.shuffle(segments)
        for i, j in segments[:num_neighbors]:
            neighbor = solution.copy()
            neighbor[i:j] = reversed(neighbor[i:j])
            neighbors.append(neighbor)
    
    elif method == "reverse":
        # Daha az ve daha etkili segment ters çevirme
        segments = []
        
        # Kısa segmentler
        for i in range(size-3):
            segments.append((i, i+3))
        
        # Orta segmentler
        for _ in range(min(5, size // 2)):
            i = random.randint(0, size-5)
            length = random.randint(4, min(7, size-i))
            segments.append((i, i+length))
        
        # Karıştır ve sınırla
        random.shuffle(segments)
        for i, j in segments[:num_neighbors]:
            neighbor = solution.copy()
            neighbor[i:j] = reversed(neighbor[i:j])
            neighbors.append(neighbor)
    
    return neighbors