from database import SessionLocal
from models import Customer, Company
from datetime import datetime
import random

def calculate_desi(demand):
    """Talep miktarına göre desi değerini hesapla"""
    # Örnek bir hesaplama: Talep * (1.2 ile 1.8 arası rastgele bir çarpan)
    # Bu gerçek dünyada ürünün boyutlarına göre değişecektir
    multiplier = random.uniform(1.2, 1.8)
    return round(float(demand) * multiplier, 2)

def seed_ankara_customers():
    db = SessionLocal()
    try:
        # Route Optimization şirketini bul
        company = db.query(Company).filter_by(name="Route Optimization A.Ş.").first()
        if not company:
            print("❌ Route Optimization şirketi bulunamadı!")
            return

        # Ankara müşterilerini oku ve ekle
        with open('data/ankara.txt', 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith(('ANKARA', 'VEHICLE', 'CUSTOMER', 'CUST NO.', '#')):
                    continue

                values = line.split()
                if len(values) >= 4:
                    try:
                        cust_id = int(values[0])
                        if cust_id == 0:  # Depo noktasını atla
                            continue
                            
                        # Müşteri adını ve notları ayır
                        comment = ' '.join(values[4:]).strip('# ') if len(values) > 4 else ''
                        
                        # Desi değerini hesapla
                        demand = float(values[3])
                        desi = calculate_desi(demand)
                        
                        # Yeni müşteri oluştur
                        customer = Customer(
                            company_id=company.id,
                            name=f"Ankara Müşteri {cust_id} - {comment}",
                            address=comment,
                            latitude=float(values[1]),
                            longitude=float(values[2]),
                            contact_person="İletişim Kişisi",
                            contact_phone="(312) XXX-XXXX",
                            email=f"musteri{cust_id}@example.com",
                            priority=5,  # Orta öncelik
                            notes=f"Talep: {demand} birim",
                            desi=desi,  # Hesaplanan desi değeri
                            created_at=datetime.now(),
                            updated_at=datetime.now()
                        )
                        db.add(customer)
                        print(f"✅ Müşteri eklendi: {customer.name} (Talep: {demand} birim, Desi: {desi})")
                        
                    except (ValueError, IndexError) as e:
                        print(f"❌ Hata: Satır işlenemedi: {line}")
                        print(f"Hata detayı: {str(e)}")
                        continue

        db.commit()
        print("\n✅ Ankara müşterileri başarıyla eklendi!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Hata oluştu: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_ankara_customers() 