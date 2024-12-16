import os
import io
import osmnx as ox
import folium
from geopy.distance import geodesic
import networkx as nx
from geopy.geocoders import Nominatim
import math
import requests
import time
import traceback

# Use a single BASE_DIR definition that works cross-platform
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

X_COORD = 'x'
Y_COORD = 'y'
COORDINATES = 'coordinates'
INSTANCE_NAME = 'instance_name'
MAX_VEHICLE_NUMBER = 'max_vehicle_number'
VEHICLE_CAPACITY = 'vehicle_capacity'
DEPART = 'depart'
DEMAND = 'demand'
READY_TIME = 'ready_time'
DUE_TIME = 'due_time'
SERVICE_TIME = 'service_time'
DISTANCE_MATRIX = 'distance_matrix'


def calculate_distance(cust_1, cust_2):
    x_diff = cust_1[COORDINATES][X_COORD] - cust_2[COORDINATES][X_COORD]
    y_diff = cust_1[COORDINATES][Y_COORD] - cust_2[COORDINATES][Y_COORD]
    return (x_diff**2 + y_diff**2)**0.5


def convert_to_real_coordinates(x, y, base_lat=41.0082, base_lon=28.9784):
    """Convert relative coordinates to real lat/lon coordinates
    Base coordinates are set to Istanbul by default"""
    # This is a simple conversion - you might want to adjust the scale factors
    lat = base_lat + (y / 1000)  # Adjust scaling factor as needed
    lon = base_lon + (x / 1000)  # Adjust scaling factor as needed
    return lat, lon


class MapHandler:
    def __init__(self, location):
        self.location = location

    def calculate_route_distance(self, coord1, coord2):
        # Mesafe hesaplama mantığı (örnek olarak sabit bir değer dönüyorum)
        return ((coord1[0] - coord2[0])**2 + (coord1[1] - coord2[1])**2)**0.5

def load_problem_instance(problem_name='istanbul-test'):
    cust_num = 0
    # Use os.path.join for cross-platform compatibility
    text_file = os.path.join(BASE_DIR, 'data', problem_name + '.txt')
    
    # Create data directory if it doesn't exist
    data_dir = os.path.join(BASE_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    # Print some debug info
    print(f"Looking for file: {text_file}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Data directory exists: {os.path.exists(data_dir)}")
    
    parsed_data = {
        DEPART: None,
        DISTANCE_MATRIX: None,
        MAX_VEHICLE_NUMBER: None,
        VEHICLE_CAPACITY: None,
        INSTANCE_NAME: None
    }

    line = ""
    values = []

    try:
        with io.open(text_file, 'rt', encoding='utf-8', newline='') as fo:
            for line_count, line in enumerate(fo, start=1):
                line = line.strip()
                if not line or line.startswith(('CUSTOMER', 'VEHICLE', 'CUST NO.', '#')):
                    continue

                values = line.split()
                if len(values) == 0:
                    continue

                if line_count == 1:
                    parsed_data[INSTANCE_NAME] = line
                elif len(values) == 2 and values[1].isdigit():
                    parsed_data[MAX_VEHICLE_NUMBER] = int(values[0])
                    parsed_data[VEHICLE_CAPACITY] = float(values[1])
                elif len(values) >= 7:
                    cust_id = int(values[0])
                    comment = ' '.join(values[7:]) if len(values) > 7 else ''
                    if cust_id == 0:
                        # Depot
                        parsed_data[DEPART] = {
                            COORDINATES: {
                                X_COORD: float(values[1]),
                                Y_COORD: float(values[2]),
                            },
                            DEMAND: float(values[3]),
                            READY_TIME: float(values[4]),
                            DUE_TIME: float(values[5]),
                            SERVICE_TIME: float(values[6]),
                            'comment': comment.strip('# ')
                        }
                    else:
                        # Customers
                        parsed_data[f'C_{cust_id}'] = {
                            COORDINATES: {
                                X_COORD: float(values[1]),
                                Y_COORD: float(values[2]),
                            },
                            DEMAND: float(values[3]),
                            READY_TIME: float(values[4]),
                            DUE_TIME: float(values[5]),
                            SERVICE_TIME: float(values[6]),
                            'comment': comment.strip('# ')
                        }
                        cust_num += 1

        # Create distance matrix
        customers = [DEPART] + [f'C_{x}' for x in range(1, cust_num + 1)]
        distance_matrix = []

        print("Creating distance matrix...")
        map_handler = MapHandler("Istanbul, Turkey")

        for c1 in customers:
            row = []
            coord1 = (
                parsed_data[c1][COORDINATES][X_COORD],
                parsed_data[c1][COORDINATES][Y_COORD]
            )

            for c2 in customers:
                if c1 == c2:
                    row.append(0)
                    continue

                coord2 = (
                    parsed_data[c2][COORDINATES][X_COORD],
                    parsed_data[c2][COORDINATES][Y_COORD]
                )
                try:
                    distance = map_handler.calculate_route_distance(coord1, coord2)
                except Exception as e:
                    print(f"Error calculating distance between {coord1} and {coord2}: {e}")
                    distance = float('inf')

                row.append(distance)

            distance_matrix.append(row)
            print(f"Calculated distances for {c1}")

        parsed_data[DISTANCE_MATRIX] = distance_matrix
        return parsed_data

    except UnicodeDecodeError as e:
        print(f"UnicodeDecodeError: {e}")
        print(f"Error in file: {text_file} at line {line_count}")
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"Error loading problem instance: {e}")
        print(f"Current line: {line}")
        print(f"Values: {values}")
        traceback.print_exc()
        return None



def calculate_real_distance(coord1, coord2):
    """Calculate real-world driving distance between two points using OSM"""
    try:
        # Get the road network if not already initialized
        map_handler = MapHandler("Istanbul, Turkey")
        
        # Calculate actual driving distance using road network
        distance = map_handler.calculate_route_distance(coord1, coord2)
        return int(distance * 1000)  # Convert to meters for OR-Tools
    except Exception as e:
        print(f"Error calculating real distance: {e}")
        # Fallback to geodesic distance only if routing fails
        return int(geodesic(coord1, coord2).meters)


class MapHandler:
    _instance = None
    _initialized = False
    
    def __new__(cls, city="Istanbul, Turkey"):
        if cls._instance is None:
            print(f"Initializing road network for {city}...")
            cls._instance = super(MapHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, city="Istanbul, Turkey"):
        if not self._initialized:
            self.G = ox.graph_from_place(city, network_type='drive')
            self.nodes, self.edges = ox.graph_to_gdfs(self.G)
            self.distance_cache = {}
            self._node_cache = {}
            self._initialized = True
            print("Road network initialized successfully!")

    def calculate_route_distance(self, coord1, coord2):
        """Calculate actual driving distance using OSM"""
        cache_key = (coord1, coord2)
        if cache_key in self.distance_cache:
            return self.distance_cache[cache_key]
            
        try:
            # Get nearest nodes
            orig_node = self._get_nearest_node(coord1)
            dest_node = self._get_nearest_node(coord2)
            
            # Calculate shortest path distance
            try:
                route = nx.shortest_path(self.G, orig_node, dest_node, weight='length')
                distance = sum(
                    self.G[route[i]][route[i+1]][0]['length'] 
                    for i in range(len(route)-1)
                ) / 1000  # Convert to kilometers
                
                self.distance_cache[cache_key] = distance
                return distance
                
            except nx.NetworkXNoPath:
                print(f"No route found between {coord1} and {coord2}")
                distance = geodesic(coord1, coord2).kilometers
                return distance
                
        except Exception as e:
            print(f"Error calculating route distance: {e}")
            return geodesic(coord1, coord2).kilometers

    def _get_nearest_node(self, coord):
        """Get nearest node with caching"""
        cache_key = str(coord)
        if cache_key in self._node_cache:
            return self._node_cache[cache_key]
            
        node = ox.distance.nearest_nodes(self.G, coord[1], coord[0])
        self._node_cache[cache_key] = node
        return node

    def _calculate_bearing(self, p1, p2):
        """Calculate bearing between two points"""
        lat1, lon1 = p1
        lat2, lon2 = p2
        
        d_lon = lon2 - lon1
        y = math.sin(d_lon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
        bearing = math.atan2(y, x)
        
        return math.degrees(bearing)

    def visualize_route(self, route, instance_data, output_file='route_map.html'):
        """Visualize the route on an interactive map"""
        first_coord = (
            instance_data[DEPART][COORDINATES][X_COORD],
            instance_data[DEPART][COORDINATES][Y_COORD]
        )
        m = folium.Map(location=first_coord, zoom_start=12)
        
        # Add depot marker
        folium.Marker(
            first_coord,
            popup='Depot',
            icon=folium.Icon(color='black', icon='info-sign')
        ).add_to(m)
        
        colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred']
        
        for route_idx, sub_route in enumerate(route):
            color = colors[route_idx % len(colors)]
            prev_coord = first_coord
            
            # Add route segments with arrows
            for i, customer_id in enumerate(sub_route):
                customer = instance_data[f'C_{customer_id}']
                curr_coord = (
                    customer[COORDINATES][X_COORD],
                    customer[COORDINATES][Y_COORD]
                )
                
                # Get actual route path using OSM
                try:
                    orig_node = self._get_nearest_node(prev_coord)
                    dest_node = self._get_nearest_node(curr_coord)
                    path = nx.shortest_path(self.G, orig_node, dest_node, weight='length')
                    
                    # Get path coordinates
                    path_coords = []
                    for node in path:
                        path_coords.append([
                            self.nodes.loc[node, 'y'],
                            self.nodes.loc[node, 'x']
                        ])
                    
                    # Draw actual route path
                    folium.PolyLine(
                        path_coords,
                        weight=2,
                        color=color,
                        opacity=0.8,
                        popup=f'Segment {i+1}'
                    ).add_to(m)
                except:
                    # Fallback to direct line if route finding fails
                    points = [prev_coord, curr_coord]
                    folium.PolyLine(
                        points,
                        weight=2,
                        color=color,
                        opacity=0.8,
                        popup=f'Segment {i+1}'
                    ).add_to(m)
                
                # Add arrow at midpoint
                mid_lat = (prev_coord[0] + curr_coord[0]) / 2
                mid_lon = (prev_coord[1] + curr_coord[1]) / 2
                
                # Calculate bearing for arrow rotation
                bearing = self._calculate_bearing(prev_coord, curr_coord)
                
                # Add arrow marker
                folium.RegularPolygonMarker(
                    location=(mid_lat, mid_lon),
                    number_of_sides=3,
                    radius=6,
                    rotation=bearing - 90,
                    color=color,
                    fill=True,
                    popup=f'→ Customer {customer_id}'
                ).add_to(m)
                
                # Add customer marker
                folium.Marker(
                    curr_coord,
                    popup=f'Customer {customer_id}',
                    icon=folium.Icon(color=color)
                ).add_to(m)
                
                prev_coord = curr_coord
            
            # Add return to depot with actual route
            try:
                orig_node = self._get_nearest_node(prev_coord)
                dest_node = self._get_nearest_node(first_coord)
                path = nx.shortest_path(self.G, orig_node, dest_node, weight='length')
                
                path_coords = []
                for node in path:
                    path_coords.append([
                        self.nodes.loc[node, 'y'],
                        self.nodes.loc[node, 'x']
                    ])
                
                folium.PolyLine(
                    path_coords,
                    weight=2,
                    color=color,
                    opacity=0.8,
                    popup='Return to depot'
                ).add_to(m)
            except:
                # Fallback to direct line
                points = [prev_coord, first_coord]
                folium.PolyLine(
                    points,
                    weight=2,
                    color=color,
                    opacity=0.8,
                    popup='Return to depot'
                ).add_to(m)
            
            # Add arrow for return
            mid_lat = (prev_coord[0] + first_coord[0]) / 2
            mid_lon = (prev_coord[1] + first_coord[1]) / 2
            bearing = self._calculate_bearing(prev_coord, first_coord)
            
            folium.RegularPolygonMarker(
                location=(mid_lat, mid_lon),
                number_of_sides=3,
                radius=6,
                rotation=bearing - 90,
                color=color,
                fill=True,
                popup='→ Depot'
            ).add_to(m)
        
        m.save(output_file)

def show_initial_locations(instance_data):
    """Show all customer locations on map before starting calculations"""
    # Create map centered on depot
    depot_coord = (
        instance_data[DEPART][COORDINATES][X_COORD],
        instance_data[DEPART][COORDINATES][Y_COORD]
    )
    m = folium.Map(location=depot_coord, zoom_start=13)
    
    # Add depot marker
    folium.Marker(
        depot_coord,
        popup='Depot (Mecidiyeköy)',
        icon=folium.Icon(color='black', icon='info-sign')
    ).add_to(m)
    
    # Add customer markers
    for i in range(1, 26):
        customer = instance_data[f'C_{i}']
        coord = (
            customer[COORDINATES][X_COORD],
            customer[COORDINATES][Y_COORD]
        )
        # Get location name from comment in data file
        location_name = "Customer"  # Default name
        if 'comment' in customer:
            location_name = customer['comment']
            
        folium.Marker(
            coord,
            popup=f'Customer {i}<br>Location: {location_name}<br>Demand: {customer[DEMAND]}',
            icon=folium.Icon(color='red')
        ).add_to(m)
    
    # Save and show map
    m.save('initial_locations.html')
    return 'initial_locations.html'


def create_navigation_link(route, instance_data):
    """Create Google Maps navigation link for the route"""
    base_url = "https://www.google.com/maps/dir/"
    
    # Start with depot
    depot_coord = (
        instance_data[DEPART][COORDINATES][X_COORD],
        instance_data[DEPART][COORDINATES][Y_COORD]
    )
    waypoints = [f"{depot_coord[0]},{depot_coord[1]}"]
    
    # Add all stops in the route
    for sub_route in route:
        for customer_id in sub_route:
            customer = instance_data[f'C_{customer_id}']
            coord = (
                customer[COORDINATES][X_COORD],
                customer[COORDINATES][Y_COORD]
            )
            waypoints.append(f"{coord[0]},{coord[1]}")
    
    # Add depot as final destination
    waypoints.append(f"{depot_coord[0]},{depot_coord[1]}")
    
    # Create navigation URL
    nav_url = base_url + '/'.join(waypoints)
    return nav_url
