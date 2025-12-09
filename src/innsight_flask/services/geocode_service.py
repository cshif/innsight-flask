"""Geocoding service for converting locations to coordinates."""

from typing import Tuple, Dict, Any, Optional

from ..config import AppConfig
from ..nominatim_client import NominatimClient
from ..exceptions import GeocodeError


class GeocodeService:
    """Service for geocoding locations."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self._client = None
    
    @property
    def client(self) -> NominatimClient:
        """Lazy initialization of NominatimClient."""
        if self._client is None:
            self._client = NominatimClient(
                api_endpoint=self.config.api_endpoint,
                user_agent=self.config.nominatim_user_agent,
                timeout=self.config.nominatim_timeout
            )
        return self._client
    
    def geocode_location(self, search_term: str) -> Tuple[float, float]:
        """Geocode search term and return coordinates."""
        geocode_results = self.client.geocode(search_term)
        
        if not geocode_results:
            raise GeocodeError("找不到地點")
        
        return geocode_results[0]
    
    def geocode_location_detailed(self, search_term: str) -> Optional[Dict[str, Any]]:
        """Geocode search term and return detailed location information."""
        geocode_results = self.client.geocode_detailed(search_term)
        
        if not geocode_results:
            return None
        
        return geocode_results[0]