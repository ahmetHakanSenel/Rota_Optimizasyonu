import requests
import numpy as np
from typing import List, Tuple
import os
import pickle
import time

class ElevationHandler:
    def __init__(self):
        self.api_url = "https://api.open-elevation.com/api/v1/lookup"
        self.elevation_cache = {}
        self._initialize_cache()
    
    def _initialize_cache(self):
        """Initialize elevation cache from disk"""
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, 'elevation_cache.pkl')
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    self.elevation_cache = pickle.load(f)
                print("Loaded elevation cache")
            except Exception as e:
                print(f"Error loading elevation cache: {e}")
                self.elevation_cache = {}
    
    def _save_cache(self):
        """Save elevation cache to disk"""
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
        cache_file = os.path.join(cache_dir, 'elevation_cache.pkl')
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(self.elevation_cache, f)
            print("Saved elevation cache")
        except Exception as e:
            print(f"Error saving elevation cache: {e}")
    
    def get_elevation(self, lat: float, lon: float) -> float:
        """Belirli bir koordinat için yükseklik bilgisini al"""
        cache_key = (round(lat, 6), round(lon, 6)) 
        if cache_key in self.elevation_cache:
            return self.elevation_cache[cache_key]
        
        try:
            params = {
                "locations": [{"latitude": lat, "longitude": lon}]
            }
            response = requests.post(self.api_url, json=params)
            data = response.json()
            
            if "results" in data and len(data["results"]) > 0:
                elevation = float(data["results"][0]["elevation"])
                self.elevation_cache[cache_key] = elevation
                self._save_cache()
                return elevation
            
            return 0
        except Exception as e:
            print(f"Error getting elevation data: {str(e)}")
            return 0
    
    def get_path_elevation_profile(self, coordinates: List[Tuple[float, float]]) -> dict:
        """Yol güzergahı için yükseklik profilini hesapla"""
        # Çok kısa rotalar için basitleştir
        if len(coordinates) <= 2:
            # Başlangıç ve bitiş noktalarının yüksekliklerini al
            elevations = []
            for lat, lon in coordinates:
                elevation = self.get_elevation(lat, lon)
                elevations.append(elevation)
            
            # Basit profil oluştur
            if len(elevations) == 2:
                diff = elevations[1] - elevations[0]
                total_ascent = max(0, diff)
                total_descent = max(0, -diff)
            else:
                total_ascent = total_descent = 0
                
            return {
                "elevations": elevations,
                "total_ascent": total_ascent,
                "total_descent": total_descent,
                "elevation_difficulty": total_ascent + total_descent,
                "avg_elevation": sum(elevations) / len(elevations) if elevations else 0,
                "max_elevation": max(elevations) if elevations else 0,
                "min_elevation": min(elevations) if elevations else 0
            }
        
        # Önbellek anahtarı oluştur
        cache_key = tuple((round(lat, 6), round(lon, 6)) for lat, lon in coordinates)
        
        # Önbellekte profil varsa kullan
        if hasattr(self, 'profile_cache') and cache_key in self.profile_cache:
            return self.profile_cache[cache_key]
            
        # Profil önbelleği yoksa oluştur
        if not hasattr(self, 'profile_cache'):
            self.profile_cache = {}
        
        # Çok fazla nokta varsa örnekleme yap
        if len(coordinates) > 10:
            # Başlangıç, bitiş ve aradaki noktaları örnekle
            indices = np.linspace(0, len(coordinates) - 1, 10, dtype=int)
            sampled_coordinates = [coordinates[i] for i in indices]
        else:
            sampled_coordinates = coordinates
        
        elevations = []
        total_ascent = 0
        total_descent = 0
        
        # Yükseklik verilerini al
        for lat, lon in sampled_coordinates:
            elevation = self.get_elevation(lat, lon)
            elevations.append(elevation)
        
        # Yükseklik değişimlerini hesapla
        for i in range(len(elevations) - 1):
            diff = elevations[i+1] - elevations[i]
            if diff > 0:
                total_ascent += diff
            else:
                total_descent += abs(diff)
        
        # İstatistikleri hesapla
        avg_elevation = sum(elevations) / len(elevations)
        max_elevation = max(elevations)
        min_elevation = min(elevations)
        
        # Yükseklik zorluğunu hesapla
        elevation_difficulty = 0
        if total_ascent > 0 or total_descent > 0:
            # Yükseklik değişimlerinin toplam mesafeye oranı
            elevation_difficulty = (total_ascent + total_descent) / len(elevations)
        
        # Sonucu oluştur ve önbelleğe al
        result = {
            "elevations": elevations,
            "total_ascent": total_ascent,
            "total_descent": total_descent,
            "elevation_difficulty": elevation_difficulty,
            "avg_elevation": avg_elevation,
            "max_elevation": max_elevation,
            "min_elevation": min_elevation
        }
        
        # Önbelleğe ekle
        self.profile_cache[cache_key] = result
        
        return result