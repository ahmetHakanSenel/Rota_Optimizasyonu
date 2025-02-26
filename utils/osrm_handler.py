import requests
from typing import List, Tuple, Dict, Any
import numpy as np
import os
import pickle
import time

class OSRMHandler:
    """Handler for OSRM (Open Source Routing Machine) API requests."""
    
    def __init__(self, base_url: str = "http://router.project-osrm.org"):
        """
        Initialize OSRM handler.
        
        Args:
            base_url: Base URL for OSRM service
        """
        self.base_url = base_url.rstrip('/')
        self.distance_matrix = {}
        self.timeout = 60
        self.max_retries = 3
        self._initialize_cache()
    
    def _initialize_cache(self):
        """Initialize the distance matrix cache from disk if it exists."""
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, 'osrm_distance_matrix.pkl')
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    self.distance_matrix = pickle.load(f)
                print("Loaded distance matrix from cache")
            except Exception as e:
                print(f"Error loading cache: {e}")
                self.distance_matrix = {}
    
    def save_cache(self):
        """Save the current distance matrix cache to disk."""
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
        cache_file = os.path.join(cache_dir, 'osrm_distance_matrix.pkl')
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(self.distance_matrix, f)
            print("Saved distance matrix to cache")
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def get_distance(self, origin: Tuple[float, float], dest: Tuple[float, float]) -> float:
        """Get the distance between two points from cache."""
        key = (tuple(origin), tuple(dest))
        reverse_key = (tuple(dest), tuple(origin))
        
        if key in self.distance_matrix:
            return self.distance_matrix[key]
        if reverse_key in self.distance_matrix:
            return self.distance_matrix[reverse_key]
        
        print(f"Warning: Distance not found in cache for {key}")
        return float('inf')
        
    def get_distance_matrix(self, locations: List[Tuple[float, float]]) -> Dict[str, Any]:
        """
        Get distance matrix for a list of locations using OSRM.
        
        Args:
            locations: List of (latitude, longitude) tuples
            
        Returns:
            Dictionary containing:
            - success: Boolean indicating if request was successful
            - distances: 2D array of distances between locations (in kilometers)
            - error: Error message if request failed
        """
        try:
            # Format coordinates for OSRM
            coordinates = ';'.join(f"{lon},{lat}" for lat, lon in locations)
            
            # Make request to OSRM table service
            url = f"{self.base_url}/table/v1/driving/{coordinates}"
            params = {
                'annotations': 'distance'
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'distances' not in data:
                return {
                    'success': False,
                    'error': 'No distance data in response'
                }
                
            # Convert distances from meters to kilometers
            distances = np.array(data['distances']) / 1000
            
            return {
                'success': True,
                'distances': distances.tolist()
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'OSRM request failed: {str(e)}'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def precompute_distances(self, instance: Dict) -> bool:
        """
        Precompute all distances between points in an instance.
        
        Args:
            instance: Dictionary containing instance data with depot and customer coordinates
            
        Returns:
            Boolean indicating if precomputation was successful
        """
        print("\nPrecomputing all distances using OSRM table service...")
        
        all_points = []
        depot = (instance['depart']['coordinates']['x'], 
                instance['depart']['coordinates']['y'])
        all_points.append(depot)
        
        i = 1
        while True:
            customer_key = f'C_{i}'
            if customer_key not in instance:
                break
            customer = instance[customer_key]
            point = (customer['coordinates']['x'],
                    customer['coordinates']['y'])
            all_points.append(point)
            i += 1
        
        print(f"Found {len(all_points)-1} customer points")
        coordinates = [f"{p[1]},{p[0]}" for p in all_points]
        
        for attempt in range(self.max_retries):
            try:
                url = f"{self.base_url}/table/v1/driving/{';'.join(coordinates)}"
                params = {
                    "annotations": "distance",
                    "sources": "all",
                    "destinations": "all"
                }
                
                print("Requesting distance matrix from OSRM...")
                response = requests.get(url, params=params, timeout=self.timeout)
                data = response.json()
                
                if response.status_code == 200 and "distances" in data:
                    print("Successfully received distance matrix")
                    
                    distances = data["distances"]
                    for i, origin in enumerate(all_points):
                        for j, dest in enumerate(all_points):
                            if i != j:
                                distance = distances[i][j] / 1000
                                self.distance_matrix[(tuple(origin), tuple(dest))] = distance
                    
                    print(f"Cached {len(self.distance_matrix)} distances")
                    self.save_cache()
                    return True
                
                print(f"Invalid response from OSRM (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            
            except requests.Timeout:
                print(f"Timeout error (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            except requests.RequestException as e:
                print(f"Network error (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            except Exception as e:
                print(f"Error calculating distance matrix: {str(e)}")
                break
        
        print("Failed to compute distance matrix")
        return False 