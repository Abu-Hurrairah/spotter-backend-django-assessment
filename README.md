# Spotter Backend Django Engineer Assessment

A Django 6.1 API that:

1. accepts a start and finish location in the USA,
2. gets a driving route using **OpenRouteService**,
3. finds route-adjacent truck stops from the supplied fuel-price CSV,
4. chooses cost-effective fuel stops for a vehicle with a **500-mile maximum range** and **10 MPG** fuel economy,
5. returns the selected stops, estimated total fuel cost, route GeoJSON, and a browser map.

## Why this design

The supplied CSV contains 8,151 fuel-price rows but **does not contain latitude/longitude**. Geocoding those records on every route request would be slow and would violate the assessment goal of minimizing external mapping calls.

This project therefore treats station geocoding as a **one-time data-ingestion step**:

- import the CSV locally,
- batch geocode it with the free U.S. Census Geocoder,
- optionally use a slow city-level fallback for unmatched highway-style addresses,
- store coordinates in SQLite,
- perform route/station matching locally thereafter.

For a new, uncached route request, the application makes at most:

- 2 OpenRouteService geocoding calls (start + finish), and
- 1 OpenRouteService directions call.

Geocodes and route results are cached, so repeated requests can use fewer calls.

## Stack

- Python 3.12+
- Django 6.1.1
- SQLite
- OpenRouteService (free developer tier)
- U.S. Census batch geocoder (free, one-time station preprocessing)
- Shapely + pyproj for local route-corridor spatial matching
- Leaflet + OpenStreetMap tiles for the returned map view

## Quick start (Windows PowerShell)

### 1. Create and activate a virtual environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Python 3.12 or 3.13 is recommended.

### 2. Configure the free routing API

Create a free OpenRouteService account and API key, then in PowerShell:

```powershell
$env:ORS_API_KEY="YOUR_FREE_ORS_KEY"
```

Or copy `.env.example` values into your environment using your preferred method. The project deliberately does not commit secrets.

### 3. Create the database

```powershell
python manage.py migrate
```

### 4. Import the assessment fuel-price file

```powershell
python manage.py import_fuel_prices --csv .\data\fuel-prices-for-be-assessment.csv --replace
```

Expected source CSV size: **8,151 rows**.

### 5. Geocode station data once

Fast/free first pass with the U.S. Census batch geocoder:

```powershell
python manage.py geocode_fuel_stations
```

Some source addresses are highway/exit descriptions (for example `I-44, EXIT 283 & US-69`) rather than conventional street addresses, so they may not match the Census address locator.

Optional fallback for unmatched station cities:

```powershell
python manage.py geocode_fuel_stations --city-fallback --max-city-fallback 300
```

The fallback uses Nominatim conservatively at about one unique city request per second. City-level coordinates are marked as lower precision, and the optimizer gives them a small penalty so exact geocodes are preferred.

Check data readiness:

```text
GET http://127.0.0.1:8000/api/v1/data/status/
```

### 6. Run the API

```powershell
python manage.py runserver
```

Health check:

```text
GET http://127.0.0.1:8000/api/v1/health/
```

## Main API

### `POST /api/v1/route/`

Request:

```json
{
  "start": "Dallas, TX",
  "finish": "Chicago, IL"
}
```

Example response shape:

```json
{
  "start": {
    "input": "Dallas, TX",
    "resolved": "Dallas, Dallas County, Texas, USA",
    "latitude": 32.7767,
    "longitude": -96.7970
  },
  "finish": {
    "input": "Chicago, IL",
    "resolved": "Chicago, Cook County, Illinois, USA",
    "latitude": 41.8781,
    "longitude": -87.6298
  },
  "distance_miles": 925.4,
  "vehicle": {
    "mpg": 10.0,
    "max_range_miles": 500.0,
    "tank_capacity_gallons": 50.0
  },
  "fuel": {
    "estimated_total_cost": 292.73,
    "selected_stops": [],
    "legs": []
  },
  "route_geojson": {
    "type": "LineString",
    "coordinates": []
  },
  "map_url": "http://127.0.0.1:8000/api/v1/routes/<uuid>/map/"
}
```

The exact route and costs depend on the current source CSV and the geocoded station rows.

## Optimization approach

### Vehicle model

- Maximum route-leg distance: **500 miles**
- Fuel economy: **10 MPG**
- Effective tank size: **50 gallons**

### Spatial filtering

1. OpenRouteService returns one route GeoJSON.
2. The route is projected from WGS84 to CONUS Albers (EPSG:5070).
3. Pre-geocoded fuel stations are projected locally.
4. Only stations inside an 8-mile corridor are considered.
5. Each station is assigned:
   - route-mile position,
   - approximate round-trip detour distance,
   - fuel price,
   - geocode precision.

### Cost optimization

The optimizer creates a directed acyclic graph:

- origin,
- route-adjacent fuel stations,
- destination.

An edge exists only when the next node is at most 500 route miles away. Edge cost is:

```text
(distance_miles + source_detour_miles) / 10 MPG * source_fuel_price
```

A shortest-path pass over the ordered DAG finds a low-cost feasible sequence of stops while naturally skipping unnecessary expensive stations.

### Starting-fuel assumption

The assignment provides MPG and maximum range but does not specify initial tank level or the fuel price paid at the origin.

To make total cost deterministic, the API estimates the origin fuel price from the cheapest route-adjacent station within the first 25 route miles (with documented fallbacks). This estimate is included in every response under:

```json
"origin_price_basis": "..."
```

In a production API I would expose starting fuel level and/or origin fuel price as explicit request parameters.

## Map

Every successful route is stored as a `RouteRun`. The response includes a map URL:

```text
GET /api/v1/routes/<route_id>/map/
```

The map displays:

- route polyline,
- start,
- finish,
- selected fuel stops,
- total route distance,
- estimated fuel cost.

Leaflet renders the map with OpenStreetMap tiles. The routing API itself is not called again when the map is opened.

## Performance characteristics

The hot request path intentionally avoids fuel-station geocoding and avoids routing calls inside loops.

Typical work per request:

1. cached geocoding lookup or up to 2 provider calls,
2. exactly 1 directions request,
3. local spatial filtering over the station table,
4. local ordered shortest-path optimization,
5. response persistence + caching.

Possible production improvements:

- PostgreSQL + PostGIS for indexed route-corridor queries,
- Redis for shared route/geocode caching,
- async job for refreshing fuel-price data,
- precomputed spatial index,
- provider retry/circuit-breaker logic,
- metrics/tracing,
- API authentication and rate limiting.

## Tests

Run:

```powershell
python manage.py test
```

The included optimizer tests cover:

- routes shorter than one tank range,
- long routes requiring intermediate stops,
- infeasible station gaps over 500 miles.

## API error behavior

- `400` — malformed JSON or missing start/finish
- `422` — geocoding/routing failure or no feasible station plan
- `500` — unexpected server error

## Security notes

- API keys are read from environment variables.
- No secret is committed to the repository.
- Input length is bounded.
- HTTP provider calls have explicit timeouts.
- CSRF is disabled only for the JSON assessment endpoint so Postman can call it without a browser session; for a production authenticated API I would use token/session authentication and a dedicated API framework policy.

## Data attribution / APIs

- Fuel-price dataset: provided with the assessment.
- Routing/geocoding: OpenRouteService / OpenStreetMap ecosystem.
- Batch station geocoding: U.S. Census Geocoder.
- Map tiles: OpenStreetMap contributors.
