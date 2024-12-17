from alg_creator import *
from process_data import ProblemInstance
import sys

if __name__ == "__main__":
    # Test parameters
    instance_name = "istanbultest2"
    num_customers = 20
    google_maps_api_key = "AIzaSyCO3wVT_K8qgm8Ni9M1hn4lgPGqYB8l9G4"
    
    print("Loading problem instance...")
    try:
        # Use ProblemInstance singleton
        problem_instance = ProblemInstance(instance_name)
        instance = problem_instance.get_data()
        if instance is None:
            print("Failed to load problem instance")
            sys.exit(1)
    except Exception as e:
        print(f"Error loading problem instance: {e}")
        sys.exit(1)
    
    print("\nStarting VRP optimization with Tabu Search...")
    routes = run_tabu_search(
        instance_name=instance_name,
        individual_size=num_customers,
        pop_size=25,
        n_gen=300,
        tabu_size=15,
        plot=False,
        stagnation_limit=30,
        verbose=True,
        use_real_distances=True,
        api_key=google_maps_api_key
    )
    
    if routes:
        print("\nOptimal routes found!")
        
        # Create Google Maps navigation link
        nav_url = create_navigation_link(routes, instance)
        print("\nGoogle Maps Navigation Link:")
        print(nav_url)
    else:
        print("No solution found!")