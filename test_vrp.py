from alg_creator import *
from process_data import ProblemInstance
import sys

if __name__ == "__main__":
    # Test parameters
    instance_name = "istanbultest"
    num_customers = 20
    
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
        pop_size=30,
        n_gen=300,
        tabu_size=25,
        plot=False,
        stagnation_limit=20,
        verbose=True,
        use_real_distances=True,
        early_stop_limit=90
    )
    
    if routes:
        print("\nOptimal routes found!")
        
        # Create GraphHopper navigation link
        nav_url = create_navigation_link(routes, instance)
        print("\nGraphHopper Navigation Link:")
        print(nav_url)
    else:
        print("No solution found!")