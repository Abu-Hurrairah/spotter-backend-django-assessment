$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -3.13 -m venv .venv
}
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py import_fuel_prices --csv .\data\fuel-prices-for-be-assessment.csv --replace
Write-Host "\nNext: set ORS_API_KEY, run station geocoding, then start Django:" -ForegroundColor Green
Write-Host '$env:ORS_API_KEY="YOUR_FREE_ORS_KEY"'
Write-Host 'python manage.py geocode_fuel_stations'
Write-Host 'python manage.py runserver'
