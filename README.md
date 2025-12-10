# InnSight Flask

A Flask-based accommodation recommendation API that helps users find the best places to stay near points of interest using geospatial analysis and travel time isochrones.

## Features

- **Natural Language Query** - Parse Chinese queries to extract POIs and filter preferences
- **Isochrone-based Ranking** - Tier accommodations by driving time from target POI
- **Smart Scoring** - Rank by configurable weights for tier, rating, and amenities
- **Amenity Filtering** - Filter by parking, wheelchair, kid-friendly, pet-friendly
- **Caching** - In-memory and ETag-based HTTP caching

## Tech Stack

- Flask 3.x, PostgreSQL/PostGIS, GeoPandas, Shapely
- OpenRouteService, Nominatim, Overpass API
- Pydantic, Gunicorn

## Installation

```bash
git clone <repository-url>
cd innsight-flask
poetry install
cp .env.sample .env
# Edit .env with your credentials
```

## Configuration

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `API_ENDPOINT` | Backend API endpoint |
| `ORS_URL` | OpenRouteService API URL |
| `ORS_API_KEY` | OpenRouteService API key |
| `OVERPASS_URL` | Overpass API endpoint |

## Running

```bash
poetry run flask --app innsight_flask run --debug
```

## License

MIT


> Made with ❤️ in 2025
