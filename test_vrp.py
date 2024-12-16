from alg_creator import *
from route_optimizer import VRPOptimizer
import webbrowser
import os
import multiprocessing
from process_data import MapHandler
import sys

if __name__ == "__main__":
    # Test parameters
    instance_name = "istanbultest"
    num_customers = 15
    
    print("Loading problem instance...")
    try:
        instance = load_problem_instance(instance_name)
        if instance is None:
            print("Failed to load problem instance")
            sys.exit(1)
    except Exception as e:
        print(f"Error loading problem instance: {e}")
        sys.exit(1)
    
    # Initialize map handler once
    print("Initializing map handler...")
    try:
        map_handler = MapHandler("Istanbul, Turkey")
    except Exception as e:
        print(f"Error initializing map handler: {e}")
        sys.exit(1)
    
    # Show initial locations
    print("Showing initial customer locations...")
    try:
        map_file = show_initial_locations(instance)
        webbrowser.open('file://' + os.path.realpath(map_file))
    except Exception as e:
        print(f"Error showing initial locations: {e}")
        sys.exit(1)
    
    print("\nStarting VRP optimization with Tabu Search...")
    routes = run_tabu_search(
        instance_name=instance_name,
        individual_size=num_customers,
        pop_size=50,
        n_gen=100,
        tabu_size=20,
        plot=True,
        stagnation_limit=30,
        verbose=True
    )
    
    if routes:
        print("\nOptimal routes found!")
        total_distance = 0
        print("\nRoute details:")
        for i, route in enumerate(routes):
            route_distance = 0
            total_demand = sum(int(instance[f'C_{j}'][DEMAND]) for j in route)
            
            # Calculate actual route distance using the singleton MapHandler
            prev_point = (instance[DEPART][COORDINATES][X_COORD], 
                         instance[DEPART][COORDINATES][Y_COORD])
            
            for j in route:
                curr_point = (instance[f'C_{j}'][COORDINATES][X_COORD],
                            instance[f'C_{j}'][COORDINATES][Y_COORD])
                route_distance += map_handler.calculate_route_distance(prev_point, curr_point)
                prev_point = curr_point
            
            # Add return to depot
            route_distance += map_handler.calculate_route_distance(prev_point, 
                (instance[DEPART][COORDINATES][X_COORD],
                 instance[DEPART][COORDINATES][Y_COORD]))
            
            total_distance += route_distance
            print(f"Route {i+1}: Depot -> {' -> '.join(str(x) for x in route)} -> Depot")
            print(f"Route {i+1} distance: {route_distance:.2f} km")
            print(f"Route {i+1} total demand: {total_demand}")
        
        print(f"\nTotal distance: {total_distance:.2f} km")
        
        # Create and show navigation link
        nav_url = create_navigation_link(routes, instance)
        print("\nNavigation link:")
        print(nav_url)
        
        print("\nOpening route map in browser...")
        webbrowser.open('file://' + os.path.realpath('route_map.html'))
    else:
        print("No solution found!")