import sys
from alg_creator import run_tabu_search
import random

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("invalid arguments")
        sys.exit()

    random.seed(231)
    
    problem_name = str(sys.argv[1])
    alg_name = str(sys.argv[2])

    customers_count = 25
    max_generations = 1500
    early_stop_threshold = 60
    
    population_size = 150
    tabu_list_size = 50

    print('### GENERAL INFO ###')
    print('Problem name: ' + problem_name)
    print(f'Customer count: {customers_count}')
    print(f'Max iterations: {max_generations}')
    print('Algorithm: ' + alg_name)
    print('### ALGORITHM PARAMETERS ###')

    if alg_name == "TABU":
        print(f'Population size: {population_size}')
        print(f'Tabu list size: {tabu_list_size}')
        print(f'Using real-world distances with OSRM')
        
        res = run_tabu_search(
            instance_name=problem_name,
            individual_size=customers_count,
            pop_size=population_size,
            n_gen=max_generations,
            tabu_size=tabu_list_size,
            plot=False,
            stagnation_limit=50,
            verbose=True,
            use_real_distances=True
        )
    else:
        print("invalid algorithm")
        sys.exit()

