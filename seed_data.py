from datetime import datetime, date
from database import SessionLocal, engine
from models import User, Company, CompanyEmployee, Vehicle, Driver, Warehouse, VehicleStatus, UserRole
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

def seed_data():
    db = SessionLocal()
    try:
        # Admin kullanıcısı oluştur
        admin_user = User(
            email="admin@routeopt.com",
            password_hash=generate_password_hash("admin123"),
            role=UserRole.ADMIN,
            first_name="System",
            last_name="Admin",
            phone="5551234567",
            is_active=True,
            last_login=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(admin_user)
        db.flush()

        # Şirket yöneticisi kullanıcısı oluştur
        company_admin = User(
            email="manager@routeopt.com",
            password_hash=generate_password_hash("manager123"),
            role=UserRole.COMPANY_ADMIN,
            first_name="Şirket",
            last_name="Yöneticisi",
            phone="5551234568",
            is_active=True,
            last_login=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(company_admin)
        db.flush()

        # Şirket oluştur
        company = Company(
            name="Route Optimization A.Ş.",
            tax_number="1234567890",
            address="Kızılay, Ankara",
            phone="3121234567",
            email="info@routeopt.com",
            max_vehicles=50,
            max_users=100,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(company)
        db.flush()

        # Admin kullanıcısını şirket çalışanı olarak ekle
        company_employee = CompanyEmployee(
            company_id=company.id,
            user_id=admin_user.id,
            department="Yönetim",
            position="Sistem Yöneticisi",
            is_admin=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(company_employee)

        # Şirket yöneticisini şirket çalışanı olarak ekle
        company_manager = CompanyEmployee(
            company_id=company.id,
            user_id=company_admin.id,
            department="Yönetim",
            position="Şirket Müdürü",
            is_admin=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(company_manager)

        # Depo oluştur (Kızılay merkez)
        warehouse = Warehouse(
            company_id=company.id,
            name="Kızılay Merkez Depo",
            address="Kızılay Meydanı, Çankaya/Ankara",
            latitude=39.9334,
            longitude=32.8597,
            capacity=10000,
            is_active=True,
            contact_person="Ahmet Depo",
            contact_phone="5551234568",
            operating_hours="08:00-18:00",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(warehouse)

        # Araçlar oluştur
        vehicles = [
            Vehicle(
                company_id=company.id,
                plate_number=f"06ABC{i:02d}",
                brand="Ford",
                model="Transit",
                year=2023,
                capacity=500,
                status=VehicleStatus.ACTIVE,
                last_maintenance_date=date(2024, 1, 1),
                next_maintenance_date=date(2024, 7, 1),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            for i in range(1, 6)  # 5 araç oluştur
        ]
        for vehicle in vehicles:
            db.add(vehicle)
        db.flush()

        # Şoförler için kullanıcılar oluştur
        driver_users = [
            User(
                email=f"driver{i}@routeopt.com",
                password_hash=generate_password_hash(f"driver{i}123"),
                role=UserRole.DRIVER,
                first_name=f"Şoför",
                last_name=f"Soyad {i}",
                phone=f"555123456{i}",
                is_active=True,
                last_login=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            for i in range(1, 6)  # 5 şoför oluştur
        ]
        for user in driver_users:
            db.add(user)
        db.flush()

        # Şoförler oluştur
        drivers = [
            Driver(
                user_id=driver_users[i].id,
                company_id=company.id,
                license_number=f"S{i:05d}",
                license_type="B",
                license_expiry_date=date(2026, 1, 1),
                total_experience_years=5,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            for i in range(5)
        ]
        for driver in drivers:
            db.add(driver)

        db.commit()
        print("✅ Test verileri başarıyla eklendi!")

    except Exception as e:
        db.rollback()
        print(f"❌ Hata oluştu: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data() 