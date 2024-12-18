from core_funs import *
import collections
import random
from process_data import OSRMHandler, ProblemInstance
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

class AdaptiveTabuList:
    """Adaptif Tabu Listesi sınıfı"""
    def __init__(self, initial_size, max_size):
        self.max_size = max_size  # Maksimum liste boyutu
        self.list = collections.deque(maxlen=initial_size)  # Tabu listesi
        self.frequency = {}  # Çözüm frekansları
        self.current_size = initial_size  # Mevcut liste boyutu
        self.best_known = float('inf')  # En iyi bilinen çözüm değeri
        self.elite_solutions = []  # En iyi çözümlerin listesi
    
    def add(self, solution):
        """Çözümü tabu listesine ekle"""
        solution_tuple = tuple(solution)  # Çözümü tuple'a çevir
        self.list.append(solution_tuple)  # Listeye ekle
        self.frequency[solution_tuple] = self.frequency.get(solution_tuple, 0) + 1  # Frekansı güncelle
        
        # Liste boyutunu güncelle
        if len(self.list) >= self.current_size:
            self.current_size = min(self.current_size + 1, self.max_size)
    
    def contains(self, solution, aspiration_value=None, current_best=float('inf')):
        """Çözümün tabu listesinde olup olmadığını kontrol et"""
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
        if self.frequency.get(solution_tuple, 0) > 3:  # 3'ten fazla tekrar
            return True
        
        # Son N çözümde varsa yasakla
        recent_solutions = list(self.list)[-5:]  # Son 5 çözüm
        if solution_tuple in recent_solutions:
            return True
        
        return False
    
    def clear(self):
        """Tabu listesini temizle ama elit çözümleri koru"""
        self.list.clear()  # Listeyi temizle
        self.frequency.clear()  # Frekansları sıfırla
        self.current_size = len(self.list)  # Boyutu güncelle
        
        # En iyi çözümleri geri yükle
        if self.elite_solutions:
            best_elite = min(self.elite_solutions, key=lambda x: x[1])
            self.best_known = best_elite[1]

def run_tabu_search(instance_name, individual_size, pop_size, n_gen, tabu_size, 
                    plot=False, stagnation_limit=50, verbose=True, 
                    use_real_distances=True):
    """Geliştirilmiş Tabu Arama algoritması"""
    # Problem verilerini yükle
    problem_instance = ProblemInstance(instance_name)
    instance = problem_instance.get_data()
    
    if instance is None:
        return None
    
    # OSRM handler'ı başlat
    maps_handler = OSRMHandler()
    
    # Değişkenleri başlat
    best_solution = None  # En iyi çözüm
    best_distance = float('inf')  # En iyi mesafe
    last_best_distance = float('inf')  # Son en iyi mesafe
    same_value_counter = 0  # Aynı değerde kalma sayacı
    
    # Başlangıç parametreleri
    current_tabu_size = tabu_size  # Mevcut tabu listesi boyutu
    current_max_neighbors = 15  # Mevcut maksimum komşu sayısı
    current_stagnation_limit = stagnation_limit  # Mevcut durağanlık limiti
    
    # Komşuluk yöntemleri ve ağırlıkları
    neighborhood_methods = {
        "swap": 0.2,      # Basit değişimler
        "insert": 0.2,    # Nokta taşıma
        "reverse": 0.15,  # Segment çevirme
        "scramble": 0.15, # Segment karıştırma
        "block_move": 0.15, # Blok taşıma
        "cross": 0.15     # Çapraz değişim
    }
    
    # Tabu listesini başlat
    tabu_list = AdaptiveTabuList(current_tabu_size, current_tabu_size * 2)
    stagnation_counter = 0  # Durağanlık sayacı
    
    # Başlangıç çözümünü oluştur
    current_solution = create_initial_solution(instance, individual_size, maps_handler)
    current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
    
    print("Starting Tabu Search optimization...")
    print(f"Parameters: generations={n_gen}, tabu_size={tabu_size}, stagnation_limit={stagnation_limit}")
    
    # Ana döngü
    for iteration in range(n_gen):
        print(f"\nIteration {iteration}:")
        
        # Durağanlık kontrolü
        if stagnation_counter >= current_stagnation_limit:
            print("Stagnation detected! Diversifying solution...")
            current_solution = diversify_solution(current_solution)  # Çözümü çeşitlendir
            current_distance = evaluate_solution_with_real_distances(current_solution, instance, maps_handler)
            print(f"New diversified solution distance: {current_distance:.2f} km")
            stagnation_counter = 0
            tabu_list.clear()
            
            # Komşuluk ağırlıklarını güncelle
            if iteration > n_gen // 2:  # İkinci yarıda daha agresif ol
                neighborhood_methods["reverse"] = 0.2
                neighborhood_methods["scramble"] = 0.2
                neighborhood_methods["block_move"] = 0.2
                neighborhood_methods["swap"] = 0.15
                neighborhood_methods["insert"] = 0.15
                neighborhood_methods["cross"] = 0.1
        
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
                    improvement = ((best_distance - best_neighbor_distance) / best_distance) * 100
                    print(f"New best solution found! Improvement: {improvement:.2f}%")
                    best_solution = best_neighbor.copy()
                    best_distance = best_neighbor_distance
                    stagnation_counter = 0
                    
                    # İyileştirme durumunda başarılı yönteme daha fazla ağırlık ver
                    for method in neighborhood_methods:
                        if method in str(best_neighbor):  # Basit kontrol
                            neighborhood_methods[method] = min(0.3, neighborhood_methods[method] + 0.05)
                            # Diğer ağırlıkları normalize et
                            total = sum(neighborhood_methods.values())
                            for m in neighborhood_methods:
                                if m != method:
                                    neighborhood_methods[m] *= (1 - neighborhood_methods[method]) / (total - neighborhood_methods[method])
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
            # Parametreleri rastgele ayarla
            current_tabu_size = max(5, min(30, current_tabu_size + random.randint(-3, 5)))
            current_max_neighbors = max(10, min(30, current_max_neighbors + random.randint(-3, 5)))
            current_stagnation_limit = max(15, min(50, current_stagnation_limit + random.randint(-5, 8)))
            
            print(f"New parameters - Tabu size: {current_tabu_size}, "
                  f"Max neighbors: {current_max_neighbors}, "
                  f"Stagnation limit: {current_stagnation_limit}")
            
            # Tabu listesini yenile
            tabu_list = AdaptiveTabuList(current_tabu_size, current_tabu_size * 2)
            same_value_counter = 0
        
        print(f"\nCurrent best distance: {best_distance:.2f} km")
        print(f"Stagnation counter: {stagnation_counter}")
    
    print("\nOptimization completed!")
    print(f"Final best distance: {best_distance:.2f} km")
    print(f"Final solution: {best_solution}")
    
    return decode_solution(best_solution, instance) if best_solution else None

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Gerçek yol mesafelerini kullanarak çözümü değerlendir"""
    total_distance = 0  # Toplam mesafe
    previous_point = (  # Başlangıç noktası (depo)
        instance[DEPART][COORDINATES][X_COORD],
        instance[DEPART][COORDINATES][Y_COORD]
    )
    
    try:
        # Ardışık noktalar arası mesafeleri hesapla
        for customer_id in solution:
            current_point = (  # Mevcut müşteri koordinatları
                instance[f'C_{customer_id}'][COORDINATES][X_COORD],
                instance[f'C_{customer_id}'][COORDINATES][Y_COORD]
            )
            
            # OSRM'den mesafeyi al
            leg_distance = map_handler.get_distance(previous_point, current_point)
            if leg_distance == float('inf'):  # Mesafe hesaplanamazsa
                return float('inf')
            
            total_distance += leg_distance  # Toplam mesafeye ekle
            previous_point = current_point  # Sonraki hesaplama için güncelle
        
        # Depoya dönüş mesafesini ekle
        depot_point = (  # Depo koordinatları
            instance[DEPART][COORDINATES][X_COORD],
            instance[DEPART][COORDINATES][Y_COORD]
        )
        final_leg = map_handler.get_distance(previous_point, depot_point)  # Son mesafe
        if final_leg == float('inf'):  # Mesafe hesaplanamazsa
            return float('inf')
        
        total_distance += final_leg  # Toplam mesafeye ekle
        return total_distance
        
    except Exception as e:
        print(f"Error calculating route: {str(e)}")
        return float('inf')

def create_initial_solution(instance, size, map_handler):
    """Başlangıç çözümü oluştur"""
    print("\nCreating initial solution...")
    
    # Basit sıralı çözüm oluştur
    solution = list(range(1, size + 1))  # 1'den size'a kadar sayılar
    random.shuffle(solution)  # Rastgele karıştır
    
    print(f"Initial solution created: {solution}")
    initial_distance = evaluate_solution_with_real_distances(solution, instance, map_handler)
    print(f"Initial solution distance: {initial_distance:.2f} km\n")
    
    return solution

def decode_solution(solution, instance):
    """Çözümü rota formatına dönüştür"""
    return [solution]  # Tek araçlı rota