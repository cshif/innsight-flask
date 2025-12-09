"""Tier service for assigning accommodation tiers based on location."""

from typing import List, Optional
import pandas as pd
import geopandas as gpd

from ..tier import assign_tier


class TierService:
    """Service for tier assignment."""
    
    def assign_tiers(self, df: pd.DataFrame, isochrones_list: Optional[List]) -> gpd.GeoDataFrame:
        """Assign tiers to accommodations based on isochrones."""
        if isochrones_list and all(isochrones_list):
            return assign_tier(df, isochrones_list)
        else:
            # If no isochrones, assign tier 0 to all
            gdf = df.copy()
            gdf['tier'] = 0
            return gdf