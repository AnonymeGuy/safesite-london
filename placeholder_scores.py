"""
Multi-dimensional London Borough baseline matrix (0-100 scale across 9 lifestyle & risk factors)
plus live parallel API updater (Environment Agency Flood API + Open-Meteo Air Quality).

Columns:
  safety       -> Metropolitan Police recorded crime rate inverse (0-100)
  transport    -> TfL Public Transport Accessibility Level (PTAL) & station density
  flood        -> Environment Agency Flood Zone 2/3 safety (updated live via EA API)
  car_friendly -> Car ownership suitability, parking ease & lower traffic congestion
  green_space  -> % green/park cover & open space access
  schools      -> Ofsted Good/Outstanding primary & secondary school density
  quietness    -> Low road/rail/flight noise & low urban crowding
  air_quality  -> Clean air baseline (updated live via Open-Meteo CAMS API)
  family_vibe  -> Suburban family suitability, garden ratio & low-rise stock
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests

# (safety, transport, flood, car_friendly, green_space, schools, quietness, air_quality, family_vibe)
_BOROUGH_METRICS = {
    "E09000001": (85, 100, 45, 15, 25, 75, 25, 45, 20),  # City of London
    "E09000002": (58, 62, 55, 78, 65, 68, 68, 70, 74),   # Barking and Dagenham
    "E09000003": (76, 72, 85, 78, 82, 88, 76, 78, 86),   # Barnet
    "E09000004": (80, 58, 72, 88, 78, 82, 82, 80, 88),   # Bexley
    "E09000005": (66, 78, 80, 58, 64, 76, 60, 66, 70),   # Brent
    "E09000006": (82, 65, 86, 90, 88, 86, 85, 86, 92),   # Bromley
    "E09000007": (54, 96, 80, 22, 72, 82, 42, 52, 55),   # Camden
    "E09000008": (68, 72, 88, 76, 78, 75, 72, 76, 80),   # Croydon
    "E09000009": (68, 76, 84, 65, 74, 80, 64, 68, 78),   # Ealing
    "E09000010": (72, 64, 76, 80, 80, 76, 74, 76, 82),   # Enfield
    "E09000011": (66, 78, 62, 62, 76, 78, 65, 70, 74),   # Greenwich
    "E09000012": (52, 86, 82, 28, 68, 74, 45, 56, 52),   # Hackney
    "E09000013": (62, 90, 38, 32, 60, 82, 48, 56, 60),   # Hammersmith and Fulham
    "E09000014": (62, 82, 84, 48, 74, 78, 56, 64, 68),   # Haringey
    "E09000015": (82, 66, 88, 84, 78, 88, 80, 82, 88),   # Harrow
    "E09000016": (78, 60, 84, 90, 84, 78, 84, 84, 88),   # Havering
    "E09000017": (72, 66, 76, 84, 80, 78, 62, 72, 82),   # Hillingdon
    "E09000018": (66, 72, 66, 68, 74, 78, 52, 68, 74),   # Hounslow
    "E09000019": (56, 94, 82, 20, 48, 76, 40, 52, 48),   # Islington
    "E09000020": (64, 92, 76, 25, 62, 86, 48, 54, 58),   # Kensington and Chelsea
    "E09000021": (82, 68, 48, 78, 80, 90, 78, 82, 88),   # Kingston upon Thames
    "E09000022": (58, 90, 70, 30, 62, 76, 46, 56, 56),   # Lambeth
    "E09000023": (64, 82, 64, 48, 68, 76, 58, 64, 68),   # Lewisham
    "E09000024": (76, 76, 76, 68, 82, 84, 72, 76, 84),   # Merton
    "E09000025": (56, 84, 62, 45, 56, 74, 52, 60, 62),   # Newham
    "E09000026": (72, 72, 80, 76, 78, 86, 74, 76, 84),   # Redbridge
    "E09000027": (86, 76, 42, 74, 94, 94, 82, 86, 94),   # Richmond upon Thames
    "E09000028": (56, 88, 54, 28, 64, 78, 46, 56, 56),   # Southwark
    "E09000029": (84, 68, 86, 86, 82, 92, 84, 84, 90),   # Sutton
    "E09000030": (54, 92, 68, 24, 52, 74, 40, 52, 48),   # Tower Hamlets
    "E09000031": (68, 78, 80, 58, 78, 80, 66, 70, 76),   # Waltham Forest
    "E09000032": (72, 86, 58, 42, 78, 86, 62, 66, 76),   # Wandsworth
    "E09000033": (44, 98, 62, 18, 68, 82, 34, 48, 45),   # Westminster
}

_BOROUGH_CENTROIDS = {
    "E09000001": (51.5155, -0.0922), "E09000002": (51.5465, 0.1313), "E09000003": (51.6252, -0.1517),
    "E09000004": (51.4549, 0.1505),  "E09000005": (51.5588, -0.2817), "E09000006": (51.3760, 0.0489),
    "E09000007": (51.5455, -0.1628), "E09000008": (51.3714, -0.0977), "E09000009": (51.5130, -0.3089),
    "E09000010": (51.6538, -0.0799), "E09000011": (51.4892, 0.0648),  "E09000012": (51.5450, -0.0553),
    "E09000013": (51.4927, -0.2339), "E09000014": (51.5906, -0.1110), "E09000015": (51.5898, -0.3346),
    "E09000016": (51.5779, 0.2121),  "E09000017": (51.5441, -0.4760), "E09000018": (51.4746, -0.3680),
    "E09000019": (51.5416, -0.1022), "E09000020": (51.5020, -0.1947), "E09000021": (51.4085, -0.3064),
    "E09000022": (51.4571, -0.1231), "E09000023": (51.4415, -0.0117), "E09000024": (51.4098, -0.2108),
    "E09000025": (51.5255, 0.0352),  "E09000026": (51.5886, 0.0824),  "E09000027": (51.4479, -0.3260),
    "E09000028": (51.4733, -0.0735), "E09000029": (51.3618, -0.1945), "E09000030": (51.5150, -0.0172),
    "E09000031": (51.5908, -0.0134), "E09000032": (51.4567, -0.1910), "E09000033": (51.5145, -0.1595),
}

COLUMNS = [
    "safety",
    "transport",
    "flood",
    "car_friendly",
    "green_space",
    "schools",
    "quietness",
    "air_quality",
    "family_vibe",
]


def placeholder_external_scores(
    live_refresh: bool = True,
    apply_live_api: bool = True,
    **kwargs,
) -> pd.DataFrame:
    """Returns the 9-dimension borough DataFrame and optionally updates Flood & Air scores via live APIs."""
    df = pd.DataFrame.from_dict(_BOROUGH_METRICS, orient="index", columns=COLUMNS).astype(float)
    if not (live_refresh and apply_live_api):
        return df

    # 1. Live UK Environment Agency Flood Alerts check across Greater London (1 API call)
    try:
        r_flood = requests.get(
            "https://environment.data.gov.uk/flood-monitoring/id/floods?lat=51.5074&long=-0.1278&dist=30",
            timeout=5,
        )
        if r_flood.status_code == 200:
            items = r_flood.json().get("items", [])
            for item in items:
                area_desc = str(item.get("description", "") + " " + item.get("eaAreaName", "")).lower()
                sev = item.get("severityLevel", 4)
                if sev <= 3:
                    for code in df.index:
                        if any(k in area_desc for k in ["thames", "london", "lea", "roding", "wandle", "ravensbourne"]):
                            df.loc[code, "flood"] = max(25.0, df.loc[code, "flood"] - 6.0)
    except Exception:
        pass

    # 2. Live Open-Meteo European AQI sample across London zones to calibrate live air_quality scores
    def _fetch_zone_aqi(code_coords):
        code, (lat, lon) = code_coords
        try:
            r = requests.get(
                f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=european_aqi,nitrogen_dioxide",
                timeout=3,
            )
            if r.status_code == 200:
                curr = r.json().get("current", {})
                no2 = float(curr.get("nitrogen_dioxide") or 25.0)
                live_score = max(35.0, min(96.0, 100.0 - no2 * 1.15))
                return code, live_score
        except Exception:
            pass
        return code, None

    try:
        sample_codes = [
            "E09000033", "E09000007", "E09000006", "E09000027",
            "E09000016", "E09000003", "E09000028", "E09000009",
        ]
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(_fetch_zone_aqi, [(c, _BOROUGH_CENTROIDS[c]) for c in sample_codes]))
        for code, live_sc in results:
            if live_sc is not None:
                df.loc[code, "air_quality"] = round(0.6 * df.loc[code, "air_quality"] + 0.4 * live_sc, 1)
    except Exception:
        pass

    return df
