from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import Company, Driver, Vehicle, Route, RouteDetail, Customer, Warehouse, RouteStatus, VehicleStatus
from database import SessionLocal, db
from datetime import datetime
from sqlalchemy import and_
from utils.route_optimizer import optimize_routes
from utils.auth import company_required
from process_data import OSRMHandler
from alg_creator import run_tabu_search
import random
import traceback

company_routes = Blueprint('company_routes', __name__)

# Reusable function for optimization prerequisite checks
def _check_prerequisites(db, num_customers=None):
    """
    Perform prerequisite checks for route optimization
    Returns tuple of (success_status, response_or_data)
    """
    try:
        # 1. Depo Kontrolü
        warehouse = db.query(Warehouse).filter_by(
            company_id=current_user.company_id, 
            is_active=True
        ).first()
        
        if not warehouse:
            return False, (jsonify({
                'success': False, 
                'error': 'Bu şirketin aktif deposu bulunmuyor. Lütfen önce bir depo tanımlayın.'
            }), 404)

        # 2. Müşteri Kontrolü
        customers = db.query(Customer).filter_by(
            company_id=current_user.company_id
        ).all()
        
        if len(customers) == 0:
            return False, (jsonify({
                'success': False, 
                'error': 'Bu şirketin müşterisi bulunmuyor. Lütfen önce müşteri ekleyin.'
            }), 400)

        # 3. Araç ve Sürücü Kontrolü
        available_vehicles = db.query(Vehicle).filter(
            Vehicle.company_id == current_user.company_id,
            Vehicle.status == VehicleStatus.ACTIVE,
            ~Vehicle.id.in_(
                db.query(Route.vehicle_id).filter(
                    Route.status.in_([RouteStatus.PLANNED, RouteStatus.IN_PROGRESS])
                )
            )
        ).all()

        if not available_vehicles:
            return False, (jsonify({
                'success': False,
                'error': 'Müsait araç bulunmuyor. Tüm araçlar aktif rotalarda veya bakımda.'
            }), 400)

        available_drivers = db.query(Driver).filter(
            Driver.company_id == current_user.company_id,
            ~Driver.id.in_(
                db.query(Route.driver_id).filter(
                    Route.status.in_([RouteStatus.PLANNED, RouteStatus.IN_PROGRESS])
                )
            )
        ).all()

        if not available_drivers:
            return False, (jsonify({
                'success': False,
                'error': 'Müsait sürücü bulunmuyor. Tüm sürücüler aktif rotalarda.'
            }), 400)

        # 4. Kapasite Kontrolü
        total_demand = sum(customer.desi for customer in customers)
        total_capacity = sum(vehicle.capacity for vehicle in available_vehicles)

        if total_demand > total_capacity:
            return False, (jsonify({
                'success': False,
                'error': f'Toplam müşteri talebi ({total_demand:.2f} desi) mevcut araç kapasitesini ({total_capacity:.2f} desi) aşıyor.'
            }), 400)
        
        # Eğer num_customers belirtilmişse, müşteri sayısı kontrolü yap
        if num_customers is not None:
            if num_customers != 0 and num_customers < 2:
                return False, (jsonify({
                    'success': False,
                    'error': 'Müşteri sayısı en az 2 olmalı veya tüm müşteriler için 0 olmalı.'
                }), 400)
                
            if num_customers != 0 and num_customers > 15:
                return False, (jsonify({
                    'success': False,
                    'error': "Müşteri sayısı 15'in üstünde olamaz."
                }), 400)

            if num_customers == 0:
                selected_customers = customers
            else:
                if len(customers) < num_customers:
                    return False, (jsonify({
                        'success': False,
                        'error': f'Yeterli müşteri yok. Şirketin {len(customers)} müşterisi var, {num_customers} müşteri istendi.'
                    }), 400)
                selected_customers = random.sample(customers, num_customers)
                
            # Tek araç kapasitesi kontrolü (optimize için)
            min_vehicle_capacity = min(vehicle.capacity for vehicle in available_vehicles)
            max_customer_demand = max(customer.desi for customer in selected_customers)
            if max_customer_demand > min_vehicle_capacity:
                return False, (jsonify({
                    'success': False,
                    'error': f'En yüksek müşteri talebi ({max_customer_demand:.2f} desi) en küçük araç kapasitesinden ({min_vehicle_capacity:.2f} desi) büyük.'
                }), 400)
                
            return True, {
                'warehouse': warehouse,
                'customers': customers,
                'selected_customers': selected_customers,
                'available_vehicles': available_vehicles,
                'available_drivers': available_drivers,
                'total_demand': total_demand,
                'total_capacity': total_capacity
            }
        
        # check_prerequisites için basitleştirilmiş veri döndür
        return True, {
            'available_vehicles': len(available_vehicles),
            'available_drivers': len(available_drivers),
            'total_customers': len(customers),
            'total_demand': total_demand,
            'total_capacity': total_capacity
        }
    
    except Exception as e:
        traceback.print_exc()
        return False, (jsonify({
            'success': False,
            'error': f'Ön kontroller sırasında bir hata oluştu: {str(e)}'
        }), 500)

@company_routes.route('/api/optimize', methods=['POST'])
@login_required
@company_required
def optimize():
    db = SessionLocal()
    try:
        data = request.get_json()
        num_customers = data.get('num_customers', 5)

        # Ön kontrolleri yap
        success, result = _check_prerequisites(db, num_customers)
        if not success:
            return result
        
        # Ön kontrol sonuçlarını al
        warehouse = result['warehouse']
        selected_customers = result['selected_customers']
        available_vehicles = result['available_vehicles']
        available_drivers = result['available_drivers']
        
        # Optimizasyon için minimum araç kapasitesini hesapla
        min_vehicle_capacity = min(vehicle.capacity for vehicle in available_vehicles)

        # 6. Optimizasyon Verilerini Hazırla
        instance_data = {
            'instance_name': 'custom',
            'max_vehicle_number': len(available_vehicles),
            'vehicle_capacity': min_vehicle_capacity,
            'depart': {
                'coordinates': {
                    'x': warehouse.latitude,
                    'y': warehouse.longitude
                },
                'demand': 0
            }
        }

        # Müşterileri instance_data'ya ekle
        for i, customer in enumerate(selected_customers, 1):
            instance_data[f'C_{i}'] = {
                'coordinates': {
                    'x': customer.latitude,
                    'y': customer.longitude
                },
                'demand': float(customer.desi)
            }

        # 7. OSRM Mesafe Hesaplama
        print("\nMesafeler hesaplanıyor...")
        maps_handler = OSRMHandler()
        if not maps_handler.precompute_distances(instance_data):
            return jsonify({
                'success': False,
                'error': 'Mesafeler hesaplanamadı. Lütfen daha sonra tekrar deneyin.'
            }), 500

        # 8. Tabu Search Algoritması
        print("\nRota optimizasyonu başlıyor...")
        routes = run_tabu_search(
            instance_data=instance_data,
            individual_size=len(selected_customers),
            n_gen=min(500, len(selected_customers) * 20),
            tabu_size=min(20, len(selected_customers) // 2 + 5),
            stagnation_limit=15,
            vehicle_capacity=float(min_vehicle_capacity)
        )

        if not routes:
            return jsonify({
                'success': False,
                'error': 'Uygun rota bulunamadı. Lütfen müşteri sayısını azaltın veya araç kapasitesini artırın.'
            }), 400

        # 9. Rotaları Veritabanına Kaydet
        print("\nRotalar kaydediliyor...")
        created_routes = []
        available_vehicles = iter(available_vehicles)
        available_drivers = iter(available_drivers)

        for route_index, route_customers in enumerate(routes):
            try:
                vehicle = next(available_vehicles)
                driver = next(available_drivers)
            except StopIteration:
                db.rollback()
                return jsonify({
                    'success': False,
                    'error': 'Yeterli sayıda müsait araç veya sürücü yok.'
                }), 400

            # Rota için toplam talep hesapla
            route_demand = sum(
                selected_customers[customer_id - 1].desi 
                for customer_id in route_customers
            )

            # Rotayı oluştur
            route = Route(
                company_id=current_user.company_id,
                driver_id=driver.id,
                vehicle_id=vehicle.id,
                warehouse_id=warehouse.id,
                status=RouteStatus.PLANNED,
                total_demand=float(route_demand),
                total_distance=0.0,  # Mesafe daha sonra hesaplanacak
                created_at=datetime.utcnow()
            )
            db.add(route)
            db.flush()

            # Rota detaylarını ekle
            for sequence, customer_id in enumerate(route_customers, 1):
                customer = selected_customers[customer_id - 1]
                detail = RouteDetail(
                    route_id=route.id,
                    customer_id=customer.id,
                    sequence_number=sequence,
                    demand=float(customer.desi),
                    status='pending',
                    created_at=datetime.utcnow()
                )
                db.add(detail)

            created_routes.append(route)

        db.commit()
        print(f"\n{len(created_routes)} rota başarıyla oluşturuldu!")

        return jsonify({
            'success': True,
            'message': f'{len(created_routes)} rota başarıyla oluşturuldu',
            'routes': [{
                'id': route.id,
                'driver': f"{route.driver.user.first_name} {route.driver.user.last_name}",
                'vehicle': route.vehicle.plate_number,
                'total_demand': route.total_demand,
                'num_stops': len(route.route_details)
            } for route in created_routes]
        })

    except Exception as e:
        db.rollback()
        print(f"Error in optimize: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Bir hata oluştu: {str(e)}'
        }), 500
    finally:
        db.close()

@company_routes.route('/api/optimize/check', methods=['POST'])
@login_required
@company_required
def check_optimize_prerequisites():
    """Rota optimizasyonu öncesi ön kontrolleri yapar"""
    db = SessionLocal()
    try:
        # Ön kontrolleri yap
        success, result = _check_prerequisites(db)
        if not success:
            return result
            
        # Başarılı sonucu döndür
        return jsonify({
            'success': True,
            'message': 'Tüm ön kontroller başarılı',
            'data': result
        })

    finally:
        db.close()

@company_routes.route('/api/route/<int:route_id>', methods=['GET'])
@login_required
@company_required
def get_route(route_id):
    try:
        # Rotayı tek sorguda ilişkili verilerle birlikte al
        route = Route.query.filter_by(
            id=route_id,
            company_id=current_user.company_id
        ).options(
            db.joinedload(Route.warehouse),
            db.joinedload(Route.vehicle),
            db.joinedload(Route.driver).joinedload(Driver.user),
            db.joinedload(Route.route_details).joinedload(RouteDetail.customer)
        ).first()
        
        if not route:
            return jsonify({'success': False, 'error': 'Rota bulunamadı'}), 404
        
        # OSRM handler'ı başlat
        osrm_handler = OSRMHandler()
        
        # Depo koordinatları
        warehouse_coords = (route.warehouse.latitude, route.warehouse.longitude)
        
        # Durakları sıraya göre al
        stops = sorted(route.route_details, key=lambda x: x.sequence_number)
        
        # Rota geometrilerini hesapla
        route_geometries = []
        total_calculated_distance = 0.0 # Hesaplanan mesafeyi de toplayalım
        if stops:
            # Noktaları koordinat listesine dönüştür
            coordinates = [warehouse_coords]  # Başlangıç deposu
            for stop in stops:
                coordinates.append((stop.customer.latitude, stop.customer.longitude))
            coordinates.append(warehouse_coords)  # Bitiş deposu
            
            # DEBUG: Check if coordinates list is populated
            print(f"DEBUG: Total coordinates to process: {len(coordinates)}")
            
            # Her bağlantı için rota detaylarını hesapla
            for i in range(len(coordinates) - 1):
                from_point = coordinates[i]
                to_point = coordinates[i + 1]
                
                # DEBUG: Check points before calling OSRM
                print(f"DEBUG: Attempting to get route segment {i}: from {from_point} to {to_point}")
                
                print(f"Fetching route details for segment {i}: {from_point} -> {to_point}") # Debug log
                segment = osrm_handler.get_route_details(from_point, to_point)
                
                if segment and segment.get('coordinates'):
                    print(f"Segment {i} details found. Distance: {segment.get('distance', 0)}") # Debug log
                    # "from" ve "to" etiketlerini oluştur
                    if i == 0:
                        from_label = 'warehouse'
                        to_label = f'customer_{stops[i].customer.id}'
                    elif i == len(coordinates) - 2:
                        from_label = f'customer_{stops[i-1].customer.id}'
                        to_label = 'warehouse'
                    else:
                        from_label = f'customer_{stops[i-1].customer.id}'
                        to_label = f'customer_{stops[i].customer.id}'
                    
                    route_geometries.append({
                        'from': from_label,
                        'to': to_label,
                        'coordinates': segment['coordinates'] # OSRM'den gelen koordinatlar
                    })
                    total_calculated_distance += segment.get('distance', 0.0)
                else:
                    # Eğer OSRM'den geometri alınamazsa logla ve bu segmenti atla (düz çizgi de çizilmeyecek)
                    print(f"Warning: Could not retrieve route geometry for segment {i}. Skipping.")

        # Eğer veritabanındaki mesafe 0 ise ve yeni hesaplandıysa güncelle (isteğe bağlı)
        # if route.total_distance == 0.0 and total_calculated_distance > 0:
        #     route.total_distance = total_calculated_distance
        #     db.session.add(route) # Eğer db session kullanılıyorsa
        #     db.session.commit() # Eğer db session kullanılıyorsa

        # Yanıt verisi oluştur
        route_data = {
            'id': route.id,
            'driver': {
                'id': route.driver.id,
                'user': {
                    'first_name': route.driver.user.first_name,
                    'last_name': route.driver.user.last_name
                }
            } if route.driver else None,
            'vehicle': {
                'id': route.vehicle.id,
                'plate_number': route.vehicle.plate_number,
                'brand': route.vehicle.brand, # Marka ve model ekleyelim
                'model': route.vehicle.model,
                'capacity': route.vehicle.capacity
            } if route.vehicle else None,
            'warehouse': {
                'id': route.warehouse.id,
                'name': route.warehouse.name,
                'address': route.warehouse.address,
                'latitude': route.warehouse.latitude,
                'longitude': route.warehouse.longitude
            },
            'total_distance': route.total_distance, # Veritabanındaki değeri kullanalım
            'calculated_distance': total_calculated_distance, # Hesaplanan değeri de gönderelim (debug için)
            'total_demand': route.total_demand,
            'status': route.status.value,
            'created_at': route.created_at.isoformat(),
            'stops': [{
                'id': detail.id,
                'sequence': detail.sequence_number,
                'demand': detail.demand,
                'status': detail.status,
                'notes': detail.notes, # Notları da ekleyelim
                'planned_arrival': detail.planned_arrival_time.isoformat() if detail.planned_arrival_time else None, # Zamanları ekleyelim
                'actual_arrival': detail.actual_arrival_time.isoformat() if detail.actual_arrival_time else None,
                'customer': {
                    'id': detail.customer.id,
                    'name': detail.customer.name,
                    'address': detail.customer.address,
                    'contact_person': detail.customer.contact_person,
                    'contact_phone': detail.customer.contact_phone,
                    'latitude': detail.customer.latitude,
                    'longitude': detail.customer.longitude
                }
            } for detail in stops], # Sıralı durakları kullanalım
            'route_geometries': route_geometries # Hesaplanan geometriler
        }
        
        return jsonify(route_data)
        
    except Exception as e:
        print(f"Rota detayları alınırken hata oluştu: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    # finally: # Eğer db session kullanılıyorsa finally bloğu gerekli olabilir
    #     db.session.close()

@company_routes.route('/api/route/<int:route_id>', methods=['DELETE'])
@login_required
@company_required
def delete_route(route_id):
    db = SessionLocal()
    try:
        route = db.query(Route).filter_by(
            id=route_id,
            company_id=current_user.company_id
        ).first()
        
        if not route:
            return jsonify({'success': False, 'error': 'Rota bulunamadı'}), 404
            
        if route.status.value != 'planned':
            return jsonify({'success': False, 'error': 'Sadece planlanmış rotalar silinebilir'}), 400
            
        # Önce rota detaylarını sil
        db.query(RouteDetail).filter_by(route_id=route.id).delete()
        
        # Sonra rotayı sil
        db.delete(route)
        db.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.rollback()
        print(f"Error deleting route: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()

@company_routes.route('/api/warehouse/add', methods=['POST'])
@login_required
@company_required
def add_warehouse():
    db = SessionLocal()
    try:
        data = request.get_json()
        
        # Şirket ID'sini mevcut kullanıcıdan al
        company_id = current_user.company_id
        
        warehouse = Warehouse(
            company_id=company_id,
            name=data['name'],
            address=data['address'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            capacity=data['capacity'],
            contact_person=data['contact_person'],
            contact_phone=data['contact_phone'],
            operating_hours=data['operating_hours'],
            is_active=data['is_active']
        )
        
        db.add(warehouse)
        db.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        print(f"Error adding warehouse: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()

@company_routes.route('/company/warehouse/<int:warehouse_id>', methods=['GET'])
@login_required
@company_required
def get_warehouse(warehouse_id):
    db = SessionLocal()
    try:
        warehouse = db.query(Warehouse).filter_by(
            id=warehouse_id,
            company_id=current_user.company_id
        ).first()
        
        if not warehouse:
            return jsonify({'success': False, 'error': 'Depo bulunamadı'}), 404
            
        return jsonify({
            'id': warehouse.id,
            'name': warehouse.name,
            'address': warehouse.address,
            'latitude': warehouse.latitude,
            'longitude': warehouse.longitude,
            'capacity': warehouse.capacity,
            'contact_person': warehouse.contact_person,
            'contact_phone': warehouse.contact_phone,
            'operating_hours': warehouse.operating_hours,
            'is_active': warehouse.is_active
        })
    except Exception as e:
        print(f"Error getting warehouse: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()

@company_routes.route('/company/warehouse/<int:warehouse_id>/edit', methods=['POST'])
@login_required
@company_required
def edit_warehouse(warehouse_id):
    db = SessionLocal()
    try:
        warehouse = db.query(Warehouse).filter_by(
            id=warehouse_id,
            company_id=current_user.company_id
        ).first()
        
        if not warehouse:
            return jsonify({'success': False, 'error': 'Depo bulunamadı'}), 404
            
        data = request.get_json()
        
        # Güvenli bir şekilde değerleri güncelle
        warehouse.name = data['name']
        warehouse.address = data['address']
        warehouse.latitude = data['latitude']
        warehouse.longitude = data['longitude']
        warehouse.capacity = data['capacity']
        warehouse.contact_person = data['contact_person']
        warehouse.contact_phone = data['contact_phone']
        warehouse.operating_hours = data['operating_hours']
        warehouse.is_active = data['is_active']
        
        db.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        print(f"Error editing warehouse: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()

@company_routes.route('/company/warehouse/<int:warehouse_id>/delete', methods=['POST'])
@login_required
@company_required
def delete_warehouse(warehouse_id):
    db = SessionLocal()
    try:
        warehouse = db.query(Warehouse).filter_by(
            id=warehouse_id,
            company_id=current_user.company_id
        ).first()
        
        if not warehouse:
            return jsonify({'success': False, 'error': 'Depo bulunamadı'}), 404
            
        # Deponun rotalarda kullanılıp kullanılmadığını kontrol et
        route_count = db.query(Route).filter_by(warehouse_id=warehouse.id).count()
        if route_count > 0:
            return jsonify({
                'success': False, 
                'error': 'Bu depo rotalarda kullanıldığı için silinemez'
            }), 400
            
        db.delete(warehouse)
        db.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        print(f"Error deleting warehouse: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close() 