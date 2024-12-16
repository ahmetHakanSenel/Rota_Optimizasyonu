from core_funs import *
from deap import base, creator, tools
from route_optimizer import VRPOptimizer
import matplotlib.pyplot as plt
import numpy
import time
import collections
from concurrent.futures import ThreadPoolExecutor
import osmnx as ox
from geopy.distance import geodesic
import networkx as nx
import math
from process_data import MapHandler  # MapHandler'ı process_data'dan import edelim

# plot data from given problem with chosen customer amount
def plot_instance(instance_name, customer_number):

    instance = load_problem_instance(instance_name)
    depot = [instance[DEPART][COORDINATES][X_COORD], instance[DEPART][COORDINATES][Y_COORD]]
    dep, = plt.plot(depot[0], depot[1], 'kP', label='depot')

    for customer_id in range(1,customer_number):
        coordinates = [instance[F'C_{customer_id}'][COORDINATES][X_COORD],
                       instance[F'C_{customer_id}'][COORDINATES][Y_COORD]]
        custs, = plt.plot(coordinates[0], coordinates[1], 'ro', label='customers')
    plt.ylabel("y coordinate")
    plt.xlabel("x coordinate")
    plt.legend([dep, custs], ['depot', 'customers'], loc=1)
    plt.show()


# plot the result
def plot_route(route, instance_name):
    instance = load_problem_instance(instance_name)
    
    # Create map handler
    map_handler = MapHandler()
    
    # Visualize route on real map
    map_handler.visualize_route(route, instance)
    
    # Also show the traditional plot
    plot_traditional_route(route, instance)  # Rename the old plot_route to plot_traditional_route


# printing the solution
def print_route(route):
    route_num = 0
    for sub_route in route:
        route_num += 1
        single_route = '0'
        for customer_id in sub_route:
            single_route = f'{single_route} -> {customer_id}'
        single_route = f'{single_route} -> 0'
        print(f' # Route {route_num} # {single_route}')

def run_pso(instance_name, particle_size, pop_size, max_iteration,
            cognitive_coef, social_coef, s_limit=3, plot=False, save=False, logs=False, early_stop_threshold=400, verbose=False):

    instance = load_problem_instance(instance_name)

    if instance is None:
        return

    if plot:
        plot_instance(instance_name=instance_name, customer_number=particle_size)

    creator.create("FitnessMax", base.Fitness, weights=(1.0, 1.0))
    creator.create("Particle", list, fitness=creator.FitnessMax, speed=list,
                   smin=None, smax=None, best=None)

    toolbox = base.Toolbox()
    toolbox.register("particle", generate_particle,
                     size=particle_size,
                     s_min=-s_limit,
                     s_max=s_limit)
    toolbox.register("population", tools.initRepeat, list, toolbox.particle)
    toolbox.register("update", update_particle, phi1=cognitive_coef, phi2=social_coef)
    toolbox.register('evaluate', calculate_fitness, data=instance)

    pop = toolbox.population(n=pop_size)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", numpy.mean)
    stats.register("std", numpy.std)
    stats.register("min", numpy.min)
    stats.register("max", numpy.max)

    logbook = tools.Logbook()
    logbook.header = ["gen", "evals"] + stats.fields

    best = None
    iter_num = 0
    previous_best = 0
    generations_without_improvement = 0
    best_fitness = float('-inf')

    print('### EVOLUTION START ###')
    start = time.time()

    for g in range(max_iteration):
        fit_count = 0
        for part in pop:
            part.fitness.values = toolbox.evaluate(part)
            if part.fitness.values[0] > previous_best:
                previous_best = part.fitness.values[0]
                iter_num = g + 1
            elif part.fitness.values[0] == previous_best:
                fit_count += 1

        current_best_fitness = max([p.fitness.values[0] for p in pop])
        if verbose:
            print(f"Generation {g}: Best Fitness = {current_best_fitness}")

        if current_best_fitness > best_fitness:
            best_fitness = current_best_fitness
            generations_without_improvement = 0
        else:
            generations_without_improvement += 1

        if generations_without_improvement >= early_stop_threshold:
            print(f"Early stopping at generation {g}: No improvement for {early_stop_threshold} generations")
            break

        if fit_count > int(numpy.ceil(pop_size * 0.15)):
            rand_pop = toolbox.population(n=pop_size)
            for part in rand_pop:
                part.fitness.values = toolbox.evaluate(part)
            some_inds = tools.selRandom(rand_pop, int(numpy.ceil(pop_size * 0.1)))  # random pop here
            mod_pop = tools.selWorst(pop, int(numpy.ceil(pop_size * 0.9)))
        else:
            some_inds = tools.selBest(pop, int(numpy.ceil(pop_size * 0.05)))  # elite pop here
            mod_pop = tools.selRandom(pop, int(numpy.ceil(pop_size * 0.95)))

        mod_pop = list(map(toolbox.clone, mod_pop))

        for part in mod_pop:
            if not part.best or part.best.fitness < part.fitness:
                part.best = creator.Particle(part)
                part.best.fitness.values = part.fitness.values
            if not best or best.fitness < part.fitness:
                best = creator.Particle(part)
                best.fitness.values = part.fitness.values

        for part in mod_pop:
            toolbox.update(part, best)

        mod_pop.extend(some_inds)
        pop[:] = mod_pop

        # Gather all the stats in one list and print them
        logbook.record(gen=g+1, evals=len(pop), **stats.compile(pop))
        print(logbook.stream)

    end = time.time()
    print('### EVOLUTION END ###')
    best_ind = tools.selBest(pop, 1)[0]
    print(f'Best individual: {best_ind}')
    route = create_route_from_ind(best_ind, instance)
    print_route(route)
    print(f'Fitness: { round(best_ind.fitness.values[0],2) }')
    print(f'Total cost: { round(calculate_fitness(best_ind, instance)[1],2) }')
    print(f'Found in (iteration): { iter_num }')
    print(f'Execution time (s): { round(end - start,2) }')
    # print(f'{round(best_ind.fitness.values[0], 2)} & {round(calculate_fitness(best_ind, instance)[1],2)} & {iter_num} & {round(end - start, 2)}')

    if plot:
        plot_route(route=route, instance_name=instance_name)

    return route


class AdaptiveTabuList:
    def __init__(self, initial_size, max_size):
        self.max_size = max_size
        self.list = collections.deque(maxlen=initial_size)
        self.current_size = initial_size

    def add(self, solution):
        self.list.append(tuple(solution))
        # Dynamically adjust the size
        if len(self.list) >= self.current_size:
            self.current_size = min(self.current_size + 1, self.max_size)

    def contains(self, solution):
        return tuple(solution) in self.list

    def clear(self):
        self.list.clear()
        self.current_size = len(self.list)

def run_tabu_search(instance_name, individual_size, pop_size, n_gen, tabu_size, 
                   plot=False, stagnation_limit=50, verbose=True):
    """Run tabu search algorithm with real road distances"""
    instance = load_problem_instance(instance_name)
    
    # Initialize parameters
    best_solution = None
    best_distance = float('inf')
    tabu_list = AdaptiveTabuList(tabu_size, tabu_size * 2)
    stagnation_counter = 0
    map_handler = MapHandler()  # Singleton instance
    
    # Create initial solution
    current_solution = create_initial_solution(instance, individual_size)
    current_distance = evaluate_solution_with_real_distances(current_solution, instance, map_handler)
    
    for iteration in range(n_gen):
        improved = False
        neighbors = generate_neighbors(current_solution)
        best_neighbor = None
        best_neighbor_distance = float('inf')
        
        # Evaluate neighbors
        for neighbor in neighbors:
            if not tabu_list.contains(neighbor):
                distance = evaluate_solution_with_real_distances(neighbor, instance, map_handler)
                if distance < best_neighbor_distance:
                    best_neighbor = neighbor
                    best_neighbor_distance = distance
                    if distance < best_distance:
                        improved = True
        
        if best_neighbor is not None:
            current_solution = best_neighbor
            current_distance = best_neighbor_distance
            tabu_list.add(current_solution)
            
            if best_neighbor_distance < best_distance:
                best_solution = best_neighbor.copy()
                best_distance = best_neighbor_distance
                stagnation_counter = 0
            else:
                stagnation_counter += 1
        
        if verbose and iteration % 10 == 0:
            print(f"Iteration {iteration}, Best distance: {best_distance:.2f} km")
        
        if stagnation_counter >= stagnation_limit:
            print(f"Early stopping at iteration {iteration} due to stagnation")
            break
    
    if best_solution:
        routes = decode_solution(best_solution, instance)
        if plot:
            map_handler.visualize_route(routes, instance)
        return routes
    
    return None

def evaluate_solution_with_real_distances(solution, instance, map_handler):
    """Calculate total distance using real road network"""
    total_distance = 0
    prev_point = (instance[DEPART][COORDINATES][X_COORD], 
                 instance[DEPART][COORDINATES][Y_COORD])
    
    for customer_id in solution:
        curr_point = (instance[f'C_{customer_id}'][COORDINATES][X_COORD],
                     instance[f'C_{customer_id}'][COORDINATES][Y_COORD])
        total_distance += map_handler.calculate_route_distance(prev_point, curr_point)
        prev_point = curr_point
    
    # Return to depot
    depot_point = (instance[DEPART][COORDINATES][X_COORD],
                  instance[DEPART][COORDINATES][Y_COORD])
    total_distance += map_handler.calculate_route_distance(prev_point, depot_point)
    
    return total_distance

def calculate_bearing(point1, point2):
    """Calculate bearing between two points"""
    lat1, lon1 = point1
    lat2, lon2 = point2
    
    d_lon = lon2 - lon1
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    bearing = math.atan2(y, x)
    
    return math.degrees(bearing)

def plot_traditional_route(route, instance):
    depot = [instance[DEPART][COORDINATES][X_COORD], instance[DEPART][COORDINATES][Y_COORD]]
    dep, = plt.plot(depot[0], depot[1], 'kP')
    
    colors = ['r-', 'b-', 'g-', 'm-', 'y-', 'c-']
    for i, sub_route in enumerate(route):
        color = colors[i % len(colors)]
        coords = [[instance[F'C_{j}'][COORDINATES][X_COORD], 
                  instance[F'C_{j}'][COORDINATES][Y_COORD]] for j in sub_route]
        coords.insert(0, depot)
        coords.append(depot)
        xs, ys = zip(*coords)
        plt.plot(xs, ys, color)
        
    plt.ylabel("y coordinate")
    plt.xlabel("x coordinate")
    plt.show()

def create_initial_solution(instance, size):
    """Create initial random solution"""
    return list(range(1, size + 1))

def generate_neighbors(solution):
    """Generate neighborhood solutions using swap operations"""
    neighbors = []
    for i in range(len(solution)):
        for j in range(i + 1, len(solution)):
            neighbor = solution.copy()
            neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
            neighbors.append(neighbor)
    return neighbors

def decode_solution(solution, instance):
    """Convert solution to route format"""
    # For now, just return single route
    return [solution]