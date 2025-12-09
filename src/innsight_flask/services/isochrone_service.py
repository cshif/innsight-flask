"""Isochrone service for calculating travel time polygons."""

from typing import List, Tuple, Optional

from ..config import AppConfig
from ..ors_client import get_isochrones_by_minutes


class IsochroneService:
    """Service for isochrone calculation and caching."""
    
    def __init__(self, config: AppConfig):
        self.config = config
    
    def get_isochrones_with_fallback(self, coord: Tuple[float, float], intervals: List[int]) -> Optional[List]:
        """Get isochrones with fallback handling."""
        try:
            return get_isochrones_by_minutes(coord, intervals)
        except Exception as e:
            # Check if we can use cached data
            if "cache" in str(e).lower():
                import sys
                print("使用快取資料", file=sys.stderr)
                try:
                    return get_isochrones_by_minutes(coord, intervals)
                except:
                    return None
            return None