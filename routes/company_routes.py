from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import Company, Driver, Vehicle, Route, RouteDetail, Customer, Warehouse, RouteStatus
from database import db
from datetime import datetime
from sqlalchemy import and_
from utils.route_optimizer import optimize_routes
from utils.auth import company_required
from process_data import OSRMHandler

company_routes = Blueprint('company_routes', __name__)

@company_routes.route('/api/optimize', methods=['POST'])
@login_required
@company_required
def optimize():
    try:
        data = request.get_json()
        num_customers = data.get('num_customers', 5)
        
        # If num_customers is 0, use all customers
        if num_customers != 0 and num_customers < 2:
            return jsonify({
                'success': False,
                'error': 'Number of customers must be at least 2 or 0 to use all customers'
            }), 400
            
        if num_customers != 0 and num_customers > 15:
            return jsonify({
                'success': False,
                'error': 'Number of customers cannot exceed 15'
            }), 400
        
        # Rota optimizasyonu için depo bilgilerini al
        warehouse = Warehouse.query.filter_by(company_id=current_user.company_id, is_active=True).first()
        if not warehouse:
            return jsonify({'success': False, 'error': 'No active warehouse found for this company'}), 404
        
        # Rota optimizasyonunu çalıştır
        result = optimize_routes(
            db=db.session,
            company_id=current_user.company_id,
            num_customers=num_customers
        )
        
        if not result['success']:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 400
            
        # Create routes in database
        created_routes = []
        for route_data in result['routes']:
            route = Route(
                company_id=current_user.company_id,
                driver_id=route_data['driver'].id,
                vehicle_id=route_data['vehicle'].id,
                warehouse_id=warehouse.id,
                status=RouteStatus.PLANNED,
                total_demand=route_data['total_demand'],
                total_distance=0.0,  # Will be updated later
                created_at=datetime.utcnow()
            )
            db.session.add(route)
            db.session.flush()  # Get route ID
            
            # Add route details
            for sequence, customer in enumerate(route_data['customers'], 1):
                detail = RouteDetail(
                    route_id=route.id,
                    customer_id=customer.id,
                    sequence_number=sequence,
                    demand=float(customer.desi),
                    status='pending'
                )
                db.session.add(detail)
            
            created_routes.append(route)
            
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Created {len(created_routes)} routes successfully',
            'routes': [{
                'id': route.id,
                'driver': f"{route.driver.user.first_name} {route.driver.user.last_name}",
                'vehicle': route.vehicle.plate_number,
                'total_demand': route.total_demand,
                'num_stops': len(route.route_details)
            } for route in created_routes]
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500

@company_routes.route('/api/route/<int:route_id>', methods=['GET'])
@login_required
@company_required
def get_route(route_id):
    try:
        route = Route.query.filter_by(
            id=route_id,
            company_id=current_user.company_id
        ).first()
        
        if not route:
            return jsonify({'success': False, 'error': 'Route not found'}), 404
        
        # OSRM handler'ı başlat
        osrm_handler = OSRMHandler()
        
        # Rota geometrilerini hazırla
        route_geometries = []
        
        # Depo koordinatları
        warehouse_coords = (route.warehouse.latitude, route.warehouse.longitude)
        
        # Durakları sıraya göre al
        stops = sorted(route.route_details, key=lambda x: x.sequence)
        
        if stops:
            # Depodan ilk müşteriye
            first_stop = stops[0]
            first_coords = (first_stop.customer.latitude, first_stop.customer.longitude)
            
            # Rota detaylarını al
            first_segment = osrm_handler.get_route_details(warehouse_coords, first_coords)
            if first_segment:
                route_geometries.append({
                    'from': 'warehouse',
                    'to': f'customer_{first_stop.customer.id}',
                    'coordinates': first_segment.get('coordinates', [])
                })
            
            # Müşteriler arası
            for i in range(len(stops) - 1):
                start_stop = stops[i]
                end_stop = stops[i + 1]
                
                start_coords = (start_stop.customer.latitude, start_stop.customer.longitude)
                end_coords = (end_stop.customer.latitude, end_stop.customer.longitude)
                
                segment = osrm_handler.get_route_details(start_coords, end_coords)
                if segment:
                    route_geometries.append({
                        'from': f'customer_{start_stop.customer.id}',
                        'to': f'customer_{end_stop.customer.id}',
                        'coordinates': segment.get('coordinates', [])
                    })
            
            # Son müşteriden depoya
            last_stop = stops[-1]
            last_coords = (last_stop.customer.latitude, last_stop.customer.longitude)
            
            last_segment = osrm_handler.get_route_details(last_coords, warehouse_coords)
            if last_segment:
                route_geometries.append({
                    'from': f'customer_{last_stop.customer.id}',
                    'to': 'warehouse',
                    'coordinates': last_segment.get('coordinates', [])
                })
            
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
                'capacity': route.vehicle.capacity
            } if route.vehicle else None,
            'warehouse': {
                'id': route.warehouse.id,
                'name': route.warehouse.name,
                'address': route.warehouse.address,
                'latitude': route.warehouse.latitude,
                'longitude': route.warehouse.longitude
            },
            'total_distance': route.total_distance,
            'total_demand': route.total_demand,
            'status': route.status,
            'created_at': route.created_at.isoformat(),
            'stops': [{
                'id': detail.id,
                'sequence': detail.sequence,
                'demand': detail.demand,
                'status': detail.status,
                'customer': {
                    'id': detail.customer.id,
                    'name': detail.customer.name,
                    'address': detail.customer.address,
                    'contact_person': detail.customer.contact_person,
                    'contact_phone': detail.customer.contact_phone,
                    'latitude': detail.customer.latitude,
                    'longitude': detail.customer.longitude
                }
            } for detail in route.route_details],
            'route_geometries': route_geometries
        }
        
        return jsonify(route_data)
        
    except Exception as e:
        print(f"Error getting route details: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@company_routes.route('/api/route/<int:route_id>', methods=['DELETE'])
@login_required
@company_required
def delete_route(route_id):
    try:
        route = Route.query.filter_by(
            id=route_id,
            company_id=current_user.company_id
        ).first()
        
        if not route:
            return jsonify({'success': False, 'error': 'Route not found'}), 404
            
        if route.status.value != 'planned':
            return jsonify({'success': False, 'error': 'Only planned routes can be deleted'}), 400
            
        # Delete route details first
        RouteDetail.query.filter_by(route_id=route.id).delete()
        
        # Delete route
        db.session.delete(route)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@company_routes.route('/api/warehouse/add', methods=['POST'])
@login_required
@company_required
def add_warehouse():
    try:
        data = request.get_json()
        
        # Şirket ID'sini kontrol et
        if current_user.company_id != data['company_id']:
            return jsonify({'success': False, 'error': 'Unauthorized to add warehouse for this company'}), 403
        
        warehouse = Warehouse(
            company_id=data['company_id'],
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
        
        db.session.add(warehouse)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@company_routes.route('/company/warehouse/<int:warehouse_id>', methods=['GET'])
@login_required
@company_required
def get_warehouse(warehouse_id):
    try:
        warehouse = Warehouse.query.filter_by(
            id=warehouse_id,
            company_id=current_user.company_id
        ).first()
        
        if not warehouse:
            return jsonify({'success': False, 'error': 'Warehouse not found'}), 404
            
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
        return jsonify({'success': False, 'error': str(e)}), 500

@company_routes.route('/company/warehouse/<int:warehouse_id>/edit', methods=['POST'])
@login_required
@company_required
def edit_warehouse(warehouse_id):
    try:
        warehouse = Warehouse.query.filter_by(
            id=warehouse_id,
            company_id=current_user.company_id
        ).first()
        
        if not warehouse:
            return jsonify({'success': False, 'error': 'Warehouse not found'}), 404
            
        data = request.get_json()
        
        warehouse.name = data['name']
        warehouse.address = data['address']
        warehouse.latitude = data['latitude']
        warehouse.longitude = data['longitude']
        warehouse.capacity = data['capacity']
        warehouse.contact_person = data['contact_person']
        warehouse.contact_phone = data['contact_phone']
        warehouse.operating_hours = data['operating_hours']
        warehouse.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@company_routes.route('/company/warehouse/<int:warehouse_id>/delete', methods=['POST'])
@login_required
@company_required
def delete_warehouse(warehouse_id):
    try:
        warehouse = Warehouse.query.filter_by(
            id=warehouse_id,
            company_id=current_user.company_id
        ).first()
        
        if not warehouse:
            return jsonify({'success': False, 'error': 'Warehouse not found'}), 404
            
        # Check if warehouse is used in any routes
        if warehouse.routes:
            return jsonify({
                'success': False, 
                'error': 'Cannot delete warehouse that is used in routes'
            }), 400
            
        db.session.delete(warehouse)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500 