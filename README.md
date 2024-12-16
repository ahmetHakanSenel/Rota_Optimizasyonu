## Vehicle Routing Problem with Real Road Distances

### Overview
This application solves the Vehicle Routing Problem (VRP) using real road distances from OpenStreetMap. It is divided into several modules:

- **Data preprocessing** (`process_data.py`): 
  - Loads problem instances from data files
  - Handles coordinate conversions
  - Calculates real road distances using OpenStreetMap
  - Visualizes routes on interactive maps

- **Core functions** (`core_funs.py`):
  - Route generation and validation
  - Distance calculations
  - Tabu list management
  - Neighborhood generation

- **Algorithm implementations** (`alg_creator.py`):
  - Particle Swarm Optimization (PSO)
  - Tabu Search
  - Route visualization and optimization

- **Route optimization** (`route_optimizer.py`):
  - OR-Tools based VRP solver
  - Handles capacity constraints
  - Optimizes for real road distances

### Features
- Real road distance calculations using OpenStreetMap
- Interactive route visualization on maps
- Multiple optimization algorithms (PSO, Tabu Search)
- Support for capacity constraints
- Navigation link generation for Google Maps
- Early stopping for efficiency

### Quick Start
1. Install requirements:
```bash
pip install -r requirements.txt
```

2. Run the test script:
```bash
python test_vrp.py
```

Or run with specific parameters:
```bash
python run.py istanbultest TABU
```

### Data Format
Problem instances should be in the following format:
```
Instance Name
NumVehicles Capacity
NodeID Latitude Longitude Demand ReadyTime DueTime ServiceTime # Location
...
```

Example:
```
Istanbul VRP Test Instance
4 100
0 41.0082 28.9784 0 0 1000 0 # Depot (Mecidiyeköy)
1 41.035 28.975 10 0 1000 30 # Şişli
...
```

### Parameters
Key parameters that can be modified:
- `num_customers`: Number of delivery locations
- `pop_size`: Population size for metaheuristics
- `n_gen`: Number of generations/iterations
- `tabu_size`: Size of tabu list
- `stagnation_limit`: Early stopping threshold
- `vehicle_capacity`: Maximum vehicle capacity

### Visualization
The application generates two types of visualizations:
1. Initial locations map (`initial_locations.html`)
2. Optimized routes map (`route_map.html`)

Both maps are interactive and show:
- Depot location
- Customer locations with demands
- Route segments with arrows
- Distance information

### References
- OpenStreetMap for road network data
- OR-Tools for basic VRP solving
- Folium for map visualization
