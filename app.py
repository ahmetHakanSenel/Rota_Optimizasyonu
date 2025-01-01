from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from alg_creator import run_tabu_search
from process_data import ProblemInstance
import os

app = Flask(__name__, static_folder='static')
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/optimize', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        instance_name = data.get('instance_name', '').lower()
        num_customers = int(data.get('num_customers', 15))
        vehicle_capacity = float(data.get('vehicle_capacity', 500))
        
        print(f"\nProcessing request for instance: {instance_name}")
        print(f"Requested customers: {num_customers}")
        print(f"Vehicle capacity: {vehicle_capacity}")
        
        problem_instance = ProblemInstance(instance_name, force_recalculate=True)
        instance = problem_instance.get_data()
        
        if instance is None:
            print(f"Failed to load instance: {instance_name}")
            return jsonify({'error': f'Failed to load problem instance: {instance_name}'}), 400
            
        if 'depart' not in instance:
            return jsonify({'error': f'No depot found in instance {instance_name}'}), 400
            
        customer_keys = sorted([k for k in instance.keys() if k.startswith('C_') and k != 'COORDINATES'])
        available_customers = len(customer_keys)
        
        print(f"Found {available_customers} customers in instance {instance_name}")
        print(f"Customer IDs: {[k.split('_')[1] for k in customer_keys]}")
        
        if available_customers == 0:
            return jsonify({'error': f'No customers found in instance {instance_name}'}), 400
            
        if num_customers > available_customers:
            return jsonify({
                'error': f'Requested {num_customers} customers but instance only has {available_customers} customers'
            }), 400
        
        instance['vehicle_capacity'] = vehicle_capacity
            
        routes = run_tabu_search(
            instance_name=instance_name,
            individual_size=num_customers,
            n_gen=1200,
            tabu_size=45,
            stagnation_limit=40,
            verbose=True,
            early_stop_limit=200,
            vehicle_capacity=vehicle_capacity
        )
        
        if not routes:
            print("No solution found. Vehicle capacity might be too small for the total demand.")
            total_demand = sum(float(instance[f'C_{i}']['demand']) for i in range(1, num_customers + 1))
            return jsonify({
                'error': f'No solution found. Total demand ({total_demand}) might be too large for the vehicle capacity ({vehicle_capacity})'
            }), 400
            
        route_data = []
        
        print(f"Processing {len(routes)} routes for {instance_name}")  # Debug log
        
        problem_instance.clear_data()
        
        for main_route in routes:
            current_route = []
            current_load = 0
            
            depot_coords = instance['depart']['coordinates']
            current_route.append({
                'name': 'Depo',
                'lat': float(depot_coords['x']),
                'lng': float(depot_coords['y']),
                'demand': 0
            })
            
            for point_id in main_route:
                customer = instance[f'C_{point_id}']
                customer_coords = customer['coordinates']
                customer_demand = float(customer['demand'])
                
                if current_load + customer_demand > vehicle_capacity:
                    current_route.append({
                        'name': 'Depo',
                        'lat': float(depot_coords['x']),
                        'lng': float(depot_coords['y']),
                        'demand': 0
                    })
                    route_data.append(current_route)
                    
                    current_route = [{
                        'name': 'Depo',
                        'lat': float(depot_coords['x']),
                        'lng': float(depot_coords['y']),
                        'demand': 0
                    }]
                    current_load = 0
                
                current_route.append({
                    'name': customer.get('comment', f'Customer {point_id}'),
                    'lat': float(customer_coords['x']),
                    'lng': float(customer_coords['y']),
                    'demand': customer_demand
                })
                current_load += customer_demand
            
            if len(current_route) > 1:
                current_route.append({
                    'name': 'Depo',
                    'lat': float(depot_coords['x']),
                    'lng': float(depot_coords['y']),
                    'demand': 0
                })
                route_data.append(current_route)
        
        print(f"Completed route calculation for {instance_name}")
        return jsonify({
            'success': True,
            'routes': route_data,
            'vehicle_capacity': vehicle_capacity
        })
        
    except Exception as e:
        print(f"Error in optimize_route: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/instances')
def get_instances():
    try:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
        instances = [f.split('.')[0] for f in os.listdir(data_dir) if f.endswith('.txt')]
        return jsonify({'instances': instances})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 