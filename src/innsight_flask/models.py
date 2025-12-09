"""Pydantic models for API request and response schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Union, Tuple


class WeightsModel(BaseModel):
    rating: Optional[float] = 1.0
    tier: Optional[float] = 1.0


class RecommendRequest(BaseModel):
    query: str = Field(..., description="Search query for accommodations")
    weights: Optional[WeightsModel] = None
    top_n: Optional[int] = Field(default=20, ge=1, le=20, description="Maximum number of results (1-20)")
    filters: Optional[List[str]] = None


class AccommodationModel(BaseModel):
    name: str
    score: float = Field(ge=0, le=100)
    tier: int = Field(ge=0, le=3)
    lat: Optional[float] = None
    lon: Optional[float] = None
    osmid: Optional[str] = None
    osmtype: Optional[str] = None
    tourism: Optional[str] = None
    rating: Optional[float] = None
    amenities: Optional[dict] = None


class StatsModel(BaseModel):
    tier_0: int = 0
    tier_1: int = 0
    tier_2: int = 0
    tier_3: int = 0


class MainPoiModel(BaseModel):
    name: str
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    display_name: Optional[str] = None
    type: Optional[str] = None
    address: Optional[dict] = None


class IntervalsModel(BaseModel):
    values: List[int]
    unit: str = "minutes"
    profile: str = "driving-car"


class PolygonGeometry(BaseModel):
    """GeoJSON Polygon 幾何體"""
    type: Literal["Polygon"] = "Polygon"
    coordinates: List[List[Tuple[float, float]]]  # [[(lon, lat), (lon, lat), ...]]


class MultiPolygonGeometry(BaseModel):
    """GeoJSON MultiPolygon 幾何體"""
    type: Literal["MultiPolygon"] = "MultiPolygon"
    coordinates: List[List[List[Tuple[float, float]]]]  # [[[[(lon, lat), (lon, lat), ...]], [...]]]


# Union 讓 API 支援兩種格式
IsochroneGeometry = Union[PolygonGeometry, MultiPolygonGeometry]


class RecommendResponse(BaseModel):
    stats: StatsModel
    top: List[AccommodationModel]
    main_poi: MainPoiModel
    isochrone_geometry: List[IsochroneGeometry] = Field(
        default_factory=list,
        description="Travel time isochrones in GeoJSON format"
    )
    intervals: IntervalsModel = Field(default_factory=lambda: IntervalsModel(values=[]))


class ErrorResponse(BaseModel):
    error: str
    message: str