"""Recommender class that provides a unified interface for accommodation recommendations."""

from typing import List, Optional, Dict
import geopandas as gpd

from .services.accommodation_search_service import AccommodationSearchService
from .config import AppConfig


class Recommender:
    """Unified interface for accommodation recommendations."""
    
    def __init__(self, search_service: AccommodationSearchService):
        """Initialize recommender with search service dependency.
        
        Args:
            search_service: Service for searching accommodations
        """
        self.search_service = search_service
    
    def recommend(self, query: str, filters: Optional[List[str]] = None, top_n: int = None, weights: Optional[Dict[str, float]] = None) -> gpd.GeoDataFrame:
        """Get accommodation recommendations based on query and preferences.
        
        Args:
            query: Search query string (fallback method, prefer recommend_by_coordinates)
            filters: Optional list of filter conditions (e.g., ["parking", "wheelchair"])
            top_n: Maximum number of results to return
            weights: Optional custom weights for scoring (e.g., {"rating": 10, "tier": 1})
            
        Returns:
            GeoDataFrame containing recommended accommodations
        """
        # Use default top_n if not specified
        if top_n is None:
            top_n = self.search_service.config.default_top_n
        
        # Get accommodations using existing search service (fallback for compatibility)
        accommodations = self.search_service.search_accommodations(query, weights=weights)
        
        # Apply ranking with filters if accommodations found
        if len(accommodations) > 0:
            accommodations = self.search_service.rank_accommodations(
                accommodations, 
                filters=filters, 
                top_n=top_n
            )
        
        return accommodations
    
    def recommend_by_coordinates(self, lat: float, lon: float, filters: Optional[List[str]] = None, top_n: int = None, weights: Optional[Dict[str, float]] = None) -> gpd.GeoDataFrame:
        """Get accommodation recommendations based on specific coordinates.
        
        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            filters: Optional list of filter conditions (e.g., ["parking", "wheelchair"])
            top_n: Maximum number of results to return
            weights: Optional custom weights for scoring (e.g., {"rating": 10, "tier": 1})
            
        Returns:
            GeoDataFrame containing recommended accommodations
        """
        # Use default top_n if not specified
        if top_n is None:
            top_n = self.search_service.config.default_top_n
        
        # Get accommodations using coordinates directly
        accommodations = self.search_service.search_accommodations_by_coordinates(lat, lon, weights=weights)
        
        # Apply ranking with filters if accommodations found
        if len(accommodations) > 0:
            accommodations = self.search_service.rank_accommodations(
                accommodations, 
                filters=filters, 
                top_n=top_n
            )
        
        return accommodations