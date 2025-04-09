from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, abort
from flask_cors import CORS
from alg_creator import run_tabu_search, split_into_routes
from database import SessionLocal
from models import User, Company, CompanyEmployee, Vehicle, Driver, Customer, Warehouse, UserRole, Route, RouteStatus, RouteDetail, VehicleStatus
from werkzeug.security import check_password_hash, generate_password_hash
import os
from functools import wraps
from sqlalchemy import func
import time
import random
from process_data import OSRMHandler
import traceback
from sqlalchemy.orm import joinedload

app = Flask(__name__, static_folder='static')
app.secret_key = os.urandom(24)  # Session için gerekli
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})  # CORS ayarları güncellendi

# Login gerektiren sayfalar için decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bu sayfaya erişmek için giriş yapmalısınız.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin gerektiren sayfalar için decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_role' not in session or session['user_role'] != 'admin':
            flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Şirket yöneticisi gerektiren sayfalar için decorator
def company_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_role' not in session or session['user_role'] != 'company_admin':
            flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Şoför gerektiren sayfalar için decorator
def driver_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_role' not in session or session['user_role'] != 'driver':
            flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = SessionLocal()
        try:
            email = request.form['email']
            password = request.form['password']
            
            user = db.query(User).filter_by(email=email).first()
            
            if user and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['user_email'] = user.email
                session['user_role'] = user.role.value
                
                if user.role == UserRole.COMPANY_ADMIN:
                    employee = db.query(CompanyEmployee).filter_by(user_id=user.id).first()
                    if employee:
                        session['company_id'] = employee.company_id
                
                user.last_login = func.now()
                db.commit()
                
                flash('Başarıyla giriş yaptınız!', 'success')
                
                # Kullanıcı rolüne göre yönlendirme
                if user.role == UserRole.ADMIN:
                    return redirect(url_for('admin_dashboard'))
                elif user.role == UserRole.COMPANY_ADMIN:
                    return redirect(url_for('company_dashboard'))
                elif user.role == UserRole.DRIVER:
                    return redirect(url_for('driver_dashboard'))
                else:
                    return redirect(url_for('index'))
            else:
                flash('Geçersiz email veya şifre!', 'danger')
        finally:
            db.close()
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Başarıyla çıkış yaptınız!', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/api/optimize', methods=['POST'])
def optimize_route():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = SessionLocal()
    try:
        data = request.json
        instance_name = data.get('instance_name', 'bursa')
        num_customers = int(data.get('num_customers', 10))
        vehicle_capacity = float(data.get('vehicle_capacity', 500))
        
        # Kullanıcının şirket bilgisini al
        if session['user_role'] == UserRole.COMPANY_ADMIN.value:
            employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
            if not employee:
                return jsonify({'error': 'Company information not found'}), 404
            company_id = employee.company_id
        elif session['user_role'] == UserRole.DRIVER.value:
            driver = db.query(Driver).filter_by(user_id=session['user_id']).first()
            if not driver:
                return jsonify({'error': 'Driver information not found'}), 404
            company_id = driver.company_id
        else:
            return jsonify({'error': 'Unauthorized role'}), 403
            
        # Şirketin aktif deposunu bul
        warehouse = db.query(Warehouse).filter_by(
            company_id=company_id,
            is_active=True
        ).first()
        
        if not warehouse:
            return jsonify({'error': 'No active warehouse found for this company'}), 404
            
        # Müşterileri al
        customers = db.query(Customer).filter_by(company_id=company_id).all()
        
        # Eğer müşteri yoksa hata döndür
        if len(customers) == 0:
            return jsonify({'error': 'No customers found for this company'}), 400
            
        # Eğer num_customers 0 ise, tüm müşterileri kullan
        if num_customers == 0:
            num_customers = len(customers)
            selected_customers = customers
        else:
            # Yeterli müşteri var mı kontrol et
            if len(customers) < num_customers:
                return jsonify({'error': f'Not enough customers. Company has {len(customers)} customers, but requested {num_customers} customers.'}), 400
            
            # Rastgele müşteri seç
            selected_customers = random.sample(customers, num_customers)
        
        # Problem instance verisi oluştur
        instance_data = {
            'instance_name': instance_name,
            'max_vehicle_number': 10,  # Maksimum araç sayısı
            'vehicle_capacity': vehicle_capacity,
            'depart': {
                'coordinates': {
                    'x': warehouse.latitude,
                    'y': warehouse.longitude
                },
                'demand': 0,
                'name': warehouse.name,
                'address': warehouse.address
            }
        }
        
        # Müşterileri ekle
        for i, customer in enumerate(selected_customers, 1):
            instance_data[f'C_{i}'] = {
                'coordinates': {
                    'x': customer.latitude,
                    'y': customer.longitude
                },
                'demand': customer.desi,
                'name': customer.name,
                'address': customer.address,
                'contact_person': customer.contact_person,
                'contact_phone': customer.contact_phone
            }
        
        # OSRM ile mesafe matrisini hesapla
        map_handler = OSRMHandler()
        if not map_handler.precompute_distances(instance_data):
            return jsonify({'error': 'Failed to compute distances'}), 500
        
        print("\nStarting Tabu Search optimization...")
        # Tabu Search algoritmasını çalıştır
        routes = run_tabu_search(
            instance_data=instance_data,
            individual_size=len(selected_customers),
            n_gen=1000,
            tabu_size=20,
            stagnation_limit=50,
            verbose=True,
            vehicle_capacity=vehicle_capacity
        )
        
        if not routes:
            print("No solution found from Tabu Search")
            return jsonify({'error': 'No feasible solution found. Try reducing the number of customers or increasing vehicle capacity.'}), 404
        
        print(f"\nFound solution with {len(routes)} routes")
        
        # Her alt rota için bir Route kaydı oluştur
        routes_response = []
        for sub_route_index, sub_route in enumerate(routes):
            print(f"\nProcessing route {sub_route_index + 1}: {sub_route}")
            
            # Müsait araç ve şoför bul
            available_driver = db.query(Driver).filter(
                Driver.company_id == company_id,
                ~Driver.id.in_(
                    db.query(Route.driver_id).filter(
                        Route.status.in_([RouteStatus.PLANNED, RouteStatus.IN_PROGRESS])
                    )
                )
            ).first()

            if not available_driver:
                print("No available driver found for this route.")
                return jsonify({'error': 'No available driver for the route.'}), 400

            # Önce şoförün atanmış aracını kontrol et
            available_vehicle = None
            if available_driver.vehicle:
                # Şoförün atanmış aracı müsait mi kontrol et
                vehicle_in_use = db.query(Route).filter(
                    Route.vehicle_id == available_driver.vehicle.id,
                    Route.status.in_([RouteStatus.PLANNED, RouteStatus.IN_PROGRESS])
                ).first()

                if not vehicle_in_use:
                    available_vehicle = available_driver.vehicle
                    print(f"Using driver's assigned vehicle: {available_vehicle.plate_number}")

            # Eğer şoförün aracı müsait değilse veya atanmış aracı yoksa, başka müsait araç bul
            if not available_vehicle:
                available_vehicle = db.query(Vehicle).filter(
                    Vehicle.company_id == company_id,
                    Vehicle.status == VehicleStatus.ACTIVE,
                    ~Vehicle.id.in_(
                        db.query(Route.vehicle_id).filter(
                            Route.status.in_([RouteStatus.PLANNED, RouteStatus.IN_PROGRESS])
                        )
                    )
                ).order_by(Vehicle.capacity.desc()).first()

                if not available_vehicle:
                    print("No available vehicle found for this route.")
                    return jsonify({'error': 'No available vehicle for the route.'}), 400

                # Şoförü bu araca ata
                available_vehicle.driver_id = available_driver.id

            # Toplam mesafe hesapla
            total_distance = 0
            prev_point = (warehouse.latitude, warehouse.longitude)
            
            # Müşteriler arası mesafeleri hesapla
            for customer_id in sub_route:
                customer = selected_customers[customer_id - 1]
                curr_point = (customer.latitude, customer.longitude)
                total_distance += map_handler.get_distance(prev_point, curr_point)
                prev_point = curr_point
            
            # Son noktadan depoya dönüş mesafesini ekle
            total_distance += map_handler.get_distance(prev_point, (warehouse.latitude, warehouse.longitude))

            # Yeni rotayı oluştur
            route = Route(
                company_id=company_id,
                warehouse_id=warehouse.id,
                vehicle_id=available_vehicle.id,
                driver_id=available_driver.id,
                status=RouteStatus.PLANNED,
                total_distance=total_distance,
                total_duration=int(total_distance * 2),  # Yaklaşık süre: 30 km/saat
                total_demand=0,  # Toplam talep aşağıda hesaplanacak
                created_at=func.now(),
                updated_at=func.now()
            )

            print(f"Attempting to save route to database: {route.__dict__}")
            db.add(route)
            db.flush()

            # Route Details ekle
            route_points = []
            total_demand = 0

            # Depo başlangıç noktası
            route_points.append({
                'lat': warehouse.latitude,
                'lng': warehouse.longitude,
                'name': warehouse.name,
                'address': warehouse.address,
                'type': 'depot'
            })

            # Müşteri noktaları
            for i, customer_id in enumerate(sub_route, 1):
                customer = selected_customers[customer_id - 1]
                route_detail = RouteDetail(
                    route_id=route.id,
                    customer_id=customer.id,
                    sequence_number=i,
                    demand=customer.desi,
                    status='pending',
                    created_at=func.now(),
                    updated_at=func.now()
                )
                db.add(route_detail)

                route_points.append({
                    'lat': customer.latitude,
                    'lng': customer.longitude,
                    'name': customer.name,
                    'address': customer.address,
                    'contact_person': customer.contact_person,
                    'contact_phone': customer.contact_phone,
                    'demand': float(customer.desi),
                    'type': 'customer'
                })

                total_demand += customer.desi

            # Depoya dönüş
            route_points.append({
                'lat': warehouse.latitude,
                'lng': warehouse.longitude,
                'name': warehouse.name,
                'address': warehouse.address,
                'type': 'depot'
            })

            # Route bilgilerini güncelle
            route.total_demand = total_demand

            routes_response.append({
                'points': route_points,
                'total_distance': float(total_distance),
                'total_demand': float(total_demand),
                'total_duration': route.total_duration,
                'vehicle': available_vehicle.plate_number,
                'driver': f"{available_driver.user.first_name} {available_driver.user.last_name}"
            })

        db.commit()
        return jsonify({
            'success': True,
            'message': f'{len(routes_response)} rota başarıyla oluşturuldu.',
            'routes': routes_response,
            'vehicle_capacity': vehicle_capacity
        })

    except Exception as e:
        db.rollback()
        print(f"Error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/optimize/check', methods=['POST'])
def check_optimize_prerequisites():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = SessionLocal()
    try:
        # Kullanıcının şirket bilgisini al
        if session['user_role'] == UserRole.COMPANY_ADMIN.value:
            employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
            if not employee:
                return jsonify({'success': False, 'error': 'Şirket bilgisi bulunamadı'}), 404
            company_id = employee.company_id
        elif session['user_role'] == UserRole.DRIVER.value:
            driver = db.query(Driver).filter_by(user_id=session['user_id']).first()
            if not driver:
                return jsonify({'success': False, 'error': 'Sürücü bilgisi bulunamadı'}), 404
            company_id = driver.company_id
        else:
            return jsonify({'success': False, 'error': 'Yetkisiz erişim'}), 403
        
        # 1. Depo Kontrolü
        warehouse = db.query(Warehouse).filter_by(
            company_id=company_id,
            is_active=True
        ).first()
        
        if not warehouse:
            return jsonify({
                'success': False, 
                'error': 'Şirketinize ait aktif depo bulunmuyor. Lütfen önce bir depo ekleyin ve aktif olarak işaretleyin.'
            }), 404
        
        # 2. Müşteri Kontrolü
        customers = db.query(Customer).filter_by(company_id=company_id).all()
        
        if len(customers) == 0:
            return jsonify({
                'success': False, 
                'error': 'Şirketinize ait müşteri bulunmuyor. Lütfen önce müşteri ekleyin.'
            }), 400
        
        # 3. Araç Kontrolü
        available_vehicles = db.query(Vehicle).filter(
            Vehicle.company_id == company_id,
            Vehicle.status == VehicleStatus.ACTIVE,
            ~Vehicle.id.in_(
                db.query(Route.vehicle_id).filter(
                    Route.status.in_([RouteStatus.PLANNED, RouteStatus.IN_PROGRESS])
                )
            )
        ).all()
        
        if not available_vehicles:
            return jsonify({
                'success': False,
                'error': 'Müsait araç bulunmuyor. Tüm araçlar aktif rotalarda veya bakımda.'
            }), 400
        
        # 4. Sürücü Kontrolü
        available_drivers = db.query(Driver).filter(
            Driver.company_id == company_id,
            ~Driver.id.in_(
                db.query(Route.driver_id).filter(
                    Route.status.in_([RouteStatus.PLANNED, RouteStatus.IN_PROGRESS])
                )
            )
        ).all()
        
        if not available_drivers:
            return jsonify({
                'success': False,
                'error': 'Müsait sürücü bulunmuyor. Tüm sürücüler aktif rotalarda.'
            }), 400
        
        # 5. Kapasite Kontrolü
        total_demand = sum(customer.desi for customer in customers)
        total_capacity = sum(vehicle.capacity for vehicle in available_vehicles)
        
        if total_demand > total_capacity:
            return jsonify({
                'success': False,
                'error': f'Toplam müşteri talebi ({total_demand:.2f} desi) mevcut araç kapasitesini ({total_capacity:.2f} desi) aşıyor.'
            }), 400
        
        # Tüm kontroller başarılı
        return jsonify({
            'success': True,
            'message': 'Rota optimizasyonu için gerekli tüm koşullar sağlanıyor.',
            'data': {
                'available_vehicles': len(available_vehicles),
                'available_drivers': len(available_drivers),
                'total_customers': len(customers),
                'total_demand': float(total_demand),
                'total_capacity': float(total_capacity)
            }
        })
        
    except Exception as e:
        print(f"Error in check_optimize_prerequisites: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Ön kontroller sırasında bir hata oluştu: {str(e)}'
        }), 500
    finally:
        db.close()

@app.route('/api/instances')
def get_instances():
    try:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
        instances = [f.split('.')[0] for f in os.listdir(data_dir) if f.endswith('.txt')]
        return jsonify({'instances': instances})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    db = SessionLocal()
    try:
        companies = db.query(Company).all()
        return render_template('admin/dashboard.html', companies=companies)
    finally:
        db.close()

@app.route('/admin/company/<int:company_id>')
@login_required
@admin_required
def company_details(company_id):
    db = SessionLocal()
    try:
        company = db.query(Company).get(company_id)
        if not company:
            flash('Şirket bulunamadı.', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        employees = db.query(CompanyEmployee).filter_by(company_id=company_id).all()
        vehicles = db.query(Vehicle).filter_by(company_id=company_id).all()
        drivers = db.query(Driver).filter_by(company_id=company_id).all()
        customers = db.query(Customer).filter_by(company_id=company_id).all()
        warehouses = db.query(Warehouse).filter_by(company_id=company_id).all()
        
        return render_template('admin/company_details.html',
            company=company,
            employees=employees,
            vehicles=vehicles,
            drivers=drivers,
            customers=customers,
            warehouses=warehouses
        )
    finally:
        db.close()

@app.route('/admin/company/<int:company_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_company(company_id):
    db = SessionLocal()
    try:
        company = db.query(Company).get(company_id)
        if not company:
            flash('Şirket bulunamadı.', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        if request.method == 'POST':
            company.name = request.form.get('name')
            company.tax_number = request.form.get('tax_number')
            company.address = request.form.get('address')
            company.phone = request.form.get('phone')
            company.email = request.form.get('email')
            company.max_vehicles = int(request.form.get('max_vehicles', 10))
            company.max_users = int(request.form.get('max_users', 50))
            
            db.commit()
            flash('Şirket bilgileri güncellendi.', 'success')
            return redirect(url_for('company_details', company_id=company_id))
            
        return render_template('admin/edit_company.html', company=company)
    finally:
        db.close()

@app.route('/admin/company/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_company():
    if request.method == 'POST':
        db = SessionLocal()
        try:
            company = Company(
                name=request.form.get('name'),
                tax_number=request.form.get('tax_number'),
                address=request.form.get('address'),
                phone=request.form.get('phone'),
                email=request.form.get('email'),
                max_vehicles=int(request.form.get('max_vehicles', 10)),
                max_users=int(request.form.get('max_users', 50))
            )
            db.add(company)
            db.commit()
            flash('Yeni şirket eklendi.', 'success')
            return redirect(url_for('admin_dashboard'))
        finally:
            db.close()
            
    return render_template('admin/add_company.html')

@app.route('/company/dashboard')
@login_required
@company_admin_required
def company_dashboard():
    db = SessionLocal()
    try:
        # Şirket yöneticisinin şirketini bul
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not employee:
            flash('Şirket bilgisi bulunamadı.', 'danger')
            return redirect(url_for('index'))
            
        company = employee.company
        print(f"\nLoading dashboard for company: {company.name} (ID: {company.id})")
        
        employees = db.query(CompanyEmployee).filter_by(company_id=company.id).all()
        vehicles = db.query(Vehicle).filter_by(company_id=company.id).all()
        drivers = db.query(Driver).filter_by(company_id=company.id).all()
        customers = db.query(Customer).filter_by(company_id=company.id).all()
        warehouses = db.query(Warehouse).filter_by(company_id=company.id).all()
        
        # Rotaları sorgula ve debug bilgisi ekle
        routes = db.query(Route).filter_by(company_id=company.id).order_by(Route.created_at.desc()).all()
        print(f"Found {len(routes)} routes for company {company.id}")
        
        # Her rotanın detaylarını yazdır
        for route in routes:
            print(f"\nRoute {route.id}:")
            print(f"  Status: {route.status.value}")
            print(f"  Vehicle: {route.vehicle.plate_number if route.vehicle else 'Not assigned'}")
            print(f"  Driver: {route.driver.user.first_name + ' ' + route.driver.user.last_name if route.driver else 'Not assigned'}")
            print(f"  Total Distance: {route.total_distance}")
            print(f"  Total Demand: {route.total_demand}")
            print(f"  Number of stops: {len(route.route_details)}")
        
        return render_template('company/dashboard.html',
            company=company,
            employees=employees,
            vehicles=vehicles,
            drivers=drivers,
            customers=customers,
            warehouses=warehouses,
            routes=routes  # Rotaları template'e gönder
        )
    except Exception as e:
        print(f"Error in company_dashboard: {str(e)}")
        traceback.print_exc()
        flash('Bir hata oluştu.', 'danger')
        return redirect(url_for('index'))
    finally:
        db.close()

@app.route('/company/customer/add', methods=['GET', 'POST'])
@login_required
@company_admin_required
def add_customer():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
            
            customer = Customer(
                company_id=employee.company_id,
                name=request.form.get('name'),
                address=request.form.get('address'),
                latitude=float(request.form.get('latitude')),
                longitude=float(request.form.get('longitude')),
                contact_person=request.form.get('contact_person'),
                contact_phone=request.form.get('contact_phone'),
                email=request.form.get('email'),
                priority=int(request.form.get('priority', 0)),
                notes=request.form.get('notes')
            )
            
            db.add(customer)
            db.commit()
            flash('Yeni müşteri başarıyla eklendi.', 'success')
            return redirect(url_for('company_dashboard'))
            
        return render_template('company/add_customer.html')
    finally:
        db.close()

@app.route('/company/customer/<int:customer_id>/edit', methods=['GET', 'POST'])
@login_required
@company_admin_required
def edit_customer(customer_id):
    db = SessionLocal()
    try:
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        customer = db.query(Customer).filter_by(id=customer_id, company_id=employee.company_id).first()
        
        if not customer:
            flash('Müşteri bulunamadı.', 'danger')
            return redirect(url_for('company_dashboard'))
            
        if request.method == 'POST':
            customer.name = request.form.get('name')
            customer.address = request.form.get('address')
            customer.latitude = float(request.form.get('latitude'))
            customer.longitude = float(request.form.get('longitude'))
            customer.contact_person = request.form.get('contact_person')
            customer.contact_phone = request.form.get('contact_phone')
            customer.email = request.form.get('email')
            customer.priority = int(request.form.get('priority', 0))
            customer.desi = float(request.form.get('desi', 0))
            customer.notes = request.form.get('notes')
            
            db.commit()
            flash('Müşteri bilgileri güncellendi.', 'success')
            return redirect(url_for('company_dashboard'))
            
        return render_template('company/edit_customer.html', customer=customer)
    finally:
        db.close()

@app.route('/company/customer/<int:customer_id>/delete', methods=['POST'])
@login_required
@company_admin_required
def delete_customer(customer_id):
    db = SessionLocal()
    try:
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        customer = db.query(Customer).filter_by(id=customer_id, company_id=employee.company_id).first()
        
        if not customer:
            flash('Müşteri bulunamadı.', 'danger')
            return redirect(url_for('company_dashboard'))
            
        # Müşterinin rotalarda kullanılıp kullanılmadığını kontrol et
        route_details = db.query(RouteDetail).filter_by(customer_id=customer_id).first()
        if route_details:
            flash('Bu müşteri rotalarda kullanıldığı için silinemiyor.', 'warning')
            return redirect(url_for('company_dashboard'))
            
        db.delete(customer)
        db.commit()
        flash('Müşteri başarıyla silindi.', 'success')
        
        return redirect(url_for('company_dashboard'))
    except Exception as e:
        db.rollback()
        print(f"Error in delete_customer: {str(e)}")
        traceback.print_exc()
        flash('Müşteri silinirken bir hata oluştu.', 'danger')
        return redirect(url_for('company_dashboard'))
    finally:
        db.close()

@app.route('/company/vehicle/add', methods=['POST'])
@login_required
@company_admin_required
def add_vehicle():
    db = SessionLocal()
    try:
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not employee:
            return jsonify({'error': 'Şirket bilgisi bulunamadı'}), 404

        data = request.json
        vehicle = Vehicle(
            company_id=employee.company_id,
            plate_number=data['plate_number'],
            brand=data['brand'],
            model=data['model'],
            capacity=data['capacity'],
            driver_id=data['driver_id'] if data['driver_id'] else None
        )
        db.add(vehicle)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/company/vehicle/<int:vehicle_id>/edit', methods=['POST'])
@login_required
@company_admin_required
def edit_vehicle(vehicle_id):
    db = SessionLocal()
    try:
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not employee:
            return jsonify({'error': 'Şirket bilgisi bulunamadı'}), 404

        vehicle = db.query(Vehicle).filter_by(id=vehicle_id, company_id=employee.company_id).first()
        if not vehicle:
            return jsonify({'error': 'Araç bulunamadı'}), 404
        
        data = request.json
        vehicle.plate_number = data['plate_number']
        vehicle.brand = data['brand']
        vehicle.model = data['model']
        vehicle.capacity = data['capacity']
        vehicle.driver_id = data['driver_id'] if data['driver_id'] else None
        
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/company/vehicle/<int:vehicle_id>/delete', methods=['POST'])
@login_required
@company_admin_required
def delete_vehicle(vehicle_id):
    db = SessionLocal()
    try:
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not employee:
            return jsonify({'error': 'Şirket bilgisi bulunamadı'}), 404

        vehicle = db.query(Vehicle).filter_by(id=vehicle_id, company_id=employee.company_id).first()
        if not vehicle:
            return jsonify({'error': 'Araç bulunamadı'}), 404
        
        db.delete(vehicle)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/company/vehicle/<int:vehicle_id>', methods=['GET'])
@login_required
@company_admin_required
def get_vehicle(vehicle_id):
    db = SessionLocal()
    try:
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not employee:
            return jsonify({'error': 'Şirket bilgisi bulunamadı'}), 404

        vehicle = db.query(Vehicle).filter_by(id=vehicle_id, company_id=employee.company_id).first()
        if not vehicle:
            return jsonify({'error': 'Araç bulunamadı'}), 404
        
        return jsonify({
            'id': vehicle.id,
            'plate_number': vehicle.plate_number,
            'brand': vehicle.brand,
            'model': vehicle.model,
            'capacity': vehicle.capacity,
            'driver_id': vehicle.driver_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/admin/company/<int:company_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_company(company_id):
    db = SessionLocal()
    try:
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            flash('Şirket bulunamadı.', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # İlişkili kayıtları sil
        db.query(CompanyEmployee).filter_by(company_id=company_id).delete()
        db.query(Vehicle).filter_by(company_id=company_id).delete()
        db.query(Driver).filter_by(company_id=company_id).delete()
        db.query(Warehouse).filter_by(company_id=company_id).delete()
        db.query(Customer).filter_by(company_id=company_id).delete()
        
        # Şirketi sil
        db.delete(company)
        db.commit()
        
        flash('Şirket başarıyla silindi.', 'success')
        return redirect(url_for('admin_dashboard'))
        
    except Exception as e:
        db.rollback()
        flash(f'Şirket silinirken bir hata oluştu: {str(e)}', 'danger')
        return redirect(url_for('admin_dashboard'))
    finally:
        db.close()

@app.route('/company/driver/add', methods=['POST'])
@login_required
@company_admin_required
def add_driver():
    try:
        db = SessionLocal()
        data = request.json
        
        # Şirket bilgisini al
        company_employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not company_employee:
            return jsonify({'success': False, 'error': 'Şirket bilgisi bulunamadı'}), 404
        
        # Yeni kullanıcı oluştur
        user = User(
            email=data['email'],  # Şoförün email adresi
            password_hash=generate_password_hash(data['password']),  # Şoförün şifresi
            role=UserRole.DRIVER,
            first_name=data['first_name'],
            last_name=data['last_name'],
            is_active=True,
            created_at=func.now(),
            updated_at=func.now()
        )
        db.add(user)
        db.flush()  # ID'yi almak için flush
        
        # Yeni şoför oluştur
        driver = Driver(
            user_id=user.id,
            company_id=company_employee.company_id,
            license_number=data['license_number'],
            total_experience_years=data['experience'],
            created_at=func.now(),
            updated_at=func.now()
        )
        db.add(driver)
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Şoför başarıyla eklendi',
            'credentials': {
                'email': user.email,
                'password': data['password']
            }
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()

@app.route('/driver/dashboard')
@login_required
@driver_required
def driver_dashboard():
    db = SessionLocal()
    try:
        # Şoförün bilgilerini al
        driver = db.query(Driver).join(User).filter(User.id == session['user_id']).first()
        if not driver:
            flash('Şoför bilgisi bulunamadı.', 'danger')
            return redirect(url_for('index'))
        
        # Aktif ve tamamlanmış rotaları al
        active_routes = db.query(Route).filter(
            Route.driver_id == driver.id,
            Route.status.in_([RouteStatus.PLANNED, RouteStatus.IN_PROGRESS])
        ).order_by(Route.start_time.desc()).all()
        
        completed_routes = db.query(Route).filter(
            Route.driver_id == driver.id,
            Route.status == RouteStatus.COMPLETED
        ).order_by(Route.start_time.desc()).limit(10).all()
        
        return render_template('driver/dashboard.html',
            driver=driver,
            active_routes=active_routes,
            completed_routes=completed_routes
        )
    finally:
        db.close()

@app.route('/api/route/<int:route_id>')
@login_required
def get_route_details(route_id):
    db = SessionLocal()
    try:
        # Rota bilgilerini ilişkili tablolarla birlikte çek
        route = db.query(Route).options(
            joinedload(Route.driver).joinedload(Driver.user),
            joinedload(Route.vehicle),
            joinedload(Route.warehouse),
            joinedload(Route.route_details).joinedload(RouteDetail.customer)
        ).get(route_id)
        
        if not route:
            return jsonify({'error': 'Rota bulunamadı'}), 404
            
        # Kullanıcının yetkisini kontrol et
        if session['user_role'] == UserRole.DRIVER.value:
            driver = db.query(Driver).filter_by(user_id=session['user_id']).first()
            if not driver or route.driver_id != driver.id:
                return jsonify({'error': 'Bu rotaya erişim yetkiniz yok'}), 403
        elif session['user_role'] == UserRole.COMPANY_ADMIN.value:
            employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
            if not employee or route.company_id != employee.company_id:
                return jsonify({'error': 'Bu rotaya erişim yetkiniz yok'}), 403
                
        # Rota detaylarını hazırla
        route_data = {
            'id': route.id,
            'status': route.status.value,
            'start_time': route.start_time.isoformat() if route.start_time else None,
            'end_time': route.end_time.isoformat() if route.end_time else None,
            'total_distance': float(route.total_distance) if route.total_distance else 0,
            'total_duration': route.total_duration,
            'total_demand': float(route.total_demand) if route.total_demand else 0,
            'vehicle': {
                'plate_number': route.vehicle.plate_number,
                'brand': route.vehicle.brand,
                'model': route.vehicle.model,
                'capacity': route.vehicle.capacity
            } if route.vehicle else None,
            'driver': {
                'user': {
                    'first_name': route.driver.user.first_name,
                    'last_name': route.driver.user.last_name
                }
            } if route.driver and route.driver.user else None,
            'warehouse': {
                'name': route.warehouse.name,
                'address': route.warehouse.address,
                'latitude': route.warehouse.latitude,
                'longitude': route.warehouse.longitude
            } if route.warehouse else None,
            'stops': []
        }
        
        # Debug: Şoför bilgilerini kontrol et
        print("\nRoute Driver Info:")
        if route.driver and route.driver.user:
            print(f"Driver ID: {route.driver.id}")
            print(f"Driver User ID: {route.driver.user_id}")
            print(f"Driver Name: {route.driver.user.first_name} {route.driver.user.last_name}")
        else:
            print("No driver assigned")
        
        # Durakları ekle
        for detail in route.route_details:
            route_data['stops'].append({
                'id': detail.id,
                'sequence': detail.sequence_number,
                'customer': {
                    'name': detail.customer.name,
                    'address': detail.customer.address,
                    'latitude': detail.customer.latitude,
                    'longitude': detail.customer.longitude,
                    'contact_person': detail.customer.contact_person,
                    'contact_phone': detail.customer.contact_phone
                },
                'demand': float(detail.demand) if detail.demand else 0,
                'status': detail.status,
                'planned_arrival': detail.planned_arrival_time.isoformat() if detail.planned_arrival_time else None,
                'actual_arrival': detail.actual_arrival_time.isoformat() if detail.actual_arrival_time else None,
                'planned_departure': detail.planned_departure_time.isoformat() if detail.planned_departure_time else None,
                'actual_departure': detail.actual_departure_time.isoformat() if detail.actual_departure_time else None,
                'notes': detail.notes
            })
            
        return jsonify(route_data)
    finally:
        db.close()

@app.route('/api/route/<int:route_id>/status', methods=['POST'])
@login_required
@driver_required
def update_route_status(route_id):
    db = SessionLocal()
    try:
        driver = db.query(Driver).filter_by(user_id=session['user_id']).first()
        route = db.query(Route).filter_by(id=route_id, driver_id=driver.id).first()
        
        if not route:
            return jsonify({'error': 'Rota bulunamadı'}), 404
            
        data = request.json
        new_status = data.get('status')
        
        if new_status not in [s.value for s in RouteStatus]:
            return jsonify({'error': 'Geçersiz durum'}), 400
            
        route.status = RouteStatus(new_status)
        
        if new_status == RouteStatus.IN_PROGRESS.value:
            route.start_time = func.now()
        elif new_status == RouteStatus.COMPLETED.value:
            route.end_time = func.now()
            
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()

@app.route('/api/route/<int:route_id>/stop/<int:stop_id>/status', methods=['POST'])
@login_required
@driver_required
def update_stop_status(route_id, stop_id):
    db = SessionLocal()
    try:
        # Şoförün yetkisini kontrol et
        driver = db.query(Driver).filter_by(user_id=session['user_id']).first()
        route = db.query(Route).filter_by(id=route_id, driver_id=driver.id).first()
        
        if not route:
            print(f"Route not found: {route_id} for driver: {driver.id}")
            return jsonify({'error': 'Rota bulunamadı'}), 404
            
        # Durak detayını bul
        stop = db.query(RouteDetail).filter_by(id=stop_id, route_id=route_id).first()
        if not stop:
            print(f"Stop not found: {stop_id} for route: {route_id}")
            return jsonify({'error': 'Durak bulunamadı'}), 404
            
        data = request.json
        new_status = data.get('status')
        notes = data.get('notes')
        
        print(f"Updating stop {stop_id} status from {stop.status} to {new_status}")
        
        if new_status not in ['pending', 'completed', 'failed', 'skipped']:
            return jsonify({'error': 'Geçersiz durum'}), 400
            
        # Durum değişikliğini kaydet
        stop.status = new_status
        stop.notes = notes
        
        # Tamamlandı ise varış zamanını kaydet
        if new_status == 'completed':
            stop.actual_arrival_time = func.now()
            print(f"Setting actual arrival time for stop {stop_id}")
        
        # Başarısız ise başarısızlık zamanını kaydet
        if new_status == 'failed':
            stop.actual_arrival_time = func.now()
            print(f"Setting failure time for stop {stop_id}")
        
        # Değişiklikleri kaydet
        db.commit()
        print(f"Successfully updated stop {stop_id} status to {new_status}")
        
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        print(f"Error updating stop status: {str(e)}")
        traceback.print_exc()  # Hata stack trace'ini yazdır
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/admin/company/<int:company_id>/warehouse/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_warehouse(company_id):
    db = SessionLocal()
    try:
        company = db.query(Company).get(company_id)
        if not company:
            flash('Şirket bulunamadı.', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        if request.method == 'POST':
            warehouse = Warehouse(
                company_id=company_id,
                name=request.form['name'],
                address=request.form['address'],
                latitude=float(request.form['latitude']),
                longitude=float(request.form['longitude']),
                capacity=float(request.form['capacity']),
                contact_person=request.form['contact_person'],
                contact_phone=request.form['contact_phone'],
                operating_hours=request.form['operating_hours'],
                is_active='is_active' in request.form,
                created_at=func.now(),
                updated_at=func.now()
            )
            db.add(warehouse)
            db.commit()
            flash('Depo başarıyla eklendi.', 'success')
            return redirect(url_for('company_details', company_id=company_id))
            
        return render_template('admin/add_warehouse.html', company_id=company_id)
    finally:
        db.close()

@app.route('/admin/warehouse/<int:warehouse_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_warehouse(warehouse_id):
    db = SessionLocal()
    try:
        warehouse = db.query(Warehouse).get(warehouse_id)
        if not warehouse:
            flash('Depo bulunamadı.', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        if request.method == 'POST':
            warehouse.name = request.form['name']
            warehouse.address = request.form['address']
            warehouse.latitude = float(request.form['latitude'])
            warehouse.longitude = float(request.form['longitude'])
            warehouse.capacity = float(request.form['capacity'])
            warehouse.contact_person = request.form['contact_person']
            warehouse.contact_phone = request.form['contact_phone']
            warehouse.operating_hours = request.form['operating_hours']
            warehouse.is_active = 'is_active' in request.form
            warehouse.updated_at = func.now()
            
            db.commit()
            flash('Depo bilgileri güncellendi.', 'success')
            return redirect(url_for('company_details', company_id=warehouse.company_id))
            
        return render_template('admin/add_warehouse.html', warehouse=warehouse, company_id=warehouse.company_id)
    finally:
        db.close()

@app.route('/admin/warehouse/<int:warehouse_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_warehouse(warehouse_id):
    db = SessionLocal()
    try:
        warehouse = db.query(Warehouse).get(warehouse_id)
        if not warehouse:
            flash('Depo bulunamadı.', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        # Deponun kullanımda olup olmadığını kontrol et
        if db.query(Route).filter_by(warehouse_id=warehouse_id).count() > 0:
            flash('Bu depo rotalarda kullanıldığı için silinemiyor.', 'danger')
            return redirect(url_for('company_details', company_id=warehouse.company_id))
            
        company_id = warehouse.company_id
        db.delete(warehouse)
        db.commit()
        flash('Depo başarıyla silindi.', 'success')
        return redirect(url_for('company_details', company_id=company_id))
    finally:
        db.close()

# Şirket yöneticisi için depo yönetimi route'ları
@app.route('/company/warehouse/add', methods=['GET', 'POST'])
@login_required
@company_admin_required
def company_add_warehouse():
    db = SessionLocal()
    try:
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not employee:
            flash('Şirket bilgisi bulunamadı.', 'danger')
            return redirect(url_for('company_dashboard'))
            
        if request.method == 'POST':
            warehouse = Warehouse(
                company_id=employee.company_id,
                name=request.form['name'],
                address=request.form['address'],
                latitude=float(request.form['latitude']),
                longitude=float(request.form['longitude']),
                capacity=float(request.form['capacity']),
                contact_person=request.form['contact_person'],
                contact_phone=request.form['contact_phone'],
                operating_hours=request.form['operating_hours'],
                is_active='is_active' in request.form,
                created_at=func.now(),
                updated_at=func.now()
            )
            db.add(warehouse)
            db.commit()
            flash('Depo başarıyla eklendi.', 'success')
            return redirect(url_for('company_dashboard'))
            
        return render_template('admin/add_warehouse.html', company_id=employee.company_id)
    finally:
        db.close()

@app.route('/company/warehouse/<int:warehouse_id>/edit', methods=['GET', 'POST'])
@login_required
@company_admin_required
def company_edit_warehouse(warehouse_id):
    db = SessionLocal()
    try:
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        warehouse = db.query(Warehouse).filter_by(id=warehouse_id, company_id=employee.company_id).first()
        
        if not warehouse:
            flash('Depo bulunamadı.', 'danger')
            return redirect(url_for('company_dashboard'))
            
        if request.method == 'POST':
            warehouse.name = request.form['name']
            warehouse.address = request.form['address']
            warehouse.latitude = float(request.form['latitude'])
            warehouse.longitude = float(request.form['longitude'])
            warehouse.capacity = float(request.form['capacity'])
            warehouse.contact_person = request.form['contact_person']
            warehouse.contact_phone = request.form['contact_phone']
            warehouse.operating_hours = request.form['operating_hours']
            warehouse.is_active = 'is_active' in request.form
            warehouse.updated_at = func.now()
            
            db.commit()
            flash('Depo bilgileri güncellendi.', 'success')
            return redirect(url_for('company_dashboard'))
            
        return render_template('admin/add_warehouse.html', warehouse=warehouse, company_id=employee.company_id)
    finally:
        db.close()

@app.route('/company/warehouse/delete/<int:warehouse_id>', methods=['POST'])
@login_required
@company_admin_required
def company_delete_warehouse_page(warehouse_id):
    db = SessionLocal()
    try:
        # Şirket yöneticisinin şirketini bul
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not employee:
            flash('Şirket bilgisi bulunamadı.', 'danger')
            return redirect(url_for('index'))
            
        # Depoyu bul
        warehouse = db.query(Warehouse).filter_by(id=warehouse_id, company_id=employee.company_id).first()
        if not warehouse:
            flash('Depo bulunamadı veya bu depoyu silme yetkiniz yok.', 'danger')
            return redirect(url_for('company_dashboard'))
            
        # Deponun kullanıldığı rotaları kontrol et
        routes_using_warehouse = db.query(Route).filter_by(warehouse_id=warehouse_id).count()
        if routes_using_warehouse > 0:
            flash('Bu depo rotalar tarafından kullanılıyor ve silinemiyor.', 'warning')
            return redirect(url_for('company_dashboard'))
            
        # Depoyu sil
        db.delete(warehouse)
        db.commit()
        
        flash('Depo başarıyla silindi.', 'success')
    except Exception as e:
        db.rollback()
        print(f"Error in company_delete_warehouse: {str(e)}")
        traceback.print_exc()
        flash('Depo silinirken bir hata oluştu.', 'danger')
    finally:
        db.close()
        
    return redirect(url_for('company_dashboard'))

def calculate_total_vehicle_capacity(company_id):
    db = SessionLocal()
    try:
        vehicles = db.query(Vehicle).filter_by(company_id=company_id).all()
        total_capacity = sum(vehicle.capacity for vehicle in vehicles)
        return total_capacity
    finally:
        db.close()

@app.route('/api/route/<int:route_id>/delete', methods=['POST'])
@login_required
@driver_required
def delete_route(route_id):
    db = SessionLocal()
    try:
        # Şoförün yetkisini kontrol et
        driver = db.query(Driver).filter_by(user_id=session['user_id']).first()
        route = db.query(Route).filter_by(id=route_id, driver_id=driver.id).first()
        
        if not route:
            return jsonify({'error': 'Rota bulunamadı'}), 404
            
        # Sadece planlanan rotalar silinebilir
        if route.status != RouteStatus.PLANNED:
            return jsonify({'error': 'Sadece planlanan rotalar silinebilir'}), 400
            
        # Önce rota detaylarını sil
        db.query(RouteDetail).filter_by(route_id=route_id).delete()
        
        # Sonra rotayı sil
        db.delete(route)
        db.commit()
        
        return jsonify({'success': True, 'message': 'Rota başarıyla silindi'})
    except Exception as e:
        db.rollback()
        print(f"Error deleting route: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/company/route/<int:route_id>/delete', methods=['POST'])
@login_required
def company_delete_route(route_id):
    db = SessionLocal()
    try:
        # Check if user is company admin or manager
        if 'user_role' not in session or (session['user_role'] != 'company_admin' and session['user_role'] != 'manager'):
            return jsonify({'error': 'Bu işlem için yetkiniz yok'}), 403
        
        # Get user's company
        employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        if not employee:
            return jsonify({'error': 'Şirket bilgisi bulunamadı'}), 404
            
        # Find the route
        route = db.query(Route).filter_by(id=route_id, company_id=employee.company_id).first()
        
        if not route:
            return jsonify({'error': 'Rota bulunamadı'}), 404
            
        # Sadece planlanan rotalar silinebilir
        if route.status != RouteStatus.PLANNED:
            return jsonify({'error': 'Sadece planlanan rotalar silinebilir'}), 400
            
        # Önce rota detaylarını sil
        db.query(RouteDetail).filter_by(route_id=route_id).delete()
        
        # Sonra rotayı sil
        db.delete(route)
        db.commit()
        
        return jsonify({'success': True, 'message': 'Rota başarıyla silindi'})
    except Exception as e:
        db.rollback()
        print(f"Error deleting route: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/company/route/delete/<int:route_id>', methods=['POST'])
@login_required
def company_delete_route_page(route_id):
    db = SessionLocal()
    try:
        # Check if user is company admin or manager
        if 'user_role' not in session or (session['user_role'] != 'company_admin' and session['user_role'] != 'manager'):
            flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
            return redirect(url_for('index'))
        
        # Get user's company
        if session['user_role'] == 'company_admin':
            employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
        else:  # manager
            employee = db.query(CompanyEmployee).filter_by(user_id=session['user_id']).first()
            
        if not employee:
            flash('Şirket bilgisi bulunamadı.', 'danger')
            return redirect(url_for('index'))
            
        # Rotayı bul
        route = db.query(Route).filter_by(id=route_id, company_id=employee.company_id).first()
        if not route:
            flash('Rota bulunamadı veya bu rotayı silme yetkiniz yok.', 'danger')
            return redirect(url_for('company_dashboard'))
            
        # Sadece planlanan rotalar silinebilir
        if route.status != RouteStatus.PLANNED:
            flash('Sadece planlanan rotalar silinebilir.', 'warning')
            return redirect(url_for('company_dashboard'))
            
        # Önce rota detaylarını sil
        db.query(RouteDetail).filter_by(route_id=route_id).delete()
        
        # Sonra rotayı sil
        db.delete(route)
        db.commit()
        
        flash('Rota başarıyla silindi.', 'success')
    except Exception as e:
        db.rollback()
        print(f"Error in company_delete_route: {str(e)}")
        traceback.print_exc()
        flash('Rota silinirken bir hata oluştu.', 'danger')
    finally:
        db.close()
        
    return redirect(url_for('company_dashboard'))

@app.route('/api/route/<int:route_id>/stop/<int:stop_id>/note', methods=['POST'])
@login_required
@driver_required
def add_stop_note(route_id, stop_id):
    db = SessionLocal()
    try:
        # Şoförün yetkisini kontrol et
        driver = db.query(Driver).filter_by(user_id=session['user_id']).first()
        route = db.query(Route).filter_by(id=route_id, driver_id=driver.id).first()
        
        if not route:
            print(f"Route not found: {route_id} for driver: {driver.id}")
            return jsonify({'error': 'Rota bulunamadı'}), 404
            
        # Durak detayını bul
        stop = db.query(RouteDetail).filter_by(id=stop_id, route_id=route_id).first()
        if not stop:
            print(f"Stop not found: {stop_id} for route: {route_id}")
            return jsonify({'error': 'Durak bulunamadı'}), 404
            
        data = request.json
        notes = data.get('notes')
        
        print(f"Adding note to stop {stop_id}: {notes}")
        
        # Notu kaydet
        stop.notes = notes
        
        # Değişiklikleri kaydet
        db.commit()
        print(f"Successfully added note to stop {stop_id}")
        
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        print(f"Error adding note to stop: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)