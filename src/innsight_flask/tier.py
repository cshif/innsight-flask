import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from typing import List, Union
from shapely.geometry import Polygon

from .exceptions import TierError

# Default buffer distance for handling boundary points
DEFAULT_BUFFER = 1e-5


def assign_tier(
        df: pd.DataFrame,
        polygons: List[Union[Polygon, List[Polygon]]],
        buffer: float = DEFAULT_BUFFER
) -> gpd.GeoDataFrame:
    """
    Assign tiers to points based on polygon containment.
    
    Args:
        df: DataFrame containing 'lat' and 'lon' columns
        polygons:
            List of polygons, sorted by tier (smaller polygons get higher tier)
            Can be Polygon or List[Polygon] (automatically takes first one)
            Example: [isochrones_15, isochrones_30, isochrones_60] where isochrones_15 gets tier=3
        buffer: Distance to buffer polygons for handling boundary points (default DEFAULT_BUFFER = 1e-5)
    
    Returns:
        GeoDataFrame containing original data plus 'tier' column and Point geometry
    """
    # Copy input DataFrame
    gdf = df.copy()
    
    # Validate required columns exist
    if 'lat' not in df.columns or 'lon' not in df.columns:
        raise TierError("DataFrame must contain 'lat' and 'lon' columns")
    
    # Check for missing latitude or longitude values
    missing_lat = df['lat'].isna().any()
    missing_lon = df['lon'].isna().any()
    
    if missing_lat or missing_lon:
        missing_info = []
        if missing_lat:
            missing_info.append("latitude")
        if missing_lon:
            missing_info.append("longitude")
        raise TierError(f"Missing {' or '.join(missing_info)}")
    
    # Process polygons input, convert to uniform Polygon objects
    processed_polygons = []
    for i, polygon_input in enumerate(polygons):
        try:
            if isinstance(polygon_input, (list, tuple)):
                if len(polygon_input) == 0:
                    raise TierError(f"Tier {i+1} polygon format error: list cannot be empty")
                # If it's a list (like List[Polygon]), take the first element
                polygon = polygon_input[0]
                # Validate that the first element in the list is a Polygon
                if not isinstance(polygon, Polygon):
                    raise TierError(f"Tier {i+1} polygon format error: list elements must be Polygon objects, got {type(polygon).__name__}")
            else:
                # Should be a Polygon
                polygon = polygon_input
                # Validate if it's a Polygon
                if not isinstance(polygon, Polygon):
                    raise TierError(f"Tier {i+1} polygon format error: must be Polygon object, got {type(polygon).__name__}")
            
            # If buffer distance is specified, buffer the polygon
            if buffer > 0:
                polygon = polygon.buffer(buffer)
            
            processed_polygons.append(polygon)
            
        except TierError:
            # Re-raise TierError
            raise
        except (AttributeError, TypeError) as e:
            # Handle other possible type errors
            raise TierError(f"Tier {i+1} polygon format error: {str(e)}")
    
    # Create GeoDataFrame
    geometry = [Point(lon, lat) for lat, lon in zip(df['lat'], df['lon'])]
    gdf = gpd.GeoDataFrame(gdf, geometry=geometry, crs='EPSG:4326')
    
    # Initialize tier column to 0
    gdf['tier'] = 0
    
    # If empty DataFrame, return directly
    if len(df) == 0:
        return gdf
    
    # Performance optimization: for duplicate coordinates, calculate only once
    # Create coordinate to index mapping
    coord_key = df['lat'].round(8).astype(str) + ',' + df['lon'].round(8).astype(str)
    unique_coords = coord_key.drop_duplicates()
    
    # Create unique coordinate tier mapping
    coord_to_tier = {}
    
    # Calculate tier only for unique coordinates
    for coord in unique_coords:
        lat_str, lon_str = coord.split(',')
        lat, lon = float(lat_str), float(lon_str)
        point = Point(lon, lat)
        
        highest_tier = 0
        # Check each polygon, from highest tier to lowest tier
        for i, polygon in enumerate(processed_polygons):
            tier_value = len(processed_polygons) - i
            
            # Use Polygon directly for containment check
            if point.within(polygon):
                highest_tier = max(highest_tier, tier_value)
        
        coord_to_tier[coord] = highest_tier
    
    # Use precomputed tier values
    gdf['tier'] = coord_key.map(coord_to_tier)
    
    return gdf