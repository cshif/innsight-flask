"""Pipeline for integration with Recommender."""

from typing import Dict, List, Any, Optional
import copy
import geopandas as gpd
import hashlib
import json
import math
import time

from .logging_config import get_logger

# Get module logger
logger = get_logger(__name__)
from shapely.geometry import Polygon

from .config import AppConfig
from .services.accommodation_search_service import AccommodationSearchService
from .services.geocode_service import GeocodeService
from .services.isochrone_service import IsochroneService
from .recommender import Recommender as RecommenderCore
from .exceptions import NetworkError, APIError, GeocodeError, IsochroneError, ServiceUnavailableError
from .parser import parse_query, extract_location_from_query


class Recommender:
    """Pipeline wrapper for Recommender."""
    
    def __init__(self):
        """Initialize the recommendation pipeline."""
        config = AppConfig.from_env()
        search_service = AccommodationSearchService(config)
        self.geocode_service = GeocodeService(config)
        self.isochrone_service = IsochroneService(config)
        self.config = config
        self.recommender = RecommenderCore(search_service)

        # Recommendation result cache
        self._cache: Dict[str, tuple] = {}  # {cache_key: (result, timestamp)}
        self._cache_ttl: int = config.recommender_cache_ttl_seconds
        self._cache_max_size: int = config.recommender_cache_maxsize
        self._cleanup_interval: int = config.recommender_cache_cleanup_interval
        self._last_cleanup_time: float = 0

        # Cache statistics (for monitoring)
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._parsing_failures: int = 0

        # Log cache configuration on initialization
        logger.info(
            "Cache initialized - Max size: %d, TTL: %d seconds (%.1f minutes), "
            "Cleanup interval: %d seconds",
            self._cache_max_size,
            self._cache_ttl,
            self._cache_ttl / 60,
            self._cleanup_interval
        )
    
    def run(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the recommendation pipeline.

        Args:
            query_data: Dictionary containing query parameters
                - query: str - Search query
                - filters: List[str] - Optional filters
                - top_n: int - Optional maximum results

        Returns:
            Dictionary with recommendation results
        """
        # Start measuring total pipeline duration
        pipeline_start = time.perf_counter()
        stages = {}

        query = query_data.get("query", "")
        filters = query_data.get("filters")
        top_n = query_data.get("top_n", 20)
        weights = query_data.get("weights")
        
        if not query:
            # Return empty results for empty query instead of error
            return {
                "stats": {"tier_0": 0, "tier_1": 0, "tier_2": 0, "tier_3": 0},
                "top": [],
                "main_poi": self._build_main_poi_data("未知景點", None, None),
                "isochrone_geometry": [],
                "intervals": {"values": [], "unit": "minutes", "profile": "driving-car"}
            }
        
        # Parse query to extract main POI information (只解析一次)
        parsing_start = time.perf_counter()
        try:
            parsed_query = parse_query(query)
            location = extract_location_from_query(parsed_query, query)
            poi = parsed_query.get('poi', '')
            parsed_filters = parsed_query.get('filters', [])
            stages['parsing_ms'] = round((time.perf_counter() - parsing_start) * 1000, 2)
            
            # Determine the main POI name and search term
            if poi:
                main_poi_name = poi
                search_term = poi
            elif location:
                # If no POI found, try to extract attraction from the original query
                main_poi_name = self._extract_attraction_from_query(query) or location
                search_term = main_poi_name
            else:
                main_poi_name = "未知景點"
                search_term = ""
            
            # Get detailed geocoding information for the main POI
            poi_details = None
            main_poi_lat = None
            main_poi_lon = None

            if search_term:
                geocoding_start = time.perf_counter()
                poi_details = self.geocode_service.geocode_location_detailed(search_term)
                stages['geocoding_ms'] = round((time.perf_counter() - geocoding_start) * 1000, 2)
                if poi_details:
                    main_poi_lat = poi_details.get("lat")
                    main_poi_lon = poi_details.get("lon")
                
        except Exception as e:
            # Log parsing failure with details
            logger.warning(
                "Query parsing failed",
                query=query,
                error_type=type(e).__name__,
                error_message=str(e)
            )

            # If parsing fails, use defaults
            main_poi_name = "未知景點"
            location = None
            poi_details = None
            main_poi_lat = None
            main_poi_lon = None
            parsed_filters = []
            poi = ""  # Ensure poi is defined for cache key check
            self._parsing_failures += 1

        # Merge parsed filters with API-provided filters
        merged_filters = self._merge_filters(parsed_filters, filters)

        # Check cache only if parsing succeeded (has poi or location)
        cache_key = None
        if poi or location:
            cache_key = self._build_cache_key(
                poi=poi,
                place=location,
                filters=merged_filters,
                weights=weights,
                profile='driving-car'
            )
            cached_result = self._get_from_cache(cache_key, top_n)
            if cached_result is not None:
                # Log performance metrics for cache hit
                total_duration_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
                logger.info(
                    "Recommendation pipeline completed",
                    total_duration_ms=total_duration_ms,
                    cache_hit=True,
                    results_count=len(cached_result.get('top', [])),
                    stages=stages
                )
                return cached_result
        
        # Search for accommodations
        try:
            # If we have main POI coordinates, use them for accommodation search
            search_start = time.perf_counter()
            if main_poi_lat is not None and main_poi_lon is not None:
                gdf = self.recommender.recommend_by_coordinates(
                    main_poi_lat, main_poi_lon, merged_filters, top_n, weights
                )
            else:
                # Fallback to original query-based search
                gdf = self.recommender.recommend(query, merged_filters, top_n, weights)
            stages['search_ms'] = round((time.perf_counter() - search_start) * 1000, 2)
            
            # Convert to serializable format
            top_results = self._serialize_gdf(gdf)
            
            # Calculate tier statistics
            stats = self._calculate_tier_stats(gdf)
            
            # Get isochrone geometry data
            isochrone_geometry = []
            intervals_data = {"values": [], "unit": "minutes", "profile": "driving-car"}

            if main_poi_lat is not None and main_poi_lon is not None:
                coord = (float(main_poi_lon), float(main_poi_lat))
                intervals = self.config.default_isochrone_intervals
                isochrone_start = time.perf_counter()
                isochrones_list = self.isochrone_service.get_isochrones_with_fallback(coord, intervals)
                stages['isochrone_ms'] = round((time.perf_counter() - isochrone_start) * 1000, 2)

                if isochrones_list:
                    isochrone_geometry = self._convert_isochrones_to_geojson(isochrones_list)
                    intervals_data = {
                        "values": intervals,
                        "unit": "minutes",
                        "profile": "driving-car"
                    }
            
            # Build result
            result = {
                "stats": stats,
                "top": top_results,
                "main_poi": self._build_main_poi_data(main_poi_name, location, poi_details),
                "isochrone_geometry": isochrone_geometry,
                "intervals": intervals_data
            }

            # Save to cache if parsing succeeded
            if cache_key is not None:
                self._save_to_cache(cache_key, result)

            # Log performance metrics
            total_duration_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
            logger.info(
                "Recommendation pipeline completed",
                total_duration_ms=total_duration_ms,
                cache_hit=False,
                results_count=len(top_results),
                stages=stages
            )

            return result
            
        except (NetworkError, APIError, GeocodeError, IsochroneError) as e:
            # External dependency failures should be re-raised as ServiceUnavailableError
            raise ServiceUnavailableError(f"External service unavailable: {str(e)}")
        except Exception as e:
            # Other exceptions return empty results
            return {
                "stats": {"tier_0": 0, "tier_1": 0, "tier_2": 0, "tier_3": 0},
                "top": [],
                "main_poi": self._build_main_poi_data(main_poi_name, location, poi_details),
                "isochrone_geometry": [],
                "intervals": {"values": [], "unit": "minutes", "profile": "driving-car"}
            }
    
    def _merge_filters(self, parsed_filters: List[str], api_filters: Optional[List[str]]) -> List[str]:
        """Merge parsed filters with API-provided filters and remove duplicates.
        
        Args:
            parsed_filters: Filters extracted from query text
            api_filters: Filters provided via API parameters
            
        Returns:
            List of unique filter strings
        """
        # Handle None values
        if parsed_filters is None:
            parsed_filters = []
        if api_filters is None:
            api_filters = []
            
        # Combine both lists and remove duplicates while preserving order
        combined = parsed_filters + api_filters
        unique_filters = []
        seen = set()
        
        for filter_item in combined:
            if filter_item not in seen:
                unique_filters.append(filter_item)
                seen.add(filter_item)
                
        return unique_filters
    
    def _serialize_gdf(self, gdf: gpd.GeoDataFrame) -> List[Dict[str, Any]]:
        """Convert GeoDataFrame to JSON-serializable format."""
        if len(gdf) == 0:
            return []
        
        def safe_float(value):
            """Safely convert value to float, handling NaN cases."""
            if value is None:
                return None
            try:
                f_val = float(value)
                return None if math.isnan(f_val) or math.isinf(f_val) else f_val
            except (ValueError, TypeError):
                return None
        
        def safe_int(value):
            """Safely convert value to int, handling NaN cases."""
            if value is None:
                return 0
            try:
                f_val = float(value)
                if math.isnan(f_val) or math.isinf(f_val):
                    return 0
                return int(f_val)
            except (ValueError, TypeError):
                return 0

        return [
            {
                "name": row.get("name", "Unknown"),
                "score": safe_float(row.get("score")) or 0.0,
                "tier": safe_int(row.get("tier")),
                "lat": safe_float(row.get("lat")),
                "lon": safe_float(row.get("lon")),
                "osmid": str(row.get("osmid")) if row.get("osmid") is not None else None,
                "osmtype": row.get("osmtype"),
                "tourism": row.get("tourism"),
                "rating": safe_float(row.get("rating")),
                "amenities": row.get("tags", {})
            }
            for _, row in gdf.iterrows()
        ]
    
    def _calculate_tier_stats(self, gdf: gpd.GeoDataFrame) -> Dict[str, int]:
        """Calculate tier statistics from GeoDataFrame."""
        if len(gdf) == 0:
            return {"tier_0": 0, "tier_1": 0, "tier_2": 0, "tier_3": 0}
        
        # Count occurrences of each tier
        tier_counts = gdf['tier'].value_counts().to_dict()
        
        return {
            "tier_0": tier_counts.get(0, 0),
            "tier_1": tier_counts.get(1, 0), 
            "tier_2": tier_counts.get(2, 0),
            "tier_3": tier_counts.get(3, 0)
        }
    
    def _build_main_poi_data(self, main_poi_name: str, location: Optional[str], poi_details: Optional[dict]) -> dict:
        """Build main POI data structure."""
        def safe_float(value):
            """Safely convert value to float, handling NaN cases."""
            if value is None:
                return None
            try:
                f_val = float(value)
                return None if math.isnan(f_val) or math.isinf(f_val) else f_val
            except (ValueError, TypeError):
                return None
        
        if poi_details:
            return {
                "name": main_poi_name,
                "location": location,
                "lat": safe_float(poi_details.get("lat")),
                "lon": safe_float(poi_details.get("lon")),
                "display_name": poi_details.get("display_name"),
                "type": poi_details.get("type"),
                "address": poi_details.get("address")
            }
        else:
            return {
                "name": main_poi_name,
                "location": location,
                "lat": None,
                "lon": None,
                "display_name": None,
                "type": None,
                "address": None
            }
    
    def _extract_attraction_from_query(self, query: str) -> Optional[str]:
        """Extract attraction name from query text."""
        # Common attraction keywords
        attraction_keywords = [
            "水族館", "博物館", "美術館", "動物園", "遊樂園", "主題樂園",
            "城堡", "神社", "寺廟", "公園", "廣場", "塔", "橋", "海灘",
            "溫泉", "滑雪場", "商場", "百貨", "市場", "街道", "老街"
        ]
        
        # Look for attraction keywords in the query
        for keyword in attraction_keywords:
            if keyword in query:
                # Find the position of the keyword
                keyword_pos = query.find(keyword)
                
                # Look for potential attraction name before the keyword
                # e.g., "沖繩水族館" from "我想去沖繩水族館"
                start_pos = max(0, keyword_pos - 10)  # Look up to 10 chars before
                potential_name = ""
                
                # Extract characters before the keyword that could be part of the attraction name
                for i in range(keyword_pos - 1, start_pos - 1, -1):
                    char = query[i]
                    # Include Chinese characters, letters, and numbers, but exclude common verbs/particles
                    if (char.isalnum() or '\u4e00' <= char <= '\u9fff') and char not in ['去', '到', '想', '的', '在', '和', '與']:
                        potential_name = char + potential_name
                    else:
                        break
                
                # Combine the potential prefix with the keyword
                full_name = potential_name + keyword
                
                # Return the full name if it looks reasonable, otherwise just the keyword
                if len(full_name) > len(keyword) and len(full_name) <= 20:
                    return full_name
                else:
                    return keyword
        
        return None
    
    def _convert_isochrones_to_geojson(self, isochrones_list: List[List[Polygon]]) -> List[Dict[str, Any]]:
        """Convert isochrone polygons to GeoJSON format."""
        geojson_geometries = []
        
        for isochrone_group in isochrones_list:
            if not isochrone_group:
                continue
                
            if len(isochrone_group) == 1:
                # Single polygon
                polygon = isochrone_group[0]
                if isinstance(polygon, Polygon):
                    coords = [list(polygon.exterior.coords)]
                    geojson_geometries.append({
                        "type": "Polygon",
                        "coordinates": coords
                    })
            else:
                # Multiple polygons - use MultiPolygon
                all_coords = []
                for polygon in isochrone_group:
                    if isinstance(polygon, Polygon):
                        all_coords.append([list(polygon.exterior.coords)])
                
                if all_coords:
                    geojson_geometries.append({
                        "type": "MultiPolygon",
                        "coordinates": all_coords
                    })
        
        return geojson_geometries

    def _build_cache_key(self, poi: str, place: Optional[str], filters: List[str],
                         weights: Optional[dict], profile: str) -> str:
        """Build cache key from parsed query parameters.

        Args:
            poi: Main point of interest
            place: Location/region
            filters: List of filter categories
            weights: Score weights
            profile: Transportation profile

        Returns:
            MD5 hash of the parameters
        """
        cache_data = {
            'poi': poi or "",
            'place': place or "",
            'filters': sorted(filters) if filters else [],
            'weights': weights,
            'profile': profile
        }
        return hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()

    def _get_from_cache(self, cache_key: str, top_n: int) -> Optional[Dict[str, Any]]:
        """Retrieve result from cache if valid.

        Args:
            cache_key: Cache key to lookup
            top_n: Number of results to return

        Returns:
            Cached result with top_n slicing, or None if cache miss/expired
        """
        if cache_key not in self._cache:
            self._cache_misses += 1
            logger.info(
                "Cache miss",
                cache_key=cache_key[:8],
                reason="not_found"
            )
            # Trigger periodic cleanup before returning
            self._cleanup_cache()
            return None

        result, timestamp = self._cache[cache_key]

        # Check if cache is expired
        if time.time() - timestamp > self._cache_ttl:
            del self._cache[cache_key]
            self._cache_misses += 1
            logger.info(
                "Cache miss",
                cache_key=cache_key[:8],
                reason="expired"
            )
            # Trigger periodic cleanup before returning
            self._cleanup_cache()
            return None

        # Cache hit - increment counter and return result
        self._cache_hits += 1

        # Log cache hit at debug level with structured fields
        logger.debug(
            "Cache hit",
            cache_key=cache_key[:8],
            cache_size=len(self._cache),
            cache_max_size=self._cache_max_size,
            top_n=top_n
        )

        # Trigger periodic cleanup after successful cache hit
        self._cleanup_cache()

        # Return cached result with top_n slicing (deep copy to avoid mutation)
        result_copy = {
            'stats': result['stats'],
            'top': result['top'][:top_n],  # Slice to requested top_n
            'main_poi': result['main_poi'],
            'isochrone_geometry': result['isochrone_geometry'],
            'intervals': result['intervals']
        }
        return result_copy

    def _save_to_cache(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Save result to cache with current timestamp.

        Args:
            cache_key: Cache key
            result: Result dictionary to cache (will be deep copied)
        """
        # Deep copy to prevent external mutations from affecting cache
        result_copy = copy.deepcopy(result)
        self._cache[cache_key] = (result_copy, time.time())

    def _cleanup_cache(self) -> None:
        """Clean up expired and excess cache entries (throttled).

        Cleanup is throttled to run at most once per cleanup_interval (default 60s).
        This prevents excessive cleanup operations on high-frequency requests.

        Cleanup strategy:
        1. Remove all expired entries (older than TTL)
        2. If cache still exceeds max size, remove oldest entries (LRU)
        """
        current_time = time.time()

        # Throttle: skip if cleaned up recently
        if current_time - self._last_cleanup_time < self._cleanup_interval:
            return

        self._last_cleanup_time = current_time

        # Step 1: Remove all expired entries
        expired_keys = [
            key for key, (_, timestamp) in self._cache.items()
            if current_time - timestamp > self._cache_ttl
        ]

        for key in expired_keys:
            del self._cache[key]

        # Step 2: If still over max size, remove oldest entries (LRU)
        num_evicted = 0
        if len(self._cache) > self._cache_max_size:
            # Sort by timestamp (oldest first)
            sorted_items = sorted(
                self._cache.items(),
                key=lambda item: item[1][1]  # item[1][1] is timestamp
            )

            # Calculate how many to remove
            num_to_remove = len(self._cache) - self._cache_max_size

            # Remove oldest entries
            for key, _ in sorted_items[:num_to_remove]:
                del self._cache[key]

            num_evicted = num_to_remove

        # Log cache statistics after cleanup
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0

        logger.info(
            "Cache stats - Size: %d/%d, Hits: %d, Misses: %d, Hit rate: %.1f%%, "
            "Parsing failures: %d, Expired: %d, Evicted: %d",
            len(self._cache),
            self._cache_max_size,
            self._cache_hits,
            self._cache_misses,
            hit_rate,
            self._parsing_failures,
            len(expired_keys),
            num_evicted
        )