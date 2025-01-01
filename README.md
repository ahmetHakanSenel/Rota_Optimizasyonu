# Araç Rota Optimizasyonu

Tabu Arama algoritması kullanarak gerçek yol mesafelerine dayalı araç rota optimizasyonu yapan web uygulaması.

## Özellikler

- Gerçek yol mesafelerini kullanarak rota optimizasyonu (OpenStreetMap verileri)
- Araç kapasitesi kısıtlaması
- Çoklu araç desteği
- İnteraktif harita görselleştirmesi
- Rota detayları (mesafe, süre, duraklar)

## Gereksinimler

- Python 3.8+
- Flask
- OSRM Sunucusu (yerel veya uzak)
- Modern web tarayıcısı

## Kurulum

1. Depoyu klonlayın:
```bash
git clone [repo-url]
```

2. Gerekli Python paketlerini yükleyin:
```bash
pip install -r requirements.txt
```

## Çalıştırma

1. OSRM sunucusunun çalıştığından emin olun

2. Flask uygulamasını başlatın:
```bash
python run.py
```

3. Web tarayıcısında açın:
```
http://localhost:5000
```

## Kullanım

1. Şehir seçin
2. Müşteri sayısını belirleyin (5-25 arası)
3. Araç kapasitesini ayarlayın
4. "Rota Oluştur" butonuna tıklayın
5. Optimizasyon sonuçlarını harita üzerinde görüntüleyin

## Teknik Detaylar

- OSRM Table Service: Tüm noktalar arası mesafe matrisi hesaplama
- OSRM Route Service: Detaylı rota bilgisi ve görselleştirme
- Tabu Arama: Adaptif tabu listesi boyutu ve çeşitli komşuluk yapıları
- Paralel işleme ile performans optimizasyonu
