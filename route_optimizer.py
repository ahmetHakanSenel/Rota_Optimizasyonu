from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

class VRPOptimizer:
    def __init__(self, distance_matrix, num_vehicles, depot=0, demands=None, vehicle_capacity=None):
        self.distance_matrix = distance_matrix
        self.num_vehicles = num_vehicles
        self.depot = depot
        self.demands = demands if demands else [0] * len(distance_matrix)
        self.vehicle_capacity = vehicle_capacity
        self.num_threads = multiprocessing.cpu_count()  # Use all available CPU cores
        
    def create_data_model(self):
        data = {
            'distance_matrix': self.distance_matrix,
            'num_vehicles': self.num_vehicles,
            'depot': self.depot,
            'demands': [int(d) for d in self.demands],
            'vehicle_capacities': [int(self.vehicle_capacity)] * self.num_vehicles if self.vehicle_capacity else None
        }
        return data

    def get_routes(self, solution, routing, manager):
        """Get vehicle routes from solution"""
        routes = []
        for vehicle_id in range(self.num_vehicles):
            index = routing.Start(vehicle_id)
            route = []
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                route.append(node_index)
                index = solution.Value(routing.NextVar(index))
            route.append(manager.IndexToNode(index))
            if len(route) > 2:  # Only include routes that visit at least one customer
                routes.append(route[1:-1])  # Remove depot from start and end
        return routes

    def solve(self):
        data = self.create_data_model()
        manager = pywrapcp.RoutingIndexManager(
            len(data['distance_matrix']),
            data['num_vehicles'],
            data['depot'])
        
        routing = pywrapcp.RoutingModel(manager)
        
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(data['distance_matrix'][from_node][to_node] * 1000)
        
        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        
        # Add Distance constraint
        dimension_name = 'Distance'
        routing.AddDimension(
            transit_callback_index,
            0,
            30000,  # 30 km max distance
            True,
            dimension_name)
        
        # Add Capacity constraint
        if data['vehicle_capacities']:
            demand_callback_index = routing.RegisterUnaryTransitCallback(
                lambda index: data['demands'][manager.IndexToNode(index)])
            routing.AddDimensionWithVehicleCapacity(
                demand_callback_index,
                0,
                data['vehicle_capacities'],
                True,
                'Capacity')
        
        # Optimize parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_parameters.time_limit.FromSeconds(30)
        
        # Solve
        solution = routing.SolveWithParameters(search_parameters)
        
        if solution:
            routes = self.get_routes(solution, routing, manager)
            total_distance = 0
            for vehicle_id in range(data['num_vehicles']):
                index = routing.Start(vehicle_id)
                route_distance = 0
                while not routing.IsEnd(index):
                    previous_index = index
                    index = solution.Value(routing.NextVar(index))
                    route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
                total_distance += route_distance
            return routes, total_distance
        return None, None