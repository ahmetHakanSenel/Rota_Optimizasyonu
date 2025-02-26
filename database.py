from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager
import os
from dotenv import load_dotenv
import urllib.parse

# .env dosyasını yükle
load_dotenv()

# Veritabanı bağlantı bilgileri - pgAdmin'den alınan bilgiler
DB_USER = "postgres"
DB_PASSWORD = "postgres123"  # Şifreyi postgres123 olarak güncelliyoruz
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "route_optimization"

# Bağlantı URL'si
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Engine oluştur
engine = create_engine(
    DATABASE_URL,
    echo=True
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base class
Base = declarative_base()

# Database session context manager
@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Bağlantı testi
def test_connection():
    try:
        with get_db() as db:
            result = db.execute(text("SELECT 1"))
            print("✅ Veritabanı bağlantısı başarılı!")
            return True
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")
        return False

if __name__ == "__main__":
    test_connection()