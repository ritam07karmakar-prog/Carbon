import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

NASA_POWER_BASE = "https://power.larc.nasa.gov/api/temporal/monthly/point"
OPEN_METEO_NDVI = "https://archive-api.open-meteo.com/v1/archive"

SATELLITE_CACHE = {}

def fetch_ndvi_era5(lat, lon, start_year=None):
    try:
        if start_year is None:
            start_year = datetime.now().year - 2
        end_year = datetime.now().year

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": f"{start_year}-01-01",
            "end_date": f"{end_year}-12-31",
            "daily": ["soil_moisture", "temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
            "timezone": "auto",
        }
        resp = requests.get(OPEN_METEO_NDVI, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            daily = data.get("daily", {})
            soil_moistures = daily.get("soil_moisture", [])
            precipitations = daily.get("precipitation_sum", [])
            temps_max = daily.get("temperature_2m_max", [])
            temps_min = daily.get("temperature_2m_min", [])

            recent = 90
            sm = [v for v in (soil_moistures or [])[-recent:] if v is not None]
            pr = [v for v in (precipitations or [])[-recent:] if v is not None]
            tmax = [v for v in (temps_max or [])[-recent:] if v is not None]
            tmin = [v for v in (temps_min or [])[-recent:] if v is not None]

            return {
                "mean_soil_moisture": round(sum(sm) / len(sm), 3) if sm else None,
                "mean_precipitation_mm": round(sum(pr) / len(pr), 1) if pr else None,
                "mean_temp_c": round((sum(tmax) / len(tmax) + sum(tmin) / len(tmin)) / 2, 1) if tmax and tmin else None,
                "data_source": "ERA5 (Open-Meteo)",
                "start_year": start_year,
                "end_year": end_year,
            }
    except Exception as e:
        logger.warning(f"ERA5 fetch failed: {e}")
    return None

def fetch_nasa_power(lat, lon):
    try:
        params = {
            "request": "execute",
            "parameters": ["PRECTOTCORR", "T2M", "GWETPROF"],
            "startDate": (datetime.now() - timedelta(days=365)).strftime("%Y%m%d"),
            "endDate": datetime.now().strftime("%Y%m%d"),
            "userCommunity": "SSE",
            "format": "JSON",
        }
        resp = requests.get(NASA_POWER_BASE, params={
            **params,
            "latitude": lat,
            "longitude": lon,
        }, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            props = data.get("properties", {}).get("parameter", {})
            precip = props.get("PRECTOTCORR", {})
            temp = props.get("T2M", {})
            moist = props.get("GWETPROF", {})

            pr_vals = [v for v in precip.values() if v is not None]
            tm_vals = [v for v in temp.values() if v is not None]
            mo_vals = [v for v in moist.values() if v is not None]

            return {
                "mean_precipitation_mm": round(sum(pr_vals) / len(pr_vals), 1) if pr_vals else None,
                "mean_temp_c": round(sum(tm_vals) / len(tm_vals), 1) if tm_vals else None,
                "mean_profile_moisture": round(sum(mo_vals) / len(mo_vals), 3) if mo_vals else None,
                "data_source": "NASA POWER",
            }
    except Exception as e:
        logger.warning(f"NASA POWER fetch failed: {e}")
    return None

def verify_location(lat, lon):
    cache_key = f"{lat:.2f},{lon:.2f}"
    if cache_key in SATELLITE_CACHE:
        return SATELLITE_CACHE[cache_key]

    result = {"latitude": lat, "longitude": lon}

    era5 = fetch_ndvi_era5(lat, lon)
    if era5:
        result.update(era5)

    power = fetch_nasa_power(lat, lon)
    if power:
        for k, v in power.items():
            if k not in result or result[k] is None:
                result[k] = v

    if era5 or power:
        result["confidence"] = "medium"
    else:
        result["confidence"] = "low"
        result["note"] = "Could not reach satellite APIs. Check internet."

    SATELLITE_CACHE[cache_key] = result
    return result

def regional_avg_som(lat, lon):
    biome_som = {
        "tropical_forest": 4.5,
        "temperate_forest": 3.5,
        "grassland": 3.0,
        "cropland": 2.5,
        "savanna": 2.0,
        "arid": 0.8,
    }

    if abs(lat) < 10:
        if abs(lon - 20) < 30:
            return {"biome": "tropical_forest", "avg_som": biome_som["tropical_forest"]}
        return {"biome": "savanna", "avg_som": biome_som["savanna"]}
    elif 10 <= abs(lat) < 35:
        return {"biome": "cropland", "avg_som": biome_som["cropland"]}
    elif 35 <= abs(lat) < 55:
        return {"biome": "temperate_forest", "avg_som": biome_som["temperate_forest"]}
    else:
        return {"biome": "grassland", "avg_som": biome_som["grassland"]}
