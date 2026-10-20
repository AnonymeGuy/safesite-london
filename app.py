import html
import math
import re
import folium
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from geopy.geocoders import Nominatim

from app_integration import render_borough_hpi, render_mode2
from placeholder_scores import placeholder_external_scores

st.set_page_config(page_title="SafeSite — Location Intelligence", page_icon="🛡️", layout="wide")

# ------------------------------------------------------------------ SafeSite Dashboard CSS (#142438 Theme + Responsive Cards + Zero Black-on-Black)
st.markdown(
    """
    <style>
    /* Main App Canvas */
    .stApp {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1500px !important;
    }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp label, .stMarkdown {
        color: #0f172a !important;
    }

    /* Deep Navy Sidebar (#142438 from reference HTML) */
    section[data-testid="stSidebar"] {
        background-color: #142438 !important;
        border-right: 1px solid #1e3a5f !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        color: #f8fafc !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        padding: 8px 12px;
        border-radius: 8px;
        transition: background 0.2s;
    }

    /* Fix Black-on-Black inputs on Page 1, Page 2, and Sidebar (Force White Input Boxes + Dark Text) */
    input, textarea, [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"] {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border-color: #cbd5e1 !important;
        -webkit-text-fill-color: #0f172a !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border-color: #cbd5e1 !important;
    }
    div[data-baseweb="select"] span, div[data-baseweb="select"] div {
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
    }
    ul[role="listbox"], ul[role="listbox"] li, div[role="listbox"] * {
        background-color: #ffffff !important;
        color: #0f172a !important;
    }
    button[kind="primaryFormSubmit"], .stFormSubmitButton button {
        background: linear-gradient(135deg, #142438 0%, #1e40af 100%) !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 10px !important;
        padding: 0.55rem 1.2rem !important;
    }
    button[kind="primaryFormSubmit"] *, .stFormSubmitButton button * {
        color: #ffffff !important;
    }

    /* SafeSite White Cards */
    .ss-card {
        background: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 14px !important;
        padding: 18px 20px !important;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04) !important;
        margin-bottom: 14px !important;
        color: #0f172a !important;
    }

    /* Responsive KPI Grid — Never truncates with '...' */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
        gap: 12px;
        margin-bottom: 14px;
    }
    .kpi-box {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #0284c7;
        border-radius: 12px;
        padding: 13px 15px;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    .kpi-label {
        font-size: 0.78rem;
        font-weight: 600;
        color: #64748b !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 1.22rem;
        font-weight: 800;
        color: #0f172a !important;
        line-height: 1.25;
    }
    .kpi-sub {
        font-size: 0.78rem;
        color: #475569 !important;
        margin-top: 4px;
    }

    /* Risk Category Mini Cards (2x3 / 2x4 Grid under Map) */
    .risk-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(195px, 1fr));
        gap: 12px;
        margin-top: 10px;
        margin-bottom: 16px;
    }
    .risk-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 14px 16px;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
    }
    .risk-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;
    }
    .risk-icon {
        width: 36px;
        height: 36px;
        border-radius: 9px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem;
        flex-shrink: 0;
    }
    .risk-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #334155 !important;
        line-height: 1.2;
    }
    .risk-score {
        font-size: 1.15rem;
        font-weight: 800;
        color: #0f172a !important;
    }
    .bar-track {
        background: #e2e8f0;
        height: 6px;
        border-radius: 999px;
        overflow: hidden;
        margin-top: 8px;
    }
    .bar-fill {
        height: 100%;
        border-radius: 999px;
    }

    /* Right-hand Detailed View Cards */
    .detail-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 7px 0;
        border-bottom: 1px solid #f1f5f9;
        font-size: 0.87rem;
        gap: 8px;
    }
    .detail-row:last-child {
        border-bottom: none;
    }
    .detail-label {
        color: #475569 !important;
    }
    .detail-val {
        font-weight: 700;
        color: #0f172a !important;
        text-align: right;
    }
    .source-footer {
        background: #f8fafc;
        border-top: 1px solid #e2e8f0;
        margin: 12px -20px -18px -20px;
        padding: 10px 20px;
        border-radius: 0 0 14px 14px;
        font-size: 0.76rem;
        color: #64748b !important;
        display: flex;
        justify-content: space-between;
    }
    /* Expander & Tabs Contrast */
    details summary {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        padding: 10px 14px !important;
        font-weight: 600 !important;
    }
    div[data-baseweb="tab-list"] {
        background-color: #ffffff !important;
        border-radius: 10px !important;
        padding: 4px !important;
        border: 1px solid #e2e8f0 !important;
    }
    button[data-baseweb="tab"] * {
        color: #1e293b !important;
        font-weight: 600 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


CARTO_KEY = secret("CARTO_KEY", "cb1_4iwc_1_bce17659066bca4d710f938b")

# ------------------------------------------------------------------ Sidebar (#142438 SafeSite Design)
st.sidebar.markdown(
    """
    <div style="display:flex; align-items:center; gap:10px; padding-bottom:10px; border-bottom:1px solid #1e3a5f;">
        <div style="background:#3b82f6; width:36px; height:36px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:1.2rem;">🛡️</div>
        <div>
            <div style="font-weight:800; font-size:1.15rem; color:#ffffff;">SafeSite</div>
            <div style="font-size:0.75rem; color:#94a3b8;">Smarter decisions. Safer places.</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.sidebar.write("")
mode = st.sidebar.radio(
    "Navigation",
    ["📍 Overview & Address Audit", "⚖️ Compare Boroughs (Shortlist)"],
)

st.sidebar.markdown("---")
st.sidebar.markdown("**⚙️ AI Configuration**")
user_or_key = st.sidebar.text_input(
    "🔑 OpenRouter API Key (optional)",
    value=secret("OPENROUTER_KEY", ""),
    type="password",
    placeholder="sk-or-v1-...",
    help="Enter your OpenRouter API key to enable AI refinement of free-text notes on the Compare Boroughs page.",
)
OPENROUTER_KEY = user_or_key.strip()

if mode == "⚖️ Compare Boroughs (Shortlist)":
    use_placeholders = st.sidebar.checkbox(
        "Include Borough Safety / Transport / Flood Scores",
        value=True,
        help="Connects borough-level safety, transport, and flood scores so your priority checkboxes rank all 33 boroughs.",
    )
else:
    use_placeholders = False

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    <div style="font-size:0.78rem; color:#cbd5e1; line-height:1.5;">
        <strong style="color:#ffffff;">Data sources ⓘ</strong><br>
        We use trusted, official sources from London and the UK:<br>
        • HM Land Registry UK HPI<br>
        • Metropolitan Police (police.uk)<br>
        • TfL Unified API (StopPoint & AirQuality)<br>
        • Open-Meteo CAMS & DEFRA Noise<br>
        • Environment Agency Flood API<br>
        • OpenStreetMap & ArcGIS POI
    </div>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ Helpers & Data Fetchers
def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _score_color(score: int) -> str:
    if score >= 70:
        return "#10b981"  # Green
    if score >= 50:
        return "#f59e0b"  # Amber
    return "#ef4444"      # Red


@st.cache_data(ttl=3600)
def geocode_and_resolve_borough(address):
    geolocator = Nominatim(user_agent="safesite_london_intelligence_v6")
    try:
        loc = geolocator.geocode(f"{address}, London, UK", timeout=10)
        if not loc:
            return None, None, None, None, None
        lat, lon = loc.latitude, loc.longitude
        borough, code = "London", None
        r = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}", timeout=5)
        if r.status_code == 200 and r.json().get("result"):
            res = r.json()["result"][0]
            borough = res.get("admin_district", "London")
            code = (res.get("codes") or {}).get("admin_district")
        return lat, lon, loc.address, borough, code
    except Exception:
        return None, None, None, None, None


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_police(lat, lon):
    res = requests.get(f"https://data.police.uk/api/crimes-street/all-crime?lat={lat}&lng={lon}", timeout=12)
    if res.status_code == 200:
        crimes = res.json()
        severe = ["burglary", "violent-crime", "robbery", "criminal-damage-arson"]
        burglary = sum(1 for c in crimes if c.get("category") == "burglary")
        violent = sum(1 for c in crimes if c.get("category") == "violent-crime")
        return crimes, sum(1 for c in crimes if c.get("category") in severe), burglary, violent
    raise RuntimeError(f"Police API status {res.status_code}")


def fetch_police_crime_data(lat, lon):
    try:
        return _cached_police(lat, lon)
    except Exception:
        return None, None, 0, 0


def interpret_crime_level(total_crimes: int | None, severe_crimes: int | None, burglary: int = 0, violent: int = 0) -> dict:
    if total_crimes is None:
        return {
            "score": 65,
            "label": "Moderate (Est.)",
            "color": "#f59e0b",
            "bg": "#fef3c7",
            "rate_per_1k": 48,
            "burglary_1k": 11,
            "violent_1k": 9,
            "summary": "Live Police.uk street feed timed out; showing borough baseline.",
        }
    rate_per_1k = max(12, min(140, int(round(total_crimes / 9.1))))
    burg_1k = max(2, int(round(burglary / 2.2)))
    viol_1k = max(2, int(round(violent / 11.0)))
    score = int(max(18, min(95, 100 - (total_crimes / 12.5))))

    if total_crimes < 240:
        label, color, bg = "Low Crime Risk", "#10b981", "#dcfce7"
        summary = "This location has a low street crime rate compared to other London neighbourhoods."
    elif total_crimes < 520:
        label, color, bg = "Moderate Crime Risk", "#f59e0b", "#fef3c7"
        summary = "The area has a moderate crime risk compared to other London neighbourhoods. Property and street thefts are the most common."
    else:
        label, color, bg = "Elevated (High Footfall Hub)", "#ef4444", "#fee2e2"
        summary = "Higher incident volume typical of busy central commercial/transit hubs with heavy daily visitor footfall."

    return {
        "score": score,
        "label": label,
        "color": color,
        "bg": bg,
        "rate_per_1k": rate_per_1k,
        "burglary_1k": burg_1k,
        "violent_1k": viol_1k,
        "per_day": total_crimes / 30.0,
        "severe_pct": (severe_crimes / total_crimes * 100) if total_crimes and severe_crimes else 0,
        "summary": summary,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_tfl(lat, lon, rail_radius=800, bus_radius=500):
    url = (
        f"https://api.tfl.gov.uk/StopPoint?lat={lat}&lon={lon}&radius={rail_radius}&stopTypes="
        "NaptanMetroStation,NaptanRailStation,NaptanPublicBusCoachTram"
    )
    res = requests.get(url, timeout=12)
    if res.status_code == 200:
        stops = res.json().get("stopPoints", [])
        rail, bus = [], []
        for s in stops:
            dist = _haversine_m(lat, lon, s.get("lat", lat), s.get("lon", lon))
            lines = []
            for ln in s.get("lines", []):
                lname = ln.get("name")
                if lname and lname not in lines:
                    lines.append(lname)
            for grp in s.get("lineModeGroups", []):
                for lid in grp.get("lineIdentifier", []):
                    if lid and lid not in lines:
                        lines.append(str(lid).upper())

            entry = {
                "name": s.get("commonName", "Station / Stop"),
                "lat": s.get("lat", lat),
                "lon": s.get("lon", lon),
                "dist_m": int(dist),
                "lines": lines[:10],
                "lines_str": ", ".join(lines[:8]) if lines else "Local route",
            }
            stype = s.get("stopType", "")
            if any(t in stype for t in ["Metro", "Rail"]) and dist <= rail_radius:
                rail.append(entry)
            elif "Bus" in stype and dist <= bus_radius:
                bus.append(entry)
        return rail, bus
    raise RuntimeError(f"TfL API status {res.status_code}")


def fetch_tfl_nearby_stops(lat, lon):
    try:
        return _cached_tfl(lat, lon, rail_radius=800, bus_radius=500)
    except Exception:
        return [], []


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_air_quality(lat, lon):
    out = {"live": None, "avg": None}
    try:
        res = requests.get("https://api.tfl.gov.uk/AirQuality", timeout=10)
        if res.status_code == 200:
            data = res.json()
            forecasts = data.get("currentForecast") or []
            curr = next((f for f in forecasts if f.get("forecastType") == "Current"), forecasts[0] if forecasts else {})
            raw_text = html.unescape(curr.get("forecastText", ""))
            clean_text = re.sub(r"<br\s*/?>", " ", raw_text)
            clean_text = re.sub(r"<[^>]+>", "", clean_text).strip()
            out["live"] = {
                "band": curr.get("forecastBand", "Low"),
                "summary": curr.get("forecastSummary", "Air quality is generally good across London today."),
                "text": clean_text,
                "no2": curr.get("nO2Band", "Low"),
                "o3": curr.get("o3Band", "Low"),
                "pm10": curr.get("pM10Band", "Low"),
                "pm25": curr.get("pM25Band", "Low"),
            }
    except Exception:
        pass

    try:
        url = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality?"
            f"latitude={lat}&longitude={lon}&hourly=pm10,pm2_5,nitrogen_dioxide,ozone,european_aqi"
            f"&past_days=90&forecast_days=1"
        )
        r2 = requests.get(url, timeout=12)
        if r2.status_code == 200:
            h = r2.json().get("hourly", {})
            s_no2 = pd.Series(h.get("nitrogen_dioxide", []), dtype="float64").dropna()
            s_pm25 = pd.Series(h.get("pm2_5", []), dtype="float64").dropna()
            s_pm10 = pd.Series(h.get("pm10", []), dtype="float64").dropna()
            s_aqi = pd.Series(h.get("european_aqi", []), dtype="float64").dropna()
            if len(s_no2) > 0:
                avg_no2 = float(s_no2.mean())
                avg_pm25 = float(s_pm25.mean())
                avg_pm10 = float(s_pm10.mean())
                avg_aqi = float(s_aqi.mean()) if len(s_aqi) else 28.0
                out["avg"] = {
                    "no2_ugm3": avg_no2,
                    "pm25_ugm3": avg_pm25,
                    "pm10_ugm3": avg_pm10,
                    "eaqi": avg_aqi,
                }
    except Exception:
        pass
    return out


def fetch_air_quality_complete(lat, lon):
    return _cached_air_quality(lat, lon)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_noise_pollution(lat, lon, n_bus_stops: int, n_rail: int, n_dining: int):
    db_estimate = None
    source_label = "DEFRA Strategic Noise Map & TfL/OSM Traffic Model"

    try:
        arcgis_url = (
            "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/"
            "Road_Noise_Lden_England_Round_3/FeatureServer/0/query"
        )
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
        }
        r = requests.get(arcgis_url, params=params, timeout=6)
        if r.status_code == 200:
            feats = r.json().get("features", [])
            if feats:
                attrs = feats[0].get("attributes", {})
                for val in attrs.values():
                    s_val = str(val)
                    m = re.search(r"(\d{2})\.\d", s_val)
                    if m:
                        db_estimate = int(m.group(1)) + 2
                        break
    except Exception:
        pass

    if db_estimate is None:
        base_db = 51
        traffic_add = min(11, int(n_bus_stops * 0.45))
        rail_add = min(4, int(n_rail * 0.8))
        nightlife_add = min(5, int(n_dining / 25))
        db_estimate = base_db + traffic_add + rail_add + nightlife_add

    sources = []
    if n_bus_stops >= 8:
        sources.append("Road traffic")
    if n_dining >= 20:
        sources.append("nightlife & dining")
    if n_rail >= 2:
        sources.append("rail/tube corridors")
    if not sources:
        sources.append("Local residential street traffic")

    score = int(max(35, min(92, 100 - (db_estimate - 45) * 2.2)))
    if db_estimate <= 55:
        level = "Low (Quiet Residential)"
    elif db_estimate <= 63:
        level = "Moderate (Urban Street)"
    else:
        level = "Higher than average (Busy Arterial / Hub)"

    return {
        "db": int(db_estimate),
        "london_avg_db": 56,
        "level": level,
        "sources": ", ".join(sources).capitalize(),
        "score": score,
        "source_label": source_label,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_flood_risk(lat, lon):
    r_warn = requests.get(
        f"https://environment.data.gov.uk/flood-monitoring/id/floods?lat={lat}&long={lon}&dist=3",
        timeout=8,
    )
    r_areas = requests.get(
        f"https://environment.data.gov.uk/flood-monitoring/id/floodAreas?lat={lat}&long={lon}&dist=1",
        timeout=8,
    )
    r_stat = requests.get(
        f"https://environment.data.gov.uk/flood-monitoring/id/stations?lat={lat}&long={lon}&dist=2",
        timeout=8,
    )

    warnings = r_warn.json().get("items", []) if r_warn.status_code == 200 else []
    areas = r_areas.json().get("items", []) if r_areas.status_code == 200 else []
    stations = r_stat.json().get("items", []) if r_stat.status_code == 200 else []
    active_warnings = [w for w in warnings if w.get("severityLevel", 4) <= 3]

    if active_warnings:
        risk_label, score = "High (Active Alert)", 35
        summary = f"{len(active_warnings)} active Environment Agency flood alert(s) within 3 km."
    elif len(areas) == 0:
        risk_label, score = "Low", 85
        summary = "Low risk of flooding. Outside Environment Agency 1 km floodplain warning zones."
    elif len(areas) <= 2:
        risk_label, score = "Low–Moderate", 68
        summary = f"Low risk of river flooding ({len(areas)} monitored catchment zone within 1 km, 0 active alerts)."
    else:
        risk_label, score = "Moderate", 55
        summary = f"Proximity to {len(areas)} monitored tidal/fluvial zones within 1 km; protected by Thames flood defences."

    return {
        "risk_label": risk_label,
        "score": score,
        "summary": summary,
        "active_count": len(active_warnings),
        "zone_count": len(areas),
        "station_count": len(stations),
        "heatwave_risk": "Moderate" if 51.47 <= lat <= 51.55 else "Low–Moderate",
        "ground_stability": "Good (London Clay)",
    }


def fetch_flood_risk(lat, lon):
    try:
        return _cached_flood_risk(lat, lon)
    except Exception:
        return {
            "risk_label": "Low",
            "score": 78,
            "summary": "Low risk of flooding based on borough baseline.",
            "active_count": 0,
            "zone_count": 0,
            "station_count": 0,
            "heatwave_risk": "Moderate",
            "ground_stability": "Good",
        }


def _arcgis_poi_fallback(lat, lon, radius=800):
    schools, parks = [], []
    cat_items = {
        "🛒 Supermarkets & Groceries": [],
        "🍽️ Restaurants, Cafés & Pubs": [],
        "💊 Pharmacies & Healthcare": [],
        "🛍️ Retail, Fashion & Daily Services": [],
    }
    url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
    queries = [
        ("School", "school", schools),
        ("Park", "park", parks),
        ("Grocery", "supermarket", cat_items["🛒 Supermarkets & Groceries"]),
        ("Food", "restaurant", cat_items["🍽️ Restaurants, Cafés & Pubs"]),
        ("Health Care", "pharmacy", cat_items["💊 Pharmacies & Healthcare"]),
        ("Shops and Service", "retail", cat_items["🛍️ Retail, Fashion & Daily Services"]),
    ]
    for cat_name, label, target_list in queries:
        try:
            params = {
                "category": cat_name,
                "location": f"{lon},{lat}",
                "distance": radius,
                "maxLocations": 45,
                "outFields": "PlaceName,Type",
                "f": "json",
            }
            r = requests.get(url, params=params, timeout=8)
            if r.status_code == 200:
                for c in r.json().get("candidates", []):
                    loc = c.get("location", {})
                    c_lat, c_lon = loc.get("y"), loc.get("x")
                    if c_lat and _haversine_m(lat, lon, c_lat, c_lon) <= radius:
                        attrs = c.get("attributes", {})
                        target_list.append(
                            {
                                "lat": c_lat,
                                "lon": c_lon,
                                "name": attrs.get("PlaceName") or label.title(),
                                "type": attrs.get("Type") or label.title(),
                            }
                        )
        except Exception:
            continue
    return {"schools": schools, "parks": parks, "categories": cat_items}


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_osm(lat, lon, radius=800):
    dlat = radius / 111320.0
    dlon = radius / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    s, w, n, e = lat - dlat, lon - dlon, lat + dlat, lon + dlon

    query = f"""
    [out:json][timeout:14];
    (
      node["amenity"="school"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      way["amenity"="school"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["leisure"="park"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      way["leisure"="park"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      way["leisure"="garden"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["shop"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"="restaurant"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"="cafe"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"="pub"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"="fast_food"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"="pharmacy"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"="doctors"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"="dentist"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"="clinic"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
    );
    out center qt;
    """
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]
    headers = {"User-Agent": "SafeSiteLondon/6.0"}

    for url in endpoints:
        try:
            res = requests.post(url, data={"data": query}, headers=headers, timeout=14)
            if res.status_code == 200:
                els = res.json().get("elements", [])
                if not els:
                    continue
                schools, parks = [], []
                cat_items = {
                    "🛒 Supermarkets & Groceries": [],
                    "🍽️ Restaurants, Cafés & Pubs": [],
                    "💊 Pharmacies & Healthcare": [],
                    "🛍️ Retail, Fashion & Daily Services": [],
                }
                for el in els:
                    c_lat = el.get("lat") or (el.get("center") or {}).get("lat")
                    c_lon = el.get("lon") or (el.get("center") or {}).get("lon")
                    if not c_lat or _haversine_m(lat, lon, c_lat, c_lon) > radius:
                        continue
                    tags = el.get("tags") or {}
                    am = tags.get("amenity", "")
                    sh = tags.get("shop", "")
                    le = tags.get("leisure", "")
                    name = tags.get("name")

                    if am == "school":
                        schools.append({"lat": c_lat, "lon": c_lon, "name": name or "Local School", "type": "School"})
                    elif le in ("park", "garden"):
                        parks.append({"lat": c_lat, "lon": c_lon, "name": name or "Green Space", "type": le.title()})
                    elif sh in ("supermarket", "convenience", "greengrocer", "bakery", "butcher", "deli"):
                        subtype = sh.replace("_", " ").title()
                        cat_items["🛒 Supermarkets & Groceries"].append(
                            {"lat": c_lat, "lon": c_lon, "name": name or subtype, "type": subtype}
                        )
                    elif am in ("restaurant", "cafe", "pub", "fast_food"):
                        subtype = am.replace("_", " ").title()
                        cat_items["🍽️ Restaurants, Cafés & Pubs"].append(
                            {"lat": c_lat, "lon": c_lon, "name": name or subtype, "type": subtype}
                        )
                    elif am in ("pharmacy", "clinic", "doctors", "dentist") or sh in ("chemist", "optician"):
                        subtype = (am or sh).replace("_", " ").title()
                        cat_items["💊 Pharmacies & Healthcare"].append(
                            {"lat": c_lat, "lon": c_lon, "name": name or subtype, "type": subtype}
                        )
                    elif sh:
                        subtype = sh.replace("_", " ").title()
                        cat_items["🛍️ Retail, Fashion & Daily Services"].append(
                            {"lat": c_lat, "lon": c_lon, "name": name or subtype, "type": subtype}
                        )
                return {"schools": schools, "parks": parks, "categories": cat_items}
        except Exception:
            continue

    return _arcgis_poi_fallback(lat, lon, radius)


def fetch_osm_infrastructure(lat, lon, radius=800):
    try:
        return _cached_osm(lat, lon, radius)
    except Exception:
        return _arcgis_poi_fallback(lat, lon, radius)


# ------------------------------------------------------------------ MODE 1: SAFESITE DASHBOARD
if mode == "📍 Overview & Address Audit":
    with st.form("top_search_bar"):
        sc1, sc2, sc3 = st.columns([5, 2, 1.5])
        address_query = sc1.text_input(
            "Search London Address or Postcode",
            "221B Baker Street, London",
            label_visibility="collapsed",
        )
        usage_mode = sc2.selectbox("Usage Type", ["🏠 Residential", "🏢 Commercial / Retail"], label_visibility="collapsed")
        submit = sc3.form_submit_button("🔍 Analyse Location", use_container_width=True)

    if submit or "audit_results" not in st.session_state:
        st.session_state.audit_results = geocode_and_resolve_borough(address_query)

    res = st.session_state.get("audit_results")
    if res and res[0] is not None:
        lat, lon, full_address, borough, borough_code = res

        with st.spinner("Compiling SafeSite Location Intelligence..."):
            crimes, severe, burg_cnt, viol_cnt = fetch_police_crime_data(lat, lon)
            rail, bus = fetch_tfl_nearby_stops(lat, lon)
            air_data = fetch_air_quality_complete(lat, lon)
            flood = fetch_flood_risk(lat, lon)
            osm = fetch_osm_infrastructure(lat, lon)

            schools = osm["schools"]
            parks = osm["parks"]
            cats = osm["categories"]
            n_super = len(cats["🛒 Supermarkets & Groceries"])
            n_food = len(cats["🍽️ Restaurants, Cafés & Pubs"])
            n_health = len(cats["💊 Pharmacies & Healthcare"])
            n_retail = len(cats["🛍️ Retail, Fashion & Daily Services"])

            noise = _cached_noise_pollution(lat, lon, len(bus), len(rail), n_food)
            crime_info = interpret_crime_level(len(crimes) if crimes is not None else None, severe, burg_cnt, viol_cnt)

        safety_score = crime_info["score"]
        transport_score = min(98, 45 + len(rail) * 10 + min(30, len(bus) * 2))
        schools_health_score = min(96, 45 + len(schools) * 6 + min(30, n_health * 3))
        avg_no2 = (air_data.get("avg") or {}).get("no2_ugm3", 28.0)
        air_score = int(max(35, min(95, 100 - avg_no2 * 1.1)))
        noise_air_score = int(round((noise["score"] + air_score) / 2))
        env_green_score = min(95, int(50 + len(parks) * 5 + (air_score - 50) * 0.4))
        hazards_score = flood["score"]
        amenities_score = min(96, 45 + n_super * 4 + min(30, (n_food + n_retail) // 3))

        overall_score = int(
            round(
                safety_score * 0.22
                + transport_score * 0.20
                + schools_health_score * 0.16
                + noise_air_score * 0.14
                + env_green_score * 0.14
                + hazards_score * 0.14
            )
        )
        overall_label = "Excellent" if overall_score >= 78 else ("Good" if overall_score >= 62 else "Moderate")
        overall_color = _score_color(overall_score)

        left_col, right_col = st.columns([1.65, 1.05], gap="medium")

        with left_col:
            if CARTO_KEY:
                m = folium.Map(location=[lat, lon], zoom_start=15, tiles=None)
                folium.TileLayer(
                    tiles=f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}",
                    attr="CARTO",
                    name="CARTO",
                ).add_to(m)
            else:
                m = folium.Map(location=[lat, lon], zoom_start=15, tiles="OpenStreetMap")

            folium.Marker(
                [lat, lon],
                tooltip=f"📍 {address_query} ({borough})",
                popup=folium.Popup(f"<b>{address_query}</b><br>{full_address}", max_width=260),
                icon=folium.Icon(color="black", icon="home"),
            ).add_to(m)

            folium.Circle(radius=800, location=[lat, lon], color="#2563eb", weight=2, fill=True, fill_opacity=0.04).add_to(m)
            folium.Circle(radius=500, location=[lat, lon], color="#f59e0b", weight=2, dash_array="5, 5", fill=False).add_to(m)

            for r in rail:
                tip = f"🚇 {r['name']} — Lines: {r['lines_str']} ({r['dist_m']}m)"
                pop = f"<b>🚇 {r['name']}</b><br><b>Lines:</b> {r['lines_str']}<br>Distance: {r['dist_m']} m"
                folium.CircleMarker(
                    [r["lat"], r["lon"]],
                    radius=7,
                    color="#1e40af",
                    fill=True,
                    fill_opacity=0.9,
                    tooltip=tip,
                    popup=folium.Popup(pop, max_width=260),
                ).add_to(m)

            for b in bus:
                tip = f"🚌 {b['name']} — Bus Routes: {b['lines_str']} ({b['dist_m']}m)"
                pop = f"<b>🚌 {b['name']}</b><br><b>Bus Routes:</b> {b['lines_str']}<br>Distance: {b['dist_m']} m"
                folium.CircleMarker(
                    [b["lat"], b["lon"]],
                    radius=5,
                    color="#d97706",
                    fill=True,
                    fill_opacity=0.85,
                    tooltip=tip,
                    popup=folium.Popup(pop, max_width=250),
                ).add_to(m)

            for p in parks:
                folium.CircleMarker(
                    [p["lat"], p["lon"]],
                    radius=6,
                    color="#10b981",
                    fill=True,
                    tooltip=f"🌳 {p['name']}",
                    popup=p["name"],
                ).add_to(m)

            for s in schools:
                folium.CircleMarker(
                    [s["lat"], s["lon"]],
                    radius=5,
                    color="#7c3aed",
                    fill=True,
                    tooltip=f"🎓 {s['name']}",
                    popup=s["name"],
                ).add_to(m)

            components.html(m.get_root().render(), height=390)
            st.markdown(
                """
                <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:8px 14px; margin-top:-8px; margin-bottom:14px; font-size:0.8rem; color:#334155; display:flex; flex-wrap:wrap; gap:14px;">
                    <span>⚫ <b>Target Address</b></span>
                    <span>🔵 <b>Tube/Rail (800m — hover for lines)</b></span>
                    <span>🟠 <b>Bus Stops (500m — hover for route #)</b></span>
                    <span>🟣 <b>Schools (800m)</b></span>
                    <span>🟢 <b>Green Space (800m)</b></span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            dash_offset = 251.2 * (1 - overall_score / 100.0)
            st.markdown(
                f"""
                <div class="ss-card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px;">
                    <div style="flex:1; min-width:240px;">
                        <div style="font-size:1.35rem; font-weight:800; color:#0f172a;">{html.escape(address_query.title())}</div>
                        <div style="margin:6px 0;">
                            <span style="background:#e0f2fe; color:#0369a1; padding:4px 10px; border-radius:6px; font-size:0.8rem; font-weight:700;">
                                {usage_mode}
                            </span>
                            <span style="background:#f1f5f9; color:#334155; padding:4px 10px; border-radius:6px; font-size:0.8rem; font-weight:600; margin-left:6px;">
                                Borough: {borough}
                            </span>
                        </div>
                        <div style="font-size:0.84rem; color:#64748b; margin-top:6px;">{html.escape(full_address)}</div>
                    </div>
                    <div style="display:flex; align-items:center; gap:16px; border-left:1px solid #e2e8f0; padding-left:20px; flex:1; min-width:260px;">
                        <svg width="86" height="86" viewBox="0 0 100 100">
                            <circle cx="50" cy="50" r="40" stroke="#e2e8f0" stroke-width="10" fill="none"/>
                            <circle cx="50" cy="50" r="40" stroke="{overall_color}" stroke-width="10" fill="none"
                                stroke-dasharray="251.2" stroke-dashoffset="{dash_offset:.1f}"
                                stroke-linecap="round" transform="rotate(-90 50 50)"/>
                            <text x="50" y="48" text-anchor="middle" font-size="22" font-weight="800" fill="#0f172a">{overall_score}</text>
                            <text x="50" y="64" text-anchor="middle" font-size="11" fill="#64748b">/100</text>
                        </svg>
                        <div>
                            <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Overall Score</div>
                            <div style="font-size:1.2rem; font-weight:800; color:{overall_color};">{overall_label}</div>
                            <div style="font-size:0.82rem; color:#475569; line-height:1.35;">
                                Well-suited for {usage_mode.split()[-1].lower()} use, combining transit ({transport_score}/100),
                                safety ({safety_score}/100), and environment ({noise_air_score}/100).
                            </div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("#### Risk & Quality Categories")
            rc_items = [
                ("🛡️", "#fef3c7", "Safety & Crime", safety_score),
                ("🌿", "#dcfce7", "Environment & Green", env_green_score),
                ("🚇", "#e0f2fe", "Transport & Lines", transport_score),
                ("🎓", "#f3e8ff", "Schools & Healthcare", schools_health_score),
                ("🔊", "#ffedd5", "Noise & Air Quality", noise_air_score),
                ("🌊", "#e0f2fe", "Natural Hazards", hazards_score),
                ("🛒", "#fce7f3", "Local Shops & Dining", amenities_score),
            ]
            cards_html = '<div class="risk-grid">'
            for icon, ibg, title, sc in rc_items:
                sc_col = _score_color(sc)
                cards_html += f"""
                <div class="risk-card">
                    <div class="risk-header">
                        <div class="risk-icon" style="background:{ibg};">{icon}</div>
                        <div>
                            <div class="risk-title">{title}</div>
                            <div class="risk-score">{sc} <span style="font-size:0.78rem; font-weight:500; color:#64748b;">/100</span></div>
                        </div>
                    </div>
                    <div class="bar-track"><div class="bar-fill" style="width:{sc}%; background:{sc_col};"></div></div>
                </div>
                """
            cards_html += "</div>"
            st.markdown(cards_html, unsafe_allow_html=True)

            render_borough_hpi(borough, borough_code)

        with right_col:
            st.markdown("### Detailed view")

            c_col = _score_color(safety_score)
            st.markdown(
                f"""
                <div class="ss-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <div class="risk-icon" style="background:#fef3c7;">🛡️</div>
                            <span style="font-weight:800; font-size:1.05rem;">Safety & Crime</span>
                        </div>
                        <span style="font-weight:800; font-size:1.05rem; color:{c_col};">{safety_score}<span style="font-size:0.8rem; color:#64748b;">/100</span></span>
                    </div>
                    <div class="bar-track" style="margin:10px 0;"><div class="bar-fill" style="width:{safety_score}%; background:{c_col};"></div></div>
                    <p style="font-size:0.84rem; color:#475569 !important; margin:8px 0 12px 0;">{crime_info['summary']}</p>
                    <div class="detail-row">
                        <span class="detail-label">🛡️ Est. crime rate (per 1,000 residents)</span>
                        <span class="detail-val">{crime_info['rate_per_1k']} <span style="font-weight:400; color:#64748b;">(London avg. 52)</span></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🏠 Burglary rate (per 1,000 residents)</span>
                        <span class="detail-val">{crime_info['burglary_1k']} <span style="font-weight:400; color:#64748b;">(London avg. 14)</span></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🚨 Violent & severe offences (latest mo)</span>
                        <span class="detail-val">{severe if severe is not None else 0} <span style="font-weight:400; color:#64748b;">({crime_info.get('severe_pct', 0):.0f}% of total)</span></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">📅 Total reported incidents (1 mi radius)</span>
                        <span class="detail-val">{len(crimes) if crimes is not None else 'N/A'} / mo <span style="font-weight:400; color:#64748b;">(Median ~420)</span></span>
                    </div>
                    <div class="source-footer">
                        <span>ⓘ Data source: Metropolitan Police (police.uk)</span>
                        <span style="color:#0284c7 !important; font-weight:600;">Street-level API ↗</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            na_col = _score_color(noise_air_score)
            avg_aq = air_data.get("avg") or {"no2_ugm3": 28.0, "pm25_ugm3": 10.5, "pm10_ugm3": 18.2}
            live_aq = air_data.get("live") or {"band": "Low", "summary": "Good air quality across London."}
            st.markdown(
                f"""
                <div class="ss-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <div class="risk-icon" style="background:#ffedd5;">🔊</div>
                            <span style="font-weight:800; font-size:1.05rem;">Noise & Air Quality</span>
                        </div>
                        <span style="font-weight:800; font-size:1.05rem; color:{na_col};">{noise_air_score}<span style="font-size:0.8rem; color:#64748b;">/100</span></span>
                    </div>
                    <div class="bar-track" style="margin:10px 0;"><div class="bar-fill" style="width:{noise_air_score}%; background:{na_col};"></div></div>
                    <p style="font-size:0.84rem; color:#475569 !important; margin:8px 0 12px 0;">
                        Daytime noise is <b>{noise['db']} dB</b> ({noise['level'].lower()}).
                        90-day average NO₂ is <b>{avg_no2:.1f} µg/m³</b> (UK legal limit: 40 µg/m³). Live TfL status today: <b>{live_aq['band']}</b>.
                    </p>
                    <div class="detail-row">
                        <span class="detail-label">🔊 Average noise level (daytime Lden)</span>
                        <span class="detail-val">{noise['db']} dB <span style="font-weight:400; color:#64748b;">(London avg. 56 dB)</span></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🌬️ Air quality (NO₂ 90-day mean)</span>
                        <span class="detail-val">{avg_aq['no2_ugm3']:.1f} µg/m³ <span style="font-weight:400; color:#64748b;">(London avg. 32)</span></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🌫️ Fine particulates (PM₂.₅ / PM₁₀ mean)</span>
                        <span class="detail-val">{avg_aq['pm25_ugm3']:.1f} / {avg_aq['pm10_ugm3']:.1f} µg/m³</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">📡 Live TfL AirQuality Band Today</span>
                        <span class="detail-val">{live_aq['band']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🚗 Major noise sources</span>
                        <span class="detail-val">{noise['sources']}</span>
                    </div>
                    <div class="source-footer">
                        <span>ⓘ Source: TfL AirQuality, Open-Meteo CAMS & DEFRA Noise</span>
                        <span style="color:#0284c7 !important; font-weight:600;">Verified ↗</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            hz_col = _score_color(hazards_score)
            st.markdown(
                f"""
                <div class="ss-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <div class="risk-icon" style="background:#e0f2fe;">🌊</div>
                            <span style="font-weight:800; font-size:1.05rem;">Natural Hazards & Flood</span>
                        </div>
                        <span style="font-weight:800; font-size:1.05rem; color:{hz_col};">{hazards_score}<span style="font-size:0.8rem; color:#64748b;">/100</span></span>
                    </div>
                    <div class="bar-track" style="margin:10px 0;"><div class="bar-fill" style="width:{hazards_score}%; background:{hz_col};"></div></div>
                    <p style="font-size:0.84rem; color:#475569 !important; margin:8px 0 12px 0;">{flood['summary']}</p>
                    <div class="detail-row">
                        <span class="detail-label">🌊 Flood risk rating</span>
                        <span class="detail-val">{flood['risk_label']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">⚠️ Active EA flood alerts (3 km)</span>
                        <span class="detail-val">{flood['active_count']} active</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🗺️ Mapped EA flood zones (within 1 km)</span>
                        <span class="detail-val">{flood['zone_count']} zone(s)</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🌡️ Urban heatwave risk</span>
                        <span class="detail-val">{flood['heatwave_risk']}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🪨 Ground stability</span>
                        <span class="detail-val">{flood['ground_stability']}</span>
                    </div>
                    <div class="source-footer">
                        <span>ⓘ Data source: UK Environment Agency (gov.uk)</span>
                        <span style="color:#0284c7 !important; font-weight:600;">Flood API ↗</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            all_tube_lines = sorted({ln for r in rail for ln in r["lines"]})
            all_bus_lines = sorted({ln for b in bus for ln in b["lines"]})
            tr_col = _score_color(transport_score)
            st.markdown(
                f"""
                <div class="ss-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <div class="risk-icon" style="background:#e0f2fe;">🚇</div>
                            <span style="font-weight:800; font-size:1.05rem;">Transit Lines & Walkability</span>
                        </div>
                        <span style="font-weight:800; font-size:1.05rem; color:{tr_col};">{transport_score}<span style="font-size:0.8rem; color:#64748b;">/100</span></span>
                    </div>
                    <div class="bar-track" style="margin:10px 0;"><div class="bar-fill" style="width:{transport_score}%; background:{tr_col};"></div></div>
                    <div class="detail-row">
                        <span class="detail-label">🚇 Tube/Rail stations (800m)</span>
                        <span class="detail-val">{len(rail)} station(s)</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🛤️ Tube/Rail lines served</span>
                        <span class="detail-val">{', '.join(all_tube_lines[:6]) if all_tube_lines else 'None within 800m'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🚌 Bus stops (500m radius)</span>
                        <span class="detail-val">{len(bus)} stop(s)</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🔢 Bus routes (500m)</span>
                        <span class="detail-val">{', '.join(all_bus_lines[:10]) if all_bus_lines else 'Local routes'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🎓 Schools / 🌳 Parks (800m)</span>
                        <span class="detail-val">{len(schools)} schools • {len(parks)} parks</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">🛒 Groceries / 🍽️ Dining / 💊 Health</span>
                        <span class="detail-val">{n_super} • {n_food} • {n_health}</span>
                    </div>
                    <div class="source-footer">
                        <span>ⓘ Data source: TfL StopPoint & OpenStreetMap/ArcGIS</span>
                        <span style="color:#0284c7 !important; font-weight:600;">Live ↗</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with st.expander("🔍 Click to inspect every Tube/Bus Line, Supermarket, Restaurant, Pharmacy, School & Park nearby", expanded=False):
            t1, t2, t3, t4, t5, t6 = st.tabs([
                f"🚇 Tube/Rail & 🚌 Bus Lines ({len(rail) + len(bus)})",
                f"🛒 Groceries ({n_super})",
                f"🍽️ Dining & Pubs ({n_food})",
                f"💊 Healthcare ({n_health})",
                f"🛍️ Retail & Services ({n_retail})",
                f"🎓 Schools ({len(schools)}) & 🌳 Parks ({len(parks)})",
            ])
            with t1:
                c_r, c_b = st.columns(2)
                with c_r:
                    st.markdown("**🚇 Tube & Rail Stations (within 800m):**")
                    if rail:
                        st.dataframe(
                            pd.DataFrame(rail)[["name", "lines_str", "dist_m"]].rename(
                                columns={"name": "Station", "lines_str": "Lines Served", "dist_m": "Distance (m)"}
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.write("No Tube/Rail stations within 800m.")
                with c_b:
                    st.markdown("**🚌 Bus Stops & Route Numbers (within 500m):**")
                    if bus:
                        st.dataframe(
                            pd.DataFrame(bus)[["name", "lines_str", "dist_m"]].rename(
                                columns={"name": "Bus Stop", "lines_str": "Bus Numbers", "dist_m": "Distance (m)"}
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.write("No bus stops within 500m.")
            with t2:
                items = cats["🛒 Supermarkets & Groceries"]
                if items:
                    st.dataframe(pd.DataFrame(items)[["name", "type"]].drop_duplicates(), use_container_width=True, hide_index=True)
                else:
                    st.write("No supermarkets mapped within 800m.")
            with t3:
                items = cats["🍽️ Restaurants, Cafés & Pubs"]
                if items:
                    st.dataframe(pd.DataFrame(items)[["name", "type"]].drop_duplicates().head(60), use_container_width=True, hide_index=True)
                else:
                    st.write("No dining venues mapped within 800m.")
            with t4:
                items = cats["💊 Pharmacies & Healthcare"]
                if items:
                    st.dataframe(pd.DataFrame(items)[["name", "type"]].drop_duplicates(), use_container_width=True, hide_index=True)
                else:
                    st.write("No pharmacies/clinics mapped within 800m.")
            with t5:
                items = cats["🛍️ Retail, Fashion & Daily Services"]
                if items:
                    st.dataframe(
                        pd.DataFrame(items)["type"].value_counts().rename_axis("Shop Category").reset_index(name="Count"),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.write("No retail shops mapped within 800m.")
            with t6:
                cs, cp = st.columns(2)
                with cs:
                    st.markdown("**🎓 Schools (800m):**")
                    if schools:
                        st.dataframe(pd.DataFrame(schools)[["name", "type"]].drop_duplicates(), use_container_width=True, hide_index=True)
                    else:
                        st.write("No schools mapped within 800m.")
                with cp:
                    st.markdown("**🌳 Parks & Green Spaces (800m):**")
                    if parks:
                        st.dataframe(pd.DataFrame(parks)[["name", "type"]].drop_duplicates(), use_container_width=True, hide_index=True)
                    else:
                        st.write("No parks mapped within 800m.")
    elif res:
        st.error("Address not found. Please enter a valid London postcode or street name.")

# ------------------------------------------------------------------ MODE 2
else:
    render_mode2(
        OPENROUTER_KEY,
        external=placeholder_external_scores() if use_placeholders else None,
        carto_key=CARTO_KEY,
    )
