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
        
        # Eğer mesafe önbellekte yoksa, doğrudan OSRM'den almayı dene
        try:
            # Koordinatları formatlayın
            origin_str = f"{origin[1]},{origin[0]}"
            dest_str = f"{dest[1]},{dest[0]}"
            
            # OSRM route servisine istek yap
            url = f"{self.base_url}/route/v1/driving/{origin_str};{dest_str}"
            params = {
                'overview': 'false',
                'alternatives': 'false'
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if response.status_code == 200 and "routes" in data and len(data["routes"]) > 0:
                # Mesafeyi kilometre cinsinden al
                distance = data["routes"][0]["distance"] / 1000
                self.distance_matrix[key] = distance
                return distance
            
            print(f"Warning: Could not get distance from OSRM for {key}")
            return float('inf')
            
        except Exception as e:
            print(f"Error getting distance from OSRM: {e}")
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
            
            response = requests.get(url, params=params, timeout=self.timeout)
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
        
        # Büyük veri setleri için parçalara ayırma
        max_batch_size = 100  # OSRM'nin işleyebileceği maksimum nokta sayısı
        if len(all_points) > max_batch_size:
            print(f"Large dataset detected. Processing in batches of {max_batch_size} points.")
            return self._batch_precompute_distances(all_points, max_batch_size)
        
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
        
        print("Failed to compute distance matrix using table service. Falling back to route service...")
        return self._fallback_precompute_distances(all_points)
    
    def _batch_precompute_distances(self, all_points: List[Tuple[float, float]], batch_size: int) -> bool:
        """
        Precompute distances in batches for large datasets.
        
        Args:
            all_points: List of (latitude, longitude) tuples
            batch_size: Maximum number of points to process in a single batch
            
        Returns:
            Boolean indicating if precomputation was successful
        """
        success = True
        total_points = len(all_points)
        
        # Depo noktasını her batch'e dahil et
        depot = all_points[0]
        
        for i in range(0, total_points, batch_size - 1):
            batch_points = [depot]  # Her batch depo ile başlar
            if i > 0:  # İlk batch değilse
                batch_points.extend(all_points[i:min(i + batch_size - 1, total_points)])
            else:  # İlk batch ise
                batch_points.extend(all_points[1:min(batch_size, total_points)])
            
            print(f"Processing batch {i//batch_size + 1} with {len(batch_points)} points")
            
            coordinates = [f"{p[1]},{p[0]}" for p in batch_points]
            
            for attempt in range(self.max_retries):
                try:
                    url = f"{self.base_url}/table/v1/driving/{';'.join(coordinates)}"
                    params = {
                        "annotations": "distance",
                        "sources": "all",
                        "destinations": "all"
                    }
                    
                    response = requests.get(url, params=params, timeout=self.timeout)
                    data = response.json()
                    
                    if response.status_code == 200 and "distances" in data:
                        distances = data["distances"]
                        for i, origin in enumerate(batch_points):
                            for j, dest in enumerate(batch_points):
                                if i != j:
                                    distance = distances[i][j] / 1000
                                    self.distance_matrix[(tuple(origin), tuple(dest))] = distance
                        
                        break  # Başarılı olduğunda döngüden çık
                    
                    print(f"Invalid response from OSRM (attempt {attempt + 1}/{self.max_retries})")
                    if attempt < self.max_retries - 1:
                        time.sleep(2)
                
                except Exception as e:
                    print(f"Error in batch processing: {str(e)}")
                    if attempt < self.max_retries - 1:
                        time.sleep(2)
                    else:
                        success = False
        
        print(f"Cached {len(self.distance_matrix)} distances")
        self.save_cache()
        return success
    
    def _fallback_precompute_distances(self, all_points: List[Tuple[float, float]]) -> bool:
        """
        Fallback method to precompute distances using route service instead of table service.
        
        Args:
            all_points: List of (latitude, longitude) tuples
            
        Returns:
            Boolean indicating if precomputation was successful
        """
        print("Using route service to compute distances between all points...")
        success_count = 0
        total_pairs = len(all_points) * (len(all_points) - 1)
        
        for i, origin in enumerate(all_points):
            for j, dest in enumerate(all_points):
                if i != j:
                    key = (tuple(origin), tuple(dest))
                    if key in self.distance_matrix:
                        success_count += 1
                        continue
                    
                    try:
                        origin_str = f"{origin[1]},{origin[0]}"
                        dest_str = f"{dest[1]},{dest[0]}"
                        
                        url = f"{self.base_url}/route/v1/driving/{origin_str};{dest_str}"
                        params = {
                            'overview': 'false',
                            'alternatives': 'false'
                        }
                        
                        response = requests.get(url, params=params, timeout=10)
                        data = response.json()
                        
                        if response.status_code == 200 and "routes" in data and len(data["routes"]) > 0:
                            distance = data["routes"][0]["distance"] / 1000
                            self.distance_matrix[key] = distance
                            success_count += 1
                            
                            # Her 10 çiftte bir ilerleme raporu
                            if success_count % 10 == 0:
                                print(f"Progress: {success_count}/{total_pairs} pairs processed")
                        
                        # OSRM'yi aşırı yüklememek için kısa bir bekleme
                        time.sleep(0.2)
                        
                    except Exception as e:
                        print(f"Error getting distance for {key}: {str(e)}")
        
        print(f"Completed with {success_count}/{total_pairs} successful distance calculations")
        self.save_cache()
        return success_count > 0 