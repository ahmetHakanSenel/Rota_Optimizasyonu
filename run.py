import sys
from alg_creator import *

if __name__ == '__main__':

    if len(sys.argv) != 3:
        print("invalid arguments")
        sys.exit()

    random.seed(231)
    plot_result = True

    problem_name = str(sys.argv[1])
    alg_name = str(sys.argv[2])

    customers_count = 25
    max_generations = 1500
    early_stop_threshold = 60
    
    particles_pop_size = 80
    cognitive_acceleration = 2
    social_acceleration = 2
    speed_limit = 1.5

    population_size = 150
    tabu_list_size = 50

    print('### GENERAL INFO ###')
    print('Problem name: ' + problem_name)
    print(f'Customer count: {customers_count}')
    print(f'Max iterations: {max_generations}')
    print('Algorithm: ' + alg_name)
    print('### ALGORITHM PARAMETERS ###')

    '''
    for mutation_prob in [0.03, 0.09]:
    for crossover_prob in [0.5, 0.7, 0.9]:
    for speed_limit in [1.5, 3]:
    for cognitive_acceleration, social_acceleration in [[2, 2], [1.5, 2.5], [2.5, 1.5]]:
    '''

    if alg_name == "PSO":
        print(f'Particles population size: {particles_pop_size}')
        print(f'Social acceleration: {social_acceleration}')
        print(f'Cognitive acceleration: {cognitive_acceleration}')
        print(f'Speed limit: {speed_limit}')
        print(f'Early stopping threshold: {early_stop_threshold}')
        res = run_pso(instance_name=problem_name, 
                      particle_size=customers_count, 
                      pop_size=population_size,
                      max_iteration=max_generations,
                      cognitive_coef=cognitive_acceleration,
                      social_coef=social_acceleration, 
                      s_limit=speed_limit, 
                      plot=plot_result)

    elif alg_name == "TABU":
        print(f'Population size: {population_size}')
        print(f'Tabu list size: {tabu_list_size}')
        print(f'Using real-world distances')
        
        res = run_tabu_search(
            instance_name=problem_name,
            individual_size=customers_count,
            pop_size=population_size,
            n_gen=max_generations,
            tabu_size=tabu_list_size,
            plot=plot_result,
            stagnation_limit=50,
            verbose=True,
            use_real_distances=True,
            api_key="YOUR_GOOGLE_MAPS_API_KEY",  # veya
            city_name="Istanbul, Turkey"  # OSM için
        )
    else:
        print("invalid algorithm")
        sys.exit()

