# Araç Rotalama Problemi Çözücü

## 📋 Proje Yapısı

```
├── app.py                 # Flask web uygulaması
├── alg_creator.py         # Tabu arama algoritması implementasyonu
├── core_funs.py          # Temel algoritma fonksiyonları
├── process_data.py       # Veri işleme ve OSRM entegrasyonu
├── data/                 # Şehir verileri
│   ├── istanbul.txt
│   ├── ankara.txt
│   └── ...
└── templates/           # Web arayüzü şablonları
    └── index.html
```

## 🔍 Temel Bileşenler

### 1. Veri İşleme (`process_data.py`)

#### ProblemInstance Sınıfı
- Singleton tasarım deseni kullanılarak problem verilerinin tek noktadan yönetimi
- Şehir verilerini yükleme ve önbellekleme
- Koordinat ve talep verilerini işleme

```python
class ProblemInstance:
    def __init__(self, problem_name=None, force_recalculate=False):
        self._data = self._load_problem_instance(problem_name, force_recalculate)
```

#### OSRMHandler Sınıfı
- OpenStreetMap ile gerçek mesafe hesaplamaları
- Mesafe matrisi önbellekleme
- HTTP isteklerinin yönetimi

```python
class OSRMHandler:
    def get_distance(self, origin, dest):
        # Önbellekten mesafe bilgisi getirme
        key = (tuple(origin), tuple(dest))
        return self.distance_matrix.get(key, float('inf'))
```

### 2. Algoritma Çekirdeği (`core_funs.py`)

#### Komşuluk Yapıları
1. **Swap (Değiştirme)**
   - İki nokta arasında konum değişimi
   - Yakın ve uzak noktalar için farklı stratejiler

2. **Insert (Ekleme)**
   - Bir noktayı farklı bir konuma taşıma
   - Akıllı konum seçimi

3. **Reverse (Ters Çevirme)**
   - Rota segmentlerini tersine çevirme
   - Farklı segment uzunlukları

4. **2-opt ve 3-opt**
   - Çapraz kenar değişimleri
   - Yerel optimizasyon

```python
def generate_neighbors(solution, method="swap", num_neighbors=5):
    if method == "swap":
        # Yakın noktaları değiştir
        for i in range(size-1):
            for j in range(i+1, min(i+5, size)):
                neighbor = solution.copy()
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
                neighbors.append(neighbor)
```

### 3. Tabu Arama Algoritması (`alg_creator.py`)

#### AdaptiveTabuList Sınıfı
- Dinamik tabu listesi boyutu
- Çözüm frekansı takibi
- Elit çözümlerin saklanması

```python
class AdaptiveTabuList:
    def contains(self, solution, aspiration_value=None):
        # Tabu durumunu ve istisna kriterlerini kontrol et
        if aspiration_value is not None and aspiration_value < self.best_known:
            return False
        return tuple(solution) in self.list
```

#### Algoritma Akışı
1. Başlangıç çözümü oluşturma
2. Komşu çözümler üretme
3. En iyi komşuyu seçme
4. Tabu listesi kontrolü
5. Çözümü güncelleme
6. Çeşitlendirme mekanizması

### 4. Web Arayüzü (`app.py`)

Flask tabanlı web uygulaması:
- REST API endpoints
- Gerçek zamanlı optimizasyon
- Harita görselleştirmesi
- Rota detayları

## 💡 Algoritma Mantığı

1. **Başlangıç Çözümü**
   - En yakın komşu
   - Açgözlü yaklaşım
   - Rastgele başlangıç

2. **Çözüm İyileştirme**
   - Adaptif komşuluk yapıları
   - Tabu mekanizması
   - Çeşitlendirme stratejileri

3. **Rota Bölme**
   - Kapasite kısıtlamaları
   - Araç sayısı optimizasyonu
   - Dengeli dağıtım

4. **Mesafe Hesaplama**
   - OSRM ile gerçek yol mesafeleri
   - Önbellekleme mekanizması
   - Hata yönetimi

## 🔧 Veri Formatı

Problem verileri aşağıdaki formatta tanımlanır:
```
ŞEHİR_ADI
VEHICLE
NUMBER     CAPACITY
25         500

CUSTOMER
CUST NO.  XCOORD.    YCOORD.    DEMAND   # COMMENT (Zorunlu değildir)
0         41.0370    28.9850    0        # Merkez
1         41.0280    28.9740    10       # Nokta 1
...
```
