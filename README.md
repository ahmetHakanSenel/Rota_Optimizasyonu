# Vehicle Routing Problem with Real Road Distances

## Overview
This application solves the Vehicle Routing Problem (VRP) using real road distances from OpenStreetMap (OSRM) and provides navigation through GraphHopper. The solution is based on an enhanced Tabu Search algorithm with adaptive neighborhood structures.

### Components
- **Data Processing** (`process_data.py`): 
  - Loads problem instances
  - Calculates real road distances using OSRM
  - Handles distance matrix caching
  - Creates GraphHopper navigation links

- **Core Functions** (`core_funs.py`):
  - Adaptive neighborhood generation
  - Parallel solution evaluation
  - Distance calculations
  - Solution diversification

- **Algorithm** (`alg_creator.py`):
  - Enhanced Tabu Search implementation
  - Adaptive parameter tuning
  - Multiple neighborhood structures
  - Solution tracking and improvement

### Features
- Real road distance calculations using OSRM
- GraphHopper navigation integration
- Adaptive Tabu Search with:
  - Multiple neighborhood structures
  - Dynamic parameter adjustment
  - Solution diversification
  - Parallel evaluation
- Efficient caching system
- Early stopping mechanism

### Quick Start
1. Install requirements:
```bash
pip install requests polyline
```

2. Run with default parameters:
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
25 500
0 41.0082 28.9784 0 0 1000 0 # Depot (Mecidiyeköy)
1 41.035 28.975 10 0 1000 10 # Şişli
...
```

### Algorithm Parameters
- `individual_size`: Number of delivery locations
- `pop_size`: Initial population size
- `n_gen`: Maximum iterations
- `tabu_size`: Initial tabu list size
- `stagnation_limit`: Diversification threshold

### Neighborhood Structures
The algorithm uses multiple neighborhood structures with adaptive weights:
- Swap: Multiple point exchanges
- Insert: Sequential point movements
- Reverse: Segment reversals
- Scramble: Segment shuffling
- Block Move: Block relocations
- Cross: Cross-exchange operations

Each structure's weight is dynamically adjusted based on its success in finding improvements.
