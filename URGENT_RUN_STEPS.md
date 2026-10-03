# Fast run steps (no API key required)

This patched version uses **OpenStreetMap Nominatim** only for start/finish geocoding and **OSRM** for the route. No API key is required.

1. Keep your existing `db.sqlite3` so the 544 Census geocodes are preserved.
2. Optional but recommended before the demo:

```powershell
python manage.py geocode_fuel_stations --skip-census --city-fallback --max-city-fallback 100
```

This takes roughly 2 minutes because the public Nominatim service is intentionally rate-limited. It prioritizes cities that update the most station rows.

3. Start:

```powershell
python manage.py runserver
```

4. Test health:
`http://127.0.0.1:8000/api/v1/health/`

5. POST in Postman:
`http://127.0.0.1:8000/api/v1/route/`

```json
{
  "start": "Dallas, TX",
  "finish": "Chicago, IL"
}
```

If a sparse route cannot make a 500-mile chain, try a different long route for the Loom demo after the 100-city fallback completes.
