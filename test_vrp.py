from alg_creator import *
from process_data import ProblemInstance
import sys

if __name__ == "__main__":
    # Test parameters
    instance_name = "bursa"
    num_customers = 15
    
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
    res = run_tabu_search(
        instance_name=instance_name,
        individual_size=num_customers,
        n_gen=1200,
        tabu_size=45,
        stagnation_limit=50,
        verbose=True
    )
    
    if res:
        print("\nOptimal routes found!")
        
        # Create GraphHopper navigation link
        nav_url = create_navigation_link(res, instance)
        print("\nGraphHopper Navigation Link:")
        print(nav_url)
    else:
        print("No solution found!")