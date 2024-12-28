# Gerçek Yol Mesafeleri ile Araç Rotalama Problemi (VRP)

## 📋 Proje Yapısı

```
.
├── app.py                 # Flask web uygulaması
├── alg_creator.py         # Tabu arama algoritması
├── core_funs.py          # Temel fonksiyonlar
├── process_data.py       # Veri işleme ve OSRM entegrasyonu
├── data/                 # Problem örnekleri
└── templates/            # Web arayüzü şablonları
```

## 🎯 Genel Bakış
Bu proje, araç rotalama problemini çözmek için geliştirilmiş bir optimizasyon sistemidir. OpenStreetMap üzerinden gerçek yol mesafelerini kullanarak, çoklu araç ve kapasite kısıtlamaları altında optimal rotalar üretir.

## 💻 Temel Bileşenler ve İşleyiş

### 1. Veri İşleme (`process_data.py`)
Problem verilerinin yüklenmesi ve işlenmesinden sorumlu ana sınıf:

```python
class ProblemInstance:
    def __init__(self, instance_name, force_recalculate=False):
        self.instance_name = instance_name
        self.cache = {}
        self.data = None
        
    def load_data(self):
        # Veri dosyasını okur ve parse eder
        
    def calculate_distances(self):
        # OSRM API ile gerçek mesafeleri hesaplar
        
    def get_data(self):
        # İşlenmiş veri setini döndürür
```

### 2. Algoritma Çekirdeği (`core_funs.py`)
Temel optimizasyon fonksiyonlarını içerir:

```python
def calculate_total_distance(route, distance_matrix):
    """Toplam rota mesafesini hesaplar"""
    
def check_capacity_constraint(route, demands, capacity):
    """Kapasite kısıtlamalarını kontrol eder"""
    
def generate_neighbor(current_solution, neighborhood_type):
    """Komşu çözüm üretir"""
    
class Solution:
    def __init__(self, routes, distance, capacity_violations):
        self.routes = routes
        self.total_distance = distance
        self.violations = capacity_violations
```

### 3. Tabu Arama Algoritması (`alg_creator.py`)
Ana optimizasyon algoritmasını içerir:

```python
class TabuSearch:
    def __init__(self, distance_matrix, demands, capacity):
        self.distance_matrix = distance_matrix
        self.demands = demands
        self.capacity = capacity
        self.tabu_list = []
        
    def run(self, max_iterations):
        """Ana tabu arama döngüsü"""
        
    def evaluate_solution(self, solution):
        """Çözüm kalitesini değerlendirir"""
```

#### Komşuluk Yapıları
1. **Takas (Swap)**: İki müşteri noktasının yerini değiştirir
```python
def swap_operator(route, i, j):
    route[i], route[j] = route[j], route[i]
    return route
```

2. **Ekleme (Insert)**: Bir müşteriyi farklı bir konuma taşır
```python
def insert_operator(route, source, target):
    customer = route.pop(source)
    route.insert(target, customer)
    return route
```

3. **Ters Çevirme (Reverse)**: Rota segmentini tersine çevirir
```python
def reverse_operator(route, start, end):
    route[start:end] = reversed(route[start:end])
    return route
```

### 4. Web Uygulaması (`app.py`)
Flask tabanlı web arayüzü:

```python
@app.route('/api/optimize', methods=['POST'])
def optimize_route():
    """
    1. İstek verilerini alır
    2. Problem örneğini yükler
    3. Tabu aramayı çalıştırır
    4. Sonuçları formatlar ve döndürür
    """
```

## 🔄 Veri Akışı

1. **Veri Yükleme**
   ```python
   instance = ProblemInstance("ornek1")
   data = instance.get_data()
   ```

2. **Mesafe Matrisi Oluşturma**
   ```python
   distances = instance.calculate_distances()
   ```

3. **Optimizasyon**
   ```python
   tabu = TabuSearch(distances, data['demands'], data['capacity'])
   solution = tabu.run(max_iterations=1000)
   ```

4. **Sonuç İşleme**
   ```python
   routes = solution.get_routes()
   total_distance = solution.get_total_distance()
   ```

## 🔧 Algoritma Detayları

### Tabu Arama Mekanizması
```python
def tabu_search(initial_solution):
    current = initial_solution
    best = current
    tabu_list = []
    
    while not stopping_condition():
        neighborhood = generate_neighbors(current)
        best_neighbor = None
        
        for neighbor in neighborhood:
            if (is_better(neighbor, best_neighbor) and 
                not is_tabu(neighbor, tabu_list)):
                best_neighbor = neighbor
                
        current = best_neighbor
        update_tabu_list(tabu_list, current)
        
        if is_better(current, best):
            best = current
            
    return best
```

### Çözüm Değerlendirme
Her çözüm şu kriterlere göre değerlendirilir:
1. Toplam mesafe
2. Kapasite kısıtı ihlalleri
3. Rota sayısı
