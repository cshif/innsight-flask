"""Accommodation service for finding and processing accommodations."""

from typing import List, Optional
import pandas as pd

from ..overpass_client import fetch_overpass


class AccommodationService:
    """Service for finding and processing accommodations."""
    
    def build_overpass_query(self, lat: float, lon: float) -> str:
        """Build Overpass API query for accommodations."""
        return f"""
            [out:json][timeout:25];

            // 1. 找 100 公尺內水族館
            nwr(around:100,{lat},{lon})["tourism"="aquarium"]->.aquarium;

            // 2. 直接查 admin_level=7 area（可根據需要調整 admin_level）
            is_in({lat},{lon})->.areas;
            area.areas[boundary="administrative"][admin_level=7]->.mainArea;

            // 3. 取這個 area 對應的 relation
            rel(pivot.mainArea)->.mainRel;

            // 4. 找主行政區的邊界 ways
            way(r.mainRel)->.borderWays;

            // 5. 找和主行政區接壤的其他 admin_level=7 行政區（即鄰居）
            rel(bw.borderWays)[boundary="administrative"][admin_level=7]->.neighborRels;

            // 6. relation 轉 area id
            rel.neighborRels->.tmpRels;
            (.tmpRels; map_to_area;)->.neighborAreas;

            // 7. 查所有鄰近 area 內的旅宿
            nwr(area.neighborAreas)[tourism~"hotel|guest_house|hostel|motel|apartment|camp_site|caravan_site"];
            out center;
            """
    
    def fetch_accommodations(self, lat: float, lon: float) -> pd.DataFrame:
        """Fetch accommodations from Overpass API."""
        query = self.build_overpass_query(lat, lon)
        elements = fetch_overpass(query)
        return self.process_accommodation_elements(elements)
    
    def process_accommodation_elements(self, elements: List[dict]) -> pd.DataFrame:
        """Process accommodation elements into DataFrame."""
        rows = []
        for el in elements:
            lat_el = el.get("lat") or el.get("center", {}).get("lat")
            lon_el = el.get("lon") or el.get("center", {}).get("lon")

            tags = el.get("tags", {})
            row = {
                "osmid": el["id"],
                "osmtype": el["type"],
                "lat": lat_el,
                "lon": lon_el,
                "tourism": tags.get("tourism"),
                "name": tags.get("name", "Unknown"),
                "rating": self._extract_rating(tags),
                "tags": self._extract_amenity_tags(tags),
            }
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def _extract_rating(self, tags: dict) -> Optional[float]:
        """Extract rating from OSM tags."""
        # Try different rating fields
        rating_fields = ['rating', 'stars', 'quality']
        for field in rating_fields:
            if field in tags:
                try:
                    return float(tags[field])
                except (ValueError, TypeError):
                    continue
        return None
    
    def _extract_amenity_tags(self, tags: dict) -> dict:
        """Extract amenity tags for scoring."""
        # Define extraction rules for each amenity
        extraction_rules = {
            'parking': {
                'direct_keys': ['parking'],
                'conditional_keys': [('parking:fee', 'no', 'yes')],  # If parking:fee=no, then parking=yes
                'indicator_keys': []
            },
            'wheelchair': {
                'direct_keys': ['wheelchair'],
                'conditional_keys': [],
                'indicator_keys': []
            },
            'kids': {
                'direct_keys': [],
                'conditional_keys': [],
                'indicator_keys': ['family_friendly', 'kids', 'children']
            },
            'pet': {
                'direct_keys': [],
                'conditional_keys': [],
                'indicator_keys': ['pets', 'pets_allowed', 'dogs']
            }
        }
        
        amenity_tags = {}
        
        for amenity, rules in extraction_rules.items():
            value = None
            
            # Check direct keys first
            for key in rules['direct_keys']:
                if key in tags:
                    value = tags[key]
                    break
            
            # Check conditional keys
            if value is None:
                for key, condition_value, result_value in rules['conditional_keys']:
                    if key in tags and tags[key] == condition_value:
                        value = result_value
                        break
            
            # Check indicator keys (return 'yes' if any match)
            if value is None:
                for key in rules['indicator_keys']:
                    if key in tags and tags[key] in ['yes', 'true']:
                        value = 'yes'
                        break
            
            amenity_tags[amenity] = value
            
        return amenity_tags