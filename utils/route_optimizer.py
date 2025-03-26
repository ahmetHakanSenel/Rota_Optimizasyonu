import random
import numpy as np
from typing import List, Dict, Any
from models import Customer, Warehouse, Vehicle, Driver, VehicleStatus
from utils.osrm_handler import OSRMHandler
from sqlalchemy.orm import Session
from alg_creator import run_tabu_search

def optimize_routes(
    db: Session,
    company_id: int,
    num_customers: int = 5
) -> Dict[str, Any]:
    """
    Optimize delivery routes for a company using Tabu Search.
    
    Args:
        db: Database session
        company_id: ID of the company
        num_customers: Number of customers to include in routes (0 means use all customers)
        
    Returns:
        Dictionary containing optimization results
    """
    try:
        # Get company's active warehouse
        warehouse = db.query(Warehouse).filter_by(
            company_id=company_id,
            is_active=True
        ).first()
        
        if not warehouse:
            return {
                'success': False,
                'error': 'No active warehouse found for this company'
            }
            
        # Get company's active vehicles with their drivers
        vehicles = db.query(Vehicle).filter(
            Vehicle.company_id == company_id,
            Vehicle.status == VehicleStatus.ACTIVE,
            Vehicle.driver_id.isnot(None)
        ).all()
        
        if not vehicles:
            return {
                'success': False,
                'error': 'No active vehicles with assigned drivers found'
            }
            
        # Get company's customers
        customers = db.query(Customer).filter_by(company_id=company_id).all()
        
        if len(customers) == 0:
            return {
                'success': False,
                'error': 'No customers found for this company'
            }
            
        # If num_customers is 0, use all customers
        if num_customers == 0:
            num_customers = len(customers)
            selected_customers = customers
        else:
            # Check if we have enough customers
            if len(customers) < num_customers:
                return {
                    'success': False,
                    'error': f'Not enough customers. Have {len(customers)}, need {num_customers}'
                }
            # Randomly select customers
            selected_customers = random.sample(customers, num_customers)
            
        # Get vehicle capacities
        vehicle_capacities = [v.capacity for v in vehicles]
        min_vehicle_capacity = min(vehicle_capacities) if vehicle_capacities else 0
        
        # Create instance data for Tabu Search
        instance_data = {
            'instance_name': 'custom',
            'max_vehicle_number': len(vehicles),
            'vehicle_capacity': float(min_vehicle_capacity),
            'depart': {
                'coordinates': {
                    'x': float(warehouse.latitude),
                    'y': float(warehouse.longitude)
                },
                'demand': 0.0
            }
        }
        
        # Add customers to instance data
        total_demand = 0.0
        for i, customer in enumerate(selected_customers, 1):
            demand = float(customer.desi)
            total_demand += demand
            instance_data[f'C_{i}'] = {
                'coordinates': {
                    'x': float(customer.latitude),
                    'y': float(customer.longitude)
                },
                'demand': demand
            }
            
        # Check if total demand exceeds total vehicle capacity
        total_capacity = sum(float(v.capacity) for v in vehicles)
        if total_demand > total_capacity:
            return {
                'success': False,
                'error': f'Total demand ({total_demand:.2f}) exceeds total vehicle capacity ({total_capacity:.2f})'
            }
            
        # Initialize OSRM handler and precompute distances
        osrm_handler = OSRMHandler()
        if not osrm_handler.precompute_distances(instance_data):
            return {
                'success': False,
                'error': 'Failed to compute distances between locations'
            }
            
        # Run Tabu Search with adjusted parameters
        result = run_tabu_search(
            instance_data=instance_data,
            individual_size=num_customers,
            n_gen=min(500, num_customers * 20),
            tabu_size=min(20, num_customers // 2 + 5),
            stagnation_limit=15,
            vehicle_capacity=float(min_vehicle_capacity)
        )
        
        if not result:
            return {
                'success': False,
                'error': 'No feasible solution found. Try reducing the number of customers or increasing vehicle capacity.'
            }
            
        # Process results and assign vehicles/drivers
        routes = []
        vehicle_index = 0
        
        for sub_route in result:
            if not sub_route or vehicle_index >= len(vehicles):
                break
                
            vehicle = vehicles[vehicle_index]
            route_customers = []
            total_demand = 0.0
            
            for customer_id in sub_route:
                if 0 <= customer_id - 1 < len(selected_customers):
                    customer = selected_customers[customer_id - 1]
                    route_customers.append(customer)
                    total_demand += float(customer.desi)
                
            if total_demand <= float(vehicle.capacity):
                routes.append({
                    'vehicle': vehicle,
                    'driver': vehicle.driver,
                    'warehouse': warehouse,
                    'customers': route_customers,
                    'total_demand': total_demand
                })
                vehicle_index += 1
                
        if not routes:
            return {
                'success': False,
                'error': 'Could not assign routes to vehicles. Please check vehicle capacities.'
            }
            
        return {
            'success': True,
            'routes': routes,
            'total_vehicles': len(routes)
        }
        
    except Exception as e:
        print(f"Optimization error: {str(e)}")
        return {
            'success': False,
            'error': f'An error occurred during optimization: {str(e)}'
        } 