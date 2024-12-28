# Gerçek Yol Mesafeleri ile Araç Rotalama Problemi (VRP)

## 📋 İçindekiler
- [Genel Bakış](#genel-bakış)
- [Sistem Gereksinimleri](#sistem-gereksinimleri)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [API Endpoints](#api-endpoints)
- [Teknik Detaylar](#teknik-detaylar)
- [Desteklenen Şehirler](#desteklenen-şehirler)
- [Sorun Giderme](#sorun-giderme)
- [Katkıda Bulunma](#katkıda-bulunma)

## 🎯 Genel Bakış
Bu uygulama, lojistik ve dağıtım operasyonları için optimize edilmiş rota planlaması sağlar. OpenStreetMap (OSRM) üzerinden gerçek yol mesafelerini kullanarak çözüm üretir ve GraphHopper ile detaylı navigasyon imkanı sunar. Çözüm, adaptif komşuluk yapıları içeren geliştirilmiş bir Tabu Arama algoritmasına dayanmaktadır.

### 🌟 Temel Özellikler
- Gerçek zamanlı trafik verilerine dayalı rota optimizasyonu
- Çoklu araç desteği
- Kapasite kısıtlamaları
- Zaman penceresi kısıtlamaları
- Dinamik rota güncellemeleri
- Web tabanlı görselleştirme
- REST API desteği

## 💻 Sistem Gereksinimleri
- Python 3.8 veya üzeri
- 4GB RAM (minimum)
- Internet bağlantısı (OSRM servisleri için)
- Linux, Windows veya macOS işletim sistemi

## 🚀 Kurulum

### 1. Projeyi İndirin
```bash
git clone https://github.com/kullanici/vrp-project.git
cd vrp-project
```

### 2. Sanal Ortam Oluşturun
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# veya
venv\Scripts\activate  # Windows
```

### 3. Gereksinimleri Yükleyin
```bash
pip install -r requirements.txt
```

## 📱 Kullanım

### Web Arayüzü ile Kullanım
1. Sunucuyu başlatın:
```bash
python app.py
```
2. Tarayıcınızda `http://localhost:5000` adresine gidin
3. Şehir seçin ve parametreleri ayarlayın
4. "Optimize Et" butonuna tıklayın

### API ile Kullanım
```python
import requests

data = {
    "instance_name": "istanbul",
    "num_customers": 15,
    "vehicle_capacity": 500
}

response = requests.post('http://localhost:5000/api/optimize', json=data)
routes = response.json()
```

## 🔌 API Endpoints

### `POST /api/optimize`
Rota optimizasyonu için kullanılır.

#### İstek Parametreleri
```json
{
    "instance_name": "istanbul",
    "num_customers": 15,
    "vehicle_capacity": 500
}
```

#### Başarılı Yanıt
```json
{
    "success": true,
    "routes": [...],
    "vehicle_capacity": 500
}
```

### `GET /api/instances`
Mevcut problem örneklerini listeler.

## 🔧 Teknik Detaylar

### Bileşenler
1. **Veri İşleme** (`process_data.py`)
   - Problem örneklerini yükler ve doğrular
   - OSRM API ile gerçek mesafeleri hesaplar
   - Mesafe matrislerini önbellekler
   - GraphHopper navigasyon bağlantıları oluşturur

2. **Temel Fonksiyonlar** (`core_funs.py`)
   - Adaptif komşuluk üretimi
   - Paralel çözüm değerlendirmesi
   - Mesafe hesaplamaları
   - Çözüm çeşitlendirme stratejileri

3. **Algoritma** (`alg_creator.py`)
   - Tabu Arama implementasyonu
   - Adaptif parametre ayarlama
   - Çoklu komşuluk yapıları
   - Çözüm izleme ve iyileştirme

### Algoritma Parametreleri
| Parametre | Açıklama | Varsayılan Değer |
|-----------|----------|------------------|
| `individual_size` | Teslimat noktası sayısı | 15 |
| `pop_size` | Başlangıç popülasyon büyüklüğü | 100 |
| `n_gen` | Maksimum iterasyon sayısı | 1200 |
| `tabu_size` | Tabu listesi boyutu | 45 |
| `stagnation_limit` | Çeşitlendirme eşiği | 40 |

### Komşuluk Yapıları
1. **Takas (Swap)**
   - İki nokta arasında yer değiştirme
   - Kompleksite: O(n²)

2. **Ekleme (Insert)**
   - Bir noktayı farklı bir konuma taşıma
   - Kompleksite: O(n)

3. **Ters Çevirme (Reverse)**
   - Rota segmentini tersine çevirme
   - Kompleksite: O(n)

4. **Karıştırma (Scramble)**
   - Rota segmentini rastgele karıştırma
   - Kompleksite: O(n log n)

## 🌍 Desteklenen Şehirler
| Şehir | Veri Seti | Müşteri Sayısı |
|-------|-----------|----------------|
| İstanbul | istanbul.txt | 100 |
| Ankara | ankara.txt | 75 |
| İzmir | izmir.txt | 50 |
| Bursa | bursa.txt | 40 |
| Tokat | tokat.txt | 30 |

## 🔍 Sorun Giderme

### Sık Karşılaşılan Hatalar
1. **OSRM Bağlantı Hatası**
   ```
   Çözüm: Internet bağlantınızı kontrol edin veya yerel OSRM sunucusu kurun
   ```

2. **Bellek Yetersizliği**
   ```
   Çözüm: Müşteri sayısını azaltın veya sistem RAM'ini artırın
   ```

3. **Çözüm Bulunamadı**
   ```
   Çözüm: Araç kapasitesini artırın veya müşteri taleplerini kontrol edin
   ```

## 🤝 Katkıda Bulunma
1. Bu depoyu fork edin
2. Yeni bir branch oluşturun (`git checkout -b feature/yeniOzellik`)
3. Değişikliklerinizi commit edin (`git commit -am 'Yeni özellik: X'`)
4. Branch'inizi push edin (`git push origin feature/yeniOzellik`)
5. Pull Request oluşturun

### Kod Stili
- PEP 8 kurallarına uyun
- Fonksiyonlarınıza docstring ekleyin
- Değişken isimlerini Türkçe karakterler kullanmadan yazın
