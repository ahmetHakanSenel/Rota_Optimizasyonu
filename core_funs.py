import random
import operator
import math
import collections

from deap import base, creator, tools # type: ignore
from process_data import *


def create_route_from_ind(individual, data):
    vehicle_capacity = data[VEHICLE_CAPACITY]
    route = []
    sub_route = []
    vehicle_load = vehicle_capacity
    
    i = 0
    while i < len(individual):
        current_customer = individual[i]
        current_demand = data[F'C_{current_customer}'][DEMAND]
        

        if vehicle_load >= current_demand:

            if i + 1 < len(individual):
                next_customer = individual[i + 1]
                next_demand = data[F'C_{next_customer}'][DEMAND]
                remaining_after_current = vehicle_load - current_demand
                
                if remaining_after_current >= next_demand:

                    sub_route.append(current_customer)
                    vehicle_load -= current_demand
                    i += 1
                else:

                    sub_route.append(current_customer)
                    route.append(sub_route)
                    sub_route = []
                    vehicle_load = vehicle_capacity
                    i += 1
            else:

                sub_route.append(current_customer)
                route.append(sub_route)
                break
        else:

            if sub_route:
                route.append(sub_route)
                sub_route = []
            vehicle_load = vehicle_capacity

    

    if sub_route and sub_route not in route:
        route.append(sub_route)
        
    return route


def calculate_fitness(individual, data):
    transport_cost = 8.0  
    vehicle_setup_cost = 50.0 

    route = create_route_from_ind(individual, data)
    total_cost = 999999
    fitness = 0
    max_vehicles_count = data[MAX_VEHICLE_NUMBER]

    # checking if we have enough vehicles
    if len(route) <= max_vehicles_count:
        total_cost = 0
        for sub_route in route:
            sub_route_distance = 0
            previous_cust_id = 0
            for cust_id in sub_route:
                # Calculate section distance
                distance = data[DISTANCE_MATRIX][previous_cust_id][cust_id]
                # Update sub-route distance
                sub_route_distance += distance

                # Update last customer ID
                previous_cust_id = cust_id

            # Calculate transport cost
            distance_depot = data[DISTANCE_MATRIX][previous_cust_id][0]
            sub_route_distance += distance_depot
            sub_route_transport_cost = vehicle_setup_cost + transport_cost * sub_route_distance
            # Obtain sub-route cost
            sub_route_cost = sub_route_transport_cost
            # Update total cost
            total_cost += sub_route_cost

    # Handle the case where total_cost is zero
    if total_cost == 0:
        fitness = 0  # or some other appropriate value
    else:
        fitness = 100000.0 / total_cost  # Ensure fitness is inversely related to cost

    return fitness, total_cost


# The initialization consist in generating a random position and a random speed for a particle.
# The next function creates a particle and initializes its attributes,
# except for the attribute best, which will be set only after evaluation
def generate_particle(size, s_min, s_max):
    """Generate a particle with speed limits"""
    # Create initial position
    position = random.sample(range(1, size + 1), size)
    part = creator.Particle(position)
    
    # Initialize speed
    part.speed = [random.uniform(s_min, s_max) for _ in range(size)]
    part.smin = s_min
    part.smax = s_max
    
    # Initialize best position
    part.best = creator.Particle(position[:])  # Create a copy of current position
    
    return part


def remove_duplicates(vals):
    duplic = [item for item, count in collections.Counter(vals).items() if count > 1]
    uniq_part = []
    offset = 0.001
    count = [1] * len(duplic)
    for val in vals:
        if val in duplic:
            ind = duplic.index(val)
            val += offset * count[ind]
            count[ind] += 1
        uniq_part.append(val)

    return uniq_part


# Change floats to integers and deal with duplicates
def validate_particle(particle):
    unique_part = remove_duplicates(particle)
    sorted_asc = sorted(unique_part, key=float)
    validated_part = []

    if len(sorted_asc) > len(set(sorted_asc)):
        print("problem")

    for val in unique_part:
        index = sorted_asc.index(val)
        validated_part.append((index + 1))

    return validated_part



def update_particle(part, best, phi1, phi2):
    """Update particle position and speed"""
    # Initialize best if not already set
    if part.best is None:
        part.best = creator.Particle(part[:])
        part.best.fitness = part.fitness
    
    u1 = (random.uniform(0, phi1) for _ in range(len(part)))
    u2 = (random.uniform(0, phi2) for _ in range(len(part)))
    
    v_u1 = map(operator.mul, u1, map(operator.sub, part.best, part))
    v_u2 = map(operator.mul, u2, map(operator.sub, best, part))
    
    part.speed = list(map(operator.add, part.speed, map(operator.add, v_u1, v_u2)))
    
    # Apply speed limits
    for i, speed in enumerate(part.speed):
        if abs(speed) < part.smin:
            part.speed[i] = math.copysign(part.smin, speed)
        elif abs(speed) > part.smax:
            part.speed[i] = math.copysign(part.smax, speed)
    
    # Update position
    position = list(map(operator.add, part, part.speed))
    part[:] = validate_particle(position)

class TabuList:
    def __init__(self, max_size=50):
        self.max_size = max_size
        self.list = collections.deque(maxlen=max_size)
        self.frequency = {}  # Çözüm frekansını takip et
        self.aspiration_criteria = float('-inf')  # En iyi çözümün fitness değeri
        
    def add(self, solution, fitness=None):
        """Add solution to tabu list with its fitness"""
        solution_tuple = tuple(solution)
        self.list.append(solution_tuple)
        self.frequency[solution_tuple] = self.frequency.get(solution_tuple, 0) + 1
        
        # Aspiration kriterini güncelle
        if fitness and fitness > self.aspiration_criteria:
            self.aspiration_criteria = fitness
        
    def contains(self, solution, fitness=None):
        """Check if solution is in tabu list with aspiration criteria"""
        solution_tuple = tuple(solution)
        
        # Aspiration kriteri: Eğer çözüm şimdiye kadarki en iyiden daha iyiyse, 
        # tabu listesinde olsa bile kabul et
        if fitness and fitness > self.aspiration_criteria:
            return False
            
        # Frekansa dayalı dinamik threshold
        threshold = 0.95 - (0.05 * self.frequency.get(solution_tuple, 0))
        threshold = max(0.7, threshold)  # Alt limit
        
        return any(self._similar_solutions(solution, tabu_sol, threshold) 
                  for tabu_sol in self.list)
    
    def clear(self):
        """Clear the tabu list"""
        self.list.clear()
        self.frequency.clear()
    
    def _similar_solutions(self, sol1, sol2, threshold):
        """Check if solutions are similar"""
        if isinstance(sol2, tuple):
            sol2 = list(sol2)
        return sum(a == b for a, b in zip(sol1, sol2)) / len(sol1) > threshold

def generate_neighbors(solution, method="swap", num_neighbors=5):
    """Generate diverse neighbors using multiple methods"""
    neighbors = []
    size = len(solution)
    
    for _ in range(num_neighbors):
        # Yeni bir birey oluştur
        neighbor = creator.Individual(solution[:])
            
        # Farklı komşuluk yapıları
        if method == "swap":
            # İki noktayı değiştir
            i, j = random.sample(range(size), 2)
            neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
        elif method == "insert":
            # Bir noktayı farklı bir konuma taşı
            i, j = random.sample(range(size), 2)
            value = neighbor[i]
            neighbor.pop(i)
            neighbor.insert(j, value)
        elif method == "reverse":
            # Alt diziyi tersine çevir
            i, j = sorted(random.sample(range(size), 2))
            neighbor[i:j+1] = reversed(neighbor[i:j+1])
        elif method == "scramble":
            # Alt diziyi karıştır
            i, j = sorted(random.sample(range(size), 2))
            sublist = neighbor[i:j+1]
            random.shuffle(sublist)
            neighbor[i:j+1] = sublist
            
        neighbors.append(neighbor)
            
    return neighbors
