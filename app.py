from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from alg_creator import run_tabu_search
from process_data import ProblemInstance
import os

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/optimize', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        instance_name = data.get('instance_name', '').lower()  # Ensure lowercase
        num_customers = data.get('num_customers', 15)
        
        print(f"Processing request for instance: {instance_name}")  # Debug log
        
        # Load problem instance with force recalculate
        problem_instance = ProblemInstance(instance_name, force_recalculate=True)
        instance = problem_instance.get_data()
        
        if instance is None:
            print(f"Failed to load instance: {instance_name}")  # Debug log
            return jsonify({'error': f'Failed to load problem instance: {instance_name}'}), 400
            
        # Run optimization
        routes = run_tabu_search(
            instance_name=instance_name,
            individual_size=num_customers,
            pop_size=100,
            n_gen=1200,
            tabu_size=45,
            plot=False,
            stagnation_limit=40,
            verbose=True,
            use_real_distances=True,
            early_stop_limit=200
        )
        
        if not routes:
            return jsonify({'error': 'No solution found'}), 400
            
        # Extract route information and split based on capacity
        route_data = []
        vehicle_capacity = float(instance.get('vehicle_capacity', 500))
        
        print(f"Processing {len(routes)} routes for {instance_name}")  # Debug log
        
        # Clear the instance data after processing
        problem_instance.clear_data()
        
        for main_route in routes:
            current_route = []
            current_load = 0
            
            # Add depot as starting point
            depot_coords = instance['depart']['coordinates']
            current_route.append({
                'name': 'Depot',
                'lat': float(depot_coords['x']),
                'lng': float(depot_coords['y']),
                'demand': 0
            })
            
            # Process each customer in the route
            for point_id in main_route:
                customer = instance[f'C_{point_id}']
                customer_coords = customer['coordinates']
                customer_demand = float(customer['demand'])
                
                # If adding this customer exceeds capacity, start a new route
                if current_load + customer_demand > vehicle_capacity:
                    # Complete current route by adding depot
                    current_route.append({
                        'name': 'Depot',
                        'lat': float(depot_coords['x']),
                        'lng': float(depot_coords['y']),
                        'demand': 0
                    })
                    route_data.append(current_route)
                    
                    # Start new route
                    current_route = [{
                        'name': 'Depot',
                        'lat': float(depot_coords['x']),
                        'lng': float(depot_coords['y']),
                        'demand': 0
                    }]
                    current_load = 0
                
                # Add customer to current route
                current_route.append({
                    'name': customer.get('comment', f'Customer {point_id}'),
                    'lat': float(customer_coords['x']),
                    'lng': float(customer_coords['y']),
                    'demand': customer_demand
                })
                current_load += customer_demand
            
            # Complete last route by adding depot
            if len(current_route) > 1:  # Only if route has customers
                current_route.append({
                    'name': 'Depot',
                    'lat': float(depot_coords['x']),
                    'lng': float(depot_coords['y']),
                    'demand': 0
                })
                route_data.append(current_route)
        
        print(f"Completed route calculation for {instance_name}")  # Debug log
        return jsonify({
            'success': True,
            'routes': route_data,
            'vehicle_capacity': vehicle_capacity
        })
        
    except Exception as e:
        print(f"Error in optimize_route: {str(e)}")  # Add detailed error logging
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
    app.run(debug=True) 