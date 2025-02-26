from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Date, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum
from datetime import datetime

# Enum sınıfları
class UserRole(enum.Enum):
    ADMIN = "admin"
    COMPANY_ADMIN = "company_admin"
    DRIVER = "driver"
    EMPLOYEE = "employee"

class VehicleStatus(enum.Enum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    INACTIVE = "inactive"

class RouteStatus(enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

# Model sınıfları
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    company_employee = relationship("CompanyEmployee", back_populates="user")
    driver = relationship("Driver", back_populates="user")

class Company(Base):
    __tablename__ = 'companies'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    tax_number = Column(String(50), unique=True)
    address = Column(Text)
    phone = Column(String(20))
    email = Column(String(255))
    max_vehicles = Column(Integer, default=10)
    max_users = Column(Integer, default=50)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    employees = relationship("CompanyEmployee", back_populates="company")
    warehouses = relationship("Warehouse", back_populates="company", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="company")
    drivers = relationship("Driver", back_populates="company")
    customers = relationship("Customer", back_populates="company")

class CompanyEmployee(Base):
    __tablename__ = 'company_employees'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    department = Column(String(100))
    position = Column(String(100))
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    company = relationship("Company", back_populates="employees")
    user = relationship("User", back_populates="company_employee")

class Warehouse(Base):
    __tablename__ = 'warehouses'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    name = Column(String(255), nullable=False)
    address = Column(Text)
    latitude = Column(Float(precision=8))
    longitude = Column(Float(precision=8))
    capacity = Column(Float)
    is_active = Column(Boolean, default=True)
    contact_person = Column(String(100))
    contact_phone = Column(String(20))
    operating_hours = Column(String(100))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    company = relationship("Company", back_populates="warehouses")
    routes = relationship("Route", back_populates="warehouse")

class Vehicle(Base):
    __tablename__ = 'vehicles'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    driver_id = Column(Integer, ForeignKey('drivers.id'), nullable=True)
    plate_number = Column(String(20), unique=True)
    brand = Column(String(100))
    model = Column(String(100))
    year = Column(Integer)
    capacity = Column(Float)
    status = Column(Enum(VehicleStatus), default=VehicleStatus.ACTIVE)
    last_maintenance_date = Column(Date)
    next_maintenance_date = Column(Date)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    company = relationship("Company", back_populates="vehicles")
    routes = relationship("Route", back_populates="vehicle")
    maintenance_logs = relationship("MaintenanceLog", back_populates="vehicle")
    driver = relationship("Driver", back_populates="vehicle")

class Driver(Base):
    __tablename__ = 'drivers'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    company_id = Column(Integer, ForeignKey('companies.id'))
    license_number = Column(String(50))
    license_type = Column(String(50))
    license_expiry_date = Column(Date)
    total_experience_years = Column(Integer)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    user = relationship("User", back_populates="driver")
    company = relationship("Company", back_populates="drivers")
    routes = relationship("Route", back_populates="driver")
    vehicle = relationship("Vehicle", back_populates="driver", uselist=False)

class Customer(Base):
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    name = Column(String(255), nullable=False)
    address = Column(Text)
    latitude = Column(Float(precision=8))
    longitude = Column(Float(precision=8))
    contact_person = Column(String(100))
    contact_phone = Column(String(20))
    email = Column(String(255))
    priority = Column(Integer, default=0)
    notes = Column(Text)
    desi = Column(Float, default=0)  # Kargo desi değeri
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    company = relationship("Company", back_populates="customers")
    route_details = relationship("RouteDetail", back_populates="customer")

class Route(Base):
    __tablename__ = 'routes'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'))
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'))
    driver_id = Column(Integer, ForeignKey('drivers.id'))
    status = Column(Enum(RouteStatus), default=RouteStatus.PLANNED)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    total_distance = Column(Float)
    total_duration = Column(Integer)  # dakika cinsinden
    total_demand = Column(Float)  # toplam yük
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    company = relationship("Company")
    warehouse = relationship("Warehouse", back_populates="routes")
    vehicle = relationship("Vehicle", back_populates="routes")
    driver = relationship("Driver", back_populates="routes")
    route_details = relationship("RouteDetail", back_populates="route", order_by="RouteDetail.sequence_number")

class RouteDetail(Base):
    __tablename__ = 'route_details'
    
    id = Column(Integer, primary_key=True)
    route_id = Column(Integer, ForeignKey('routes.id'))
    customer_id = Column(Integer, ForeignKey('customers.id'))
    sequence_number = Column(Integer)
    planned_arrival_time = Column(DateTime)
    actual_arrival_time = Column(DateTime)
    planned_departure_time = Column(DateTime)
    actual_departure_time = Column(DateTime)
    demand = Column(Float)  # müşterinin yük miktarı
    status = Column(String(50))  # pending, completed, failed, skipped
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # İlişkiler
    route = relationship("Route", back_populates="route_details")
    customer = relationship("Customer", back_populates="route_details")

class MaintenanceLog(Base):
    __tablename__ = 'maintenance_logs'
    
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'))
    maintenance_type = Column(String(100))
    description = Column(Text)
    cost = Column(Float)
    service_provider = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)
    next_maintenance_date = Column(Date)
    created_at = Column(DateTime, default=func.now())

    # İlişkiler
    vehicle = relationship("Vehicle", back_populates="maintenance_logs") 