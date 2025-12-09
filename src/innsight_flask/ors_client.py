import os
import time
from functools import wraps
from json import JSONDecodeError
from typing import Dict, List, Tuple

import requests
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, HTTPError, Timeout
from shapely.geometry import Polygon

from .exceptions import IsochroneError, NetworkError, APIError
from .logging_config import get_logger

# Get module logger
logger = get_logger(__name__)

load_dotenv()

# Configuration constants
DEFAULT_CACHE_MAXSIZE = 128
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 1
DEFAULT_BACKOFF_MULTIPLIER = 2
DEFAULT_REQUEST_TIMEOUT = (5, 30)


def retry_on_network_error(max_attempts=DEFAULT_MAX_ATTEMPTS, delay=DEFAULT_RETRY_DELAY, backoff=DEFAULT_BACKOFF_MULTIPLIER):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (Timeout, ConnectionError, HTTPError, JSONDecodeError) as e:
                    # Handle specific error transformations
                    if isinstance(e, HTTPError):
                        status = e.response.status_code
                        if not (status == 429 or 500 <= status < 600):
                            raise
                        # Transform retryable HTTP errors for final attempt
                        if attempt == max_attempts - 1:
                            new_error = HTTPError(f"Upstream temporary failure ({status}): {e.response.text}")
                            new_error.response = e.response
                            raise new_error
                    elif isinstance(e, JSONDecodeError):
                        # Transform JSONDecodeError for final attempt
                        if attempt == max_attempts - 1:
                            raise ConnectionError(f"Invalid response format: {str(e)}")
                    
                    if attempt == max_attempts - 1:
                        logger.error(
                            "API call failed after retries",
                            service="openrouteservice",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            total_attempts=max_attempts
                        )
                        raise

                    logger.warning(
                        "API call failed, retrying",
                        service="openrouteservice",
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        retry_delay_seconds=current_delay
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None

        return wrapper
    return decorator


# Custom cache storage
_fallback_cache: Dict[Tuple, Tuple[List[Polygon], float]] = {}  # (key, (result, timestamp))


def fallback_cache(maxsize=DEFAULT_CACHE_MAXSIZE, ttl_hours=DEFAULT_CACHE_TTL_HOURS):
    """
    Cache decorator that falls back to expired cache on failure.
    - maxsize: Maximum number of cache items
    - ttl_hours: Cache validity period (hours)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key
            key = (func.__name__, args, tuple(sorted(kwargs.items())))
            current_time = time.time()
            
            # Check for valid cache
            if key in _fallback_cache:
                cached_result, cached_time = _fallback_cache[key]
                age_hours = (current_time - cached_time) / 3600
                
                # Return cached result if still valid
                if age_hours <= ttl_hours:
                    return cached_result
            
            try:
                # Try to execute function
                result = func(*args, **kwargs)
                # Update cache on success
                _fallback_cache[key] = (result, current_time)
                
                # Clean up expired cache items
                if len(_fallback_cache) > maxsize:
                    expired_keys = [
                        k for k, (_, timestamp) in _fallback_cache.items()
                        if current_time - timestamp > ttl_hours * 3600
                    ]
                    for expired_key in expired_keys:
                        _fallback_cache.pop(expired_key, None)
                    
                    # If still too many, remove oldest items
                    if len(_fallback_cache) > maxsize:
                        oldest_key = min(
                            _fallback_cache.keys(),
                            key=lambda k: _fallback_cache[k][1]
                        )
                        _fallback_cache.pop(oldest_key, None)
                
                return result
                
            except (Timeout, ConnectionError, HTTPError, JSONDecodeError) as e:
                # Only fallback to cache for network-related errors
                if key in _fallback_cache:
                    cached_result, cached_time = _fallback_cache[key]
                    age_hours = (current_time - cached_time) / 3600
                    logger.warning(
                        "API call failed, using stale cache",
                        service="openrouteservice",
                        cache_age_hours=round(age_hours, 1),
                        error_type=type(e).__name__,
                        error_message=str(e)
                    )
                    return cached_result
                else:
                    # Raise custom error when no cache available
                    raise IsochroneError(f"Isochrone request failed and no cache available: {str(e)}") from e
        
        # Add cache management methods
        wrapper.cache_clear = lambda: _fallback_cache.clear()
        wrapper.cache_info = lambda: {
            'size': len(_fallback_cache),
            'items': {k: (len(v[0]), v[1]) for k, v in _fallback_cache.items()}
        }
        
        return wrapper
    return decorator


@fallback_cache(maxsize=DEFAULT_CACHE_MAXSIZE, ttl_hours=DEFAULT_CACHE_TTL_HOURS)
@retry_on_network_error(max_attempts=DEFAULT_MAX_ATTEMPTS, delay=DEFAULT_RETRY_DELAY, backoff=DEFAULT_BACKOFF_MULTIPLIER)
def _fetch_isochrones_from_api(
        profile: str,
        locations: Tuple[Tuple[float, float], ...],
        max_range: Tuple[int, ...]
) -> List[Polygon]:
    # Start measuring latency
    start_time = time.perf_counter()

    resp = requests.post(
        url=f"{os.getenv('ORS_URL')}/isochrones/{profile}",
        json={"locations": locations, "range": max_range},
        headers={
            "Accept": "application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8",
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": os.getenv("ORS_API_KEY"),
        },
        timeout=DEFAULT_REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()

    # Check for API errors
    if isinstance(data, dict) and "error" in data:
        code = data["error"].get("code")
        msg = data["error"].get("message", repr(data["error"]))
        raise APIError(f"ORS API error {code}: {msg}", status_code=code)

    # Convert GeoJSON features to Shapely polygons
    polygons = []
    if "features" in data:
        for feature in data["features"]:
            if feature.get("geometry", {}).get("type") == "Polygon":
                coords = feature["geometry"]["coordinates"][0]  # Exterior ring coordinates
                polygons.append(Polygon(coords))

    # Log successful API call with latency
    latency_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "External API call succeeded",
        service="openrouteservice",
        endpoint="/v2/isochrones",
        profile=profile,
        latency_ms=round(latency_ms, 2),
        success=True
    )

    return polygons


def get_isochrones_by_minutes(
    coord: Tuple[float, float], 
    intervals: List[int],
    profile: str = 'driving-car'
) -> List[List[Polygon]]:
    """
    Get isochrones by minute intervals.
    
    Args:
        coord: Coordinates (lon, lat)
        intervals: List of time intervals (minutes)
        profile: Transportation mode, defaults to 'driving-car'
    
    Returns:
        List of isochrones, each element corresponds to a time interval
    """
    # Convert minutes to seconds and make single API call
    max_range = tuple(minutes * 60 for minutes in intervals)
    all_polygons = _fetch_isochrones_from_api(profile, (coord,), max_range)
    
    # ORS API returns one polygon per time range
    # Convert single polygon list to list of lists format for consistency
    return [[polygon] for polygon in all_polygons]

# Expose cache methods
get_isochrones_by_minutes.cache_info = _fetch_isochrones_from_api.cache_info
get_isochrones_by_minutes.cache_clear = _fetch_isochrones_from_api.cache_clear

