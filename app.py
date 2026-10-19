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

st.set_page_config(page_title="SafeSite London", page_icon="🏡", layout="wide")

# ------------------------------------------------------------------ High-Contrast Bright UI CSS (No white-on-white)
st.markdown(
    """
    <style>
    /* Force high-contrast dark text on bright backgrounds across light & dark OS themes */
    .stApp {
        background: linear-gradient(180deg, #f0f9ff 0%, #f8fafc 100%) !important;
        color: #0f172a !important;
    }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp label, .stApp span, .stMarkdown {
        color: #0f172a;
    }
    /* Sidebar styling: deep ocean blue with crisp white text */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e3a8a 100%) !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div {
        color: #f8fafc !important;
    }
    /* Metric cards: white background, explicit dark text */
    div[data-testid="stMetric"] {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-left: 5px solid #0284c7 !important;
        border-radius: 12px !important;
        padding: 14px 16px !important;
        box-shadow: 0 4px 10px rgba(15, 23, 42, 0.06) !important;
    }
    div[data-testid="stMetricLabel"] * {
        color: #334155 !important;
        font-weight: 600 !important;
    }
    div[data-testid="stMetricValue"] * {
        color: #0f172a !important;
        font-weight: 800 !important;
    }
    /* Hero Banner */
    .hero-banner {
        background: linear-gradient(135deg, #0369a1 0%, #0d9488 100%);
        padding: 22px 26px;
        border-radius: 16px;
        margin-bottom: 18px;
        box-shadow: 0 8px 20px rgba(3, 105, 161, 0.18);
    }
    .hero-banner h2, .hero-banner p {
        color: #ffffff !important;
        margin: 0;
    }
    /* Info Cards */
    .info-card {
        background: #ffffff !important;
        color: #0f172a !important;
        border-radius: 14px;
        padding: 18px 20px;
        border: 1px solid #cbd5e1;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
        margin-bottom: 14px;
    }
    .info-card * {
        color: #0f172a;
    }
    .badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    /* Expander header contrast */
    details summary {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border-radius: 8px;
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


OPENROUTER_KEY = secret("OPENROUTER_KEY", "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")
CARTO_KEY = secret("CARTO_KEY", "cb1_4iwc_1_bce17659066bca4d710f938b")

# ------------------------------------------------------------------ Sidebar
st.sidebar.markdown("## 🏡 SafeSite London")
st.sidebar.caption("Interactive Property & Risk Intelligence")
mode = st.sidebar.radio(
    "Choose Your Workflow:",
    ["📍 Address Analysis & Diligence", "🧭 Borough Finder & Shortlist"],
)

if mode == "🧭 Borough Finder & Shortlist":
    use_placeholders = st.sidebar.checkbox(
        "Include Borough Safety / Transport / Flood Scores",
        value=True,
        help="Connects borough-level safety, transport, and flood scores so your priority checkboxes rank all 33 boroughs.",
    )
else:
    use_placeholders = False

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Connected Official APIs:**\n"
    "- 💷 HM Land Registry UK HPI\n"
    "- 🌬️ TfL + Open-Meteo Air Quality\n"
    "- 🌊 Environment Agency Flood API\n"
    "- 🚇 TfL StopPoints (500m / 800m)\n"
    "- 🛡️ UK Police Street Crime\n"
    "- 🗺️ OpenStreetMap Amenities"
)


# ------------------------------------------------------------------ Helpers & Data Fetchers
def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@st.cache_data(ttl=3600)
def geocode_and_resolve_borough(address):
    geolocator = Nominatim(user_agent="safesite_london_analyst_v5")
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
        return crimes, sum(1 for c in crimes if c.get("category") in severe)
    raise RuntimeError(f"Police API status {res.status_code}")


def fetch_police_crime_data(lat, lon):
    try:
        return _cached_police(lat, lon)
    except Exception:
        return None, None


def interpret_crime_level(total_crimes: int | None, severe_crimes: int | None) -> dict:
    if total_crimes is None:
        return {
            "label": "Unavailable",
            "color": "#475569",
            "bg": "#e2e8f0",
            "pct_bar": 0,
            "summary": "Police.uk API did not respond in time.",
        }
    if total_crimes < 220:
        label, color, bg = "Low Crime (Quiet Residential)", "#15803d", "#dcfce7"
        comp = f"{int((1 - total_crimes / 420) * 100)}% below the typical London neighbourhood (~420/mo)"
    elif total_crimes < 450:
        label, color, bg = "Moderate / Typical London", "#0369a1", "#e0f2fe"
        comp = "In line with the Greater London residential median (~420/mo)"
    elif total_crimes < 750:
        label, color, bg = "Elevated (Busy High Street / Hub)", "#b45309", "#fef3c7"
        comp = f"{total_crimes / 420:.1f}x the London residential median — typical of lively shopping/station areas"
    else:
        label, color, bg = "High Volume (Central / Nightlife Hub)", "#b91c1c", "#fee2e2"
        comp = (
            f"{total_crimes / 420:.1f}x the residential average — driven by high daily footfall, "
            "tourists, and retail/nightlife density"
        )

    per_day = total_crimes / 30.0
    severe_pct = (severe_crimes / total_crimes * 100) if total_crimes and severe_crimes is not None else 0
    pct_bar = min(100, int((total_crimes / 1000) * 100))
    return {
        "label": label,
        "color": color,
        "bg": bg,
        "pct_bar": pct_bar,
        "per_day": per_day,
        "severe_pct": severe_pct,
        "summary": comp,
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
        rail = [
            s for s in stops
            if any(t in s.get("stopType", "") for t in ["Metro", "Rail"])
            and _haversine_m(lat, lon, s.get("lat", lat), s.get("lon", lon)) <= rail_radius
        ]
        bus = [
            s for s in stops
            if "Bus" in s.get("stopType", "")
            and _haversine_m(lat, lon, s.get("lat", lat), s.get("lon", lon)) <= bus_radius
        ]
        return rail, bus
    raise RuntimeError(f"TfL API status {res.status_code}")


def fetch_tfl_nearby_stops(lat, lon):
    try:
        return _cached_tfl(lat, lon, rail_radius=800, bus_radius=500)
    except Exception:
        return None, None


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_air_quality(lat, lon):
    out = {"live": None, "avg": None}
    # 1. Live TfL AirQuality API
    try:
        res = requests.get("https://api.tfl.gov.uk/AirQuality", timeout=10)
        if res.status_code == 200:
            data = res.json()
            forecasts = data.get("currentForecast") or []
            curr = next((f for f in forecasts if f.get("forecastType") == "Current"), forecasts[0] if forecasts else {})
            raw_text = html.unescape(curr.get("forecastText", ""))
            clean_text = re.sub(r"<br\s*/?>", "\n", raw_text)
            clean_text = re.sub(r"<[^>]+>", "", clean_text).strip()
            out["live"] = {
                "band": curr.get("forecastBand", "Unknown"),
                "summary": curr.get("forecastSummary", "No summary available."),
                "text": clean_text,
                "no2": curr.get("nO2Band", "N/A"),
                "o3": curr.get("o3Band", "N/A"),
                "pm10": curr.get("pM10Band", "N/A"),
                "pm25": curr.get("pM25Band", "N/A"),
            }
    except Exception:
        pass

    # 2. Local 90-Day Average Pollution at exact coordinates (Open-Meteo CAMS European Air Quality API)
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
            s_o3 = pd.Series(h.get("ozone", []), dtype="float64").dropna()
            s_aqi = pd.Series(h.get("european_aqi", []), dtype="float64").dropna()
            if len(s_no2) > 0:
                avg_no2 = float(s_no2.mean())
                avg_pm25 = float(s_pm25.mean())
                avg_pm10 = float(s_pm10.mean())
                avg_o3 = float(s_o3.mean())
                avg_aqi = float(s_aqi.mean()) if len(s_aqi) else 0.0
                # UK Legal Annual Limits: NO2 = 40 ug/m3, PM2.5 = 20 ug/m3, PM10 = 40 ug/m3
                if avg_no2 < 22 and avg_pm25 < 10:
                    rating, color, bg = "Clean / Low Average Pollution", "#15803d", "#dcfce7"
                elif avg_no2 <= 32 and avg_pm25 <= 14:
                    rating, color, bg = "Moderate Urban Average (Within UK Legal Limits)", "#0369a1", "#e0f2fe"
                elif avg_no2 <= 40:
                    rating, color, bg = "Elevated Roadside/Urban Pollution (Near 40 µg/m³ NO₂ limit)", "#b45309", "#fef3c7"
                else:
                    rating, color, bg = "High Average Pollution (Exceeds 40 µg/m³ UK NO₂ Limit)", "#b91c1c", "#fee2e2"

                out["avg"] = {
                    "no2_ugm3": avg_no2,
                    "pm25_ugm3": avg_pm25,
                    "pm10_ugm3": avg_pm10,
                    "o3_ugm3": avg_o3,
                    "eaqi": avg_aqi,
                    "rating": rating,
                    "color": color,
                    "bg": bg,
                }
    except Exception:
        pass

    if not out["live"] and not out["avg"]:
        raise RuntimeError("Air quality APIs unavailable")
    return out


def fetch_air_quality_complete(lat, lon):
    try:
        return _cached_air_quality(lat, lon)
    except Exception:
        return {"live": None, "avg": None}


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_flood_risk(lat, lon):
    # UK Environment Agency Real-Time Flood Monitoring API
    # 1. Active warnings/alerts within 3 km
    r_warn = requests.get(
        f"https://environment.data.gov.uk/flood-monitoring/id/floods?lat={lat}&long={lon}&dist=3",
        timeout=10,
    )
    # 2. Mapped EA Flood Risk Zones (Flood Areas) within 1 km
    r_areas = requests.get(
        f"https://environment.data.gov.uk/flood-monitoring/id/floodAreas?lat={lat}&long={lon}&dist=1",
        timeout=10,
    )
    # 3. Nearby River / Tidal Level Monitoring Stations within 2 km
    r_stat = requests.get(
        f"https://environment.data.gov.uk/flood-monitoring/id/stations?lat={lat}&long={lon}&dist=2",
        timeout=10,
    )

    warnings = r_warn.json().get("items", []) if r_warn.status_code == 200 else []
    areas = r_areas.json().get("items", []) if r_areas.status_code == 200 else []
    stations = r_stat.json().get("items", []) if r_stat.status_code == 200 else []

    active_warnings = [w for w in warnings if w.get("severityLevel", 4) <= 3]
    rivers = sorted({a.get("riverOrSea", "") for a in areas if a.get("riverOrSea")})

    if active_warnings:
        level = "Active Flood Alert / Warning Nearby"
        color, bg = "#b91c1c", "#fee2e2"
        desc = f"{len(active_warnings)} active Environment Agency alert(s) within 3 km."
    elif len(areas) == 0:
        level = "Very Low Flood Risk (Outside EA 1 km Floodplain Zones)"
        color, bg = "#15803d", "#dcfce7"
        desc = "No Environment Agency Flood Warning Areas within 1 km of this address."
    elif len(areas) <= 2:
        level = "Low–Moderate Flood Exposure (Near Monitored Watercourse)"
        color, bg = "#0369a1", "#e0f2fe"
        desc = f"Within 1 km of {len(areas)} mapped EA flood zone(s) ({', '.join(rivers) or 'local watercourse'}), but 0 active warnings."
    else:
        level = "Elevated Flood Zone Proximity (Tidal / Fluvial Catchment)"
        color, bg = "#b45309", "#fef3c7"
        desc = (
            f"Overlaps {len(areas)} EA flood monitoring zones within 1 km "
            f"({', '.join(rivers[:3]) or 'Thames / local catchment'}). Check property-specific surface water & Thames Barrier coverage."
        )

    return {
        "level": level,
        "color": color,
        "bg": bg,
        "desc": desc,
        "active_count": len(active_warnings),
        "zone_count": len(areas),
        "station_count": len(stations),
        "zones": [a.get("label", "Flood Zone") for a in areas[:6]],
        "stations": [s.get("label", "Station") for s in stations[:6]],
    }


def fetch_flood_risk(lat, lon):
    try:
        return _cached_flood_risk(lat, lon)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_osm(lat, lon, radius=800):
    # Bounding-box query is 10x faster than 'around:' on Overpass and prevents timeouts
    dlat = radius / 111320.0
    dlon = radius / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    s, w, n, e = lat - dlat, lon - dlon, lat + dlat, lon + dlon

    query = f"""
    [out:json][timeout:18];
    (
      nwr["amenity"="school"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      nwr["leisure"~"^(park|garden|nature_reserve)$"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["shop"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
      node["amenity"~"^(restaurant|cafe|pub|fast_food|supermarket|pharmacy|bank|clinic|doctors|dentist|post_office|library|gym)$"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});
    );
    out center qt;
    """
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]
    headers = {"User-Agent": "SafeSiteLondon/5.0 (https://streamlit.io)"}

    for url in endpoints:
        try:
            res = requests.post(url, data={"data": query}, headers=headers, timeout=18)
            if res.status_code == 200:
                els = res.json().get("elements", [])
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
                        schools.append({"lat": c_lat, "lon": c_lon, "name": name or "School", "type": "School"})
                    elif le in ("park", "garden", "nature_reserve"):
                        parks.append({"lat": c_lat, "lon": c_lon, "name": name or "Park / Garden", "type": le.title()})
                    elif sh in ("supermarket", "convenience", "greengrocer", "bakery", "butcher", "deli") or am == "supermarket":
                        subtype = (sh or am).replace("_", " ").title()
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
                    elif sh or am:
                        subtype = (sh or am).replace("_", " ").title()
                        cat_items["🛍️ Retail, Fashion & Daily Services"].append(
                            {"lat": c_lat, "lon": c_lon, "name": name or subtype, "type": subtype}
                        )

                return {"schools": schools, "parks": parks, "categories": cat_items}
        except Exception:
            continue

    raise RuntimeError("All Overpass mirrors timed out")


def fetch_osm_infrastructure(lat, lon, radius=800):
    try:
        return _cached_osm(lat, lon, radius)
    except Exception:
        return None


# ------------------------------------------------------------------ MODE 1
if mode == "📍 Address Analysis & Diligence":
    st.markdown(
        """
        <div class="hero-banner">
            <h2>📍 Street-Level Property & Risk Diligence</h2>
            <p style="margin-top:6px;">
                Audit any London street or postcode for 25th–75th percentile borough prices, 90-day average & live air pollution,
                Environment Agency flood risk, transit (500m bus / 800m rail), clickable local amenities, and street crime benchmarks.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("💡 What can this Address Audit do? (Model & Data Capabilities)", expanded=False):
        st.markdown(
            """
            * **💷 Price Range & Trend (HM Land Registry):** Shows both the **average price** and the **25%–75% typical market range** in the borough, plus 1, 5, and 10-year growth rates.
            * **🌬️ Average + Live Air Quality (Open-Meteo CAMS + TfL AirQuality):** Combines **90-day average pollutant concentrations ($\mu\\text{g/m}^3$)** against WHO/UK limits with **TfL's live daily pollution band**.
            * **🌊 Flood Risk Assessment (Environment Agency API):** Checks mapped EA Flood Risk Zones within 1 km, active flood alerts within 3 km, and nearby river/tidal gauges.
            * **🛒 Clickable Local Amenities & Transit:** Counts **Bus stops within 500m**, **Tube/Rail, Parks, and Schools within 800m**, and breaks down local businesses into **Supermarkets, Restaurants/Cafés, Healthcare, and Retail** (click the expander to inspect every category).
            * **🛡️ Contextualized Street Crime:** Benchmarks local monthly incidents against the Greater London residential median (~420/month).
            """
        )

    with st.form("search_form"):
        c1, c2 = st.columns([4, 1])
        address_query = c1.text_input("🔍 Enter a London Street, Landmark, or Postcode", "Marylebone High Street")
        submit = c2.form_submit_button("🚀 Run Full Audit", use_container_width=True)

    if submit or "audit_results" not in st.session_state:
        st.session_state.audit_results = geocode_and_resolve_borough(address_query)

    res = st.session_state.get("audit_results")
    if res and res[0] is not None:
        lat, lon, full_address, borough, borough_code = res
        st.success(f"**Target Borough:** {borough}  |  **Resolved Location:** {full_address}")

        with st.spinner("Auditing HM Land Registry, Air Quality (Average & Live), Environment Agency Flood Zones, TfL & OpenStreetMap..."):
            crimes, severe = fetch_police_crime_data(lat, lon)
            rail, bus = fetch_tfl_nearby_stops(lat, lon)
            air_data = fetch_air_quality_complete(lat, lon)
            flood = fetch_flood_risk(lat, lon)
            osm = fetch_osm_infrastructure(lat, lon)

        # 1. Borough HPI with 25-75% range
        render_borough_hpi(borough, borough_code)
        st.write("---")

        # 2. Average + Live Air Quality
        st.subheader("🌬️ Air Pollution: 90-Day Local Average & Live TfL Forecast")
        avg_aq = air_data.get("avg")
        live_aq = air_data.get("live")

        col_aq1, col_aq2 = st.columns(2)
        with col_aq1:
            if avg_aq:
                st.markdown(
                    f"""
                    <div class="info-card" style="border-left: 6px solid {avg_aq['color']}; background:{avg_aq['bg']} !important;">
                        <div style="font-size:1.05rem; font-weight:800; color:{avg_aq['color']} !important;">
                            📊 90-Day Local Average: {avg_aq['rating']}
                        </div>
                        <div style="margin-top:6px; font-size:0.9rem; color:#1e293b !important;">
                            Benchmarked against UK Legal Annual Limits (NO₂: 40 µg/m³, PM₂.₅: 20 µg/m³, PM₁₀: 40 µg/m³).
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                m_aq = st.columns(4)
                m_aq[0].metric("Avg NO₂", f"{avg_aq['no2_ugm3']:.1f} µg/m³", "Limit: 40", delta_color="off")
                m_aq[1].metric("Avg PM₂.₅", f"{avg_aq['pm25_ugm3']:.1f} µg/m³", "Limit: 20", delta_color="off")
                m_aq[2].metric("Avg PM₁₀", f"{avg_aq['pm10_ugm3']:.1f} µg/m³", "Limit: 40", delta_color="off")
                m_aq[3].metric("Avg Euro AQI", f"{avg_aq['eaqi']:.0f}", "Lower = cleaner", delta_color="off")
            else:
                st.info("Historical average air quality unavailable.")

        with col_aq2:
            if live_aq:
                band = live_aq["band"]
                band_colors = {
                    "Low": ("#15803d", "#dcfce7", "🟢 Live TfL Status: Low Pollution Today"),
                    "Moderate": ("#b45309", "#fef3c7", "🟡 Live TfL Status: Moderate Pollution Today"),
                    "High": ("#b91c1c", "#fee2e2", "🔴 Live TfL Status: High Pollution Alert Today"),
                }
                fg, bg, desc = band_colors.get(band, ("#0369a1", "#e0f2fe", f"Live TfL Band: {band}"))
                st.markdown(
                    f"""
                    <div class="info-card" style="border-left: 6px solid {fg}; background:{bg} !important;">
                        <div style="font-size:1.05rem; font-weight:800; color:{fg} !important;">{desc}</div>
                        <div style="margin-top:6px; font-size:0.9rem; color:#1e293b !important;">{live_aq['summary']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                l_aq = st.columns(4)
                l_aq[0].metric("Today NO₂", live_aq["no2"])
                l_aq[1].metric("Today PM₂.₅", live_aq["pm25"])
                l_aq[2].metric("Today PM₁₀", live_aq["pm10"])
                l_aq[3].metric("Today O₃", live_aq["o3"])
            else:
                st.info("Live TfL AirQuality feed temporarily unavailable.")

        st.write("---")

        # 3. Environment Agency Flood Risk Assessment
        st.subheader("🌊 Flood Risk & Catchment Analysis (UK Environment Agency)")
        if flood:
            st.markdown(
                f"""
                <div class="info-card" style="border-left: 6px solid {flood['color']}; background:{flood['bg']} !important;">
                    <div style="font-size:1.05rem; font-weight:800; color:{flood['color']} !important;">
                        {flood['level']}
                    </div>
                    <div style="margin-top:6px; color:#1e293b !important;">{flood['desc']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            f_cols = st.columns(3)
            f_cols[0].metric("Active Flood Alerts (3 km)", flood["active_count"])
            f_cols[1].metric("Mapped EA Flood Zones (1 km)", flood["zone_count"])
            f_cols[2].metric("River / Tide Gauges (2 km)", flood["station_count"])
            if flood["zones"] or flood["stations"]:
                with st.expander("🔍 View nearby Environment Agency flood zones & monitoring stations"):
                    if flood["zones"]:
                        st.write("**Mapped Flood Zones (within 1 km):** " + " • ".join(flood["zones"]))
                    if flood["stations"]:
                        st.write("**Water Level Monitoring Stations (within 2 km):** " + " • ".join(flood["stations"]))
        else:
            st.info("Environment Agency Flood Monitoring API temporarily unavailable.")

        st.write("---")

        # 4. Walkability, Schools, Parks & Categorized Amenities (with Clickable Expander)
        st.subheader("🚇 Walkability, Schools, Parks & Local Amenities")
        schools = osm["schools"] if osm else None
        parks = osm["parks"] if osm else None
        cats = osm["categories"] if osm else {}

        n_super = len(cats.get("🛒 Supermarkets & Groceries", [])) if osm else None
        n_food = len(cats.get("🍽️ Restaurants, Cafés & Pubs", [])) if osm else None
        n_health = len(cats.get("💊 Pharmacies & Healthcare", [])) if osm else None
        n_retail = len(cats.get("🛍️ Retail, Fashion & Daily Services", [])) if osm else None

        i = st.columns(6)
        i[0].metric("🚇 Tube & Rail (800m)", len(rail) if rail is not None else "N/A")
        i[1].metric("🚌 Bus Stops (500m)", len(bus) if bus is not None else "N/A")
        i[2].metric("🌳 Parks & Gardens (800m)", len(parks) if parks is not None else "N/A")
        i[3].metric("🏫 Schools (800m)", len(schools) if schools is not None else "N/A")
        i[4].metric("🛒 Supermarkets (800m)", n_super if n_super is not None else "N/A")
        i[5].metric("🍽️ Dining & Cafés (800m)", n_food if n_food is not None else "N/A")

        if osm:
            with st.expander("🔍 Click to explore all Shops, Supermarkets, Restaurants, Healthcare, Schools & Parks (800m)", expanded=False):
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    f"🛒 Groceries ({n_super})",
                    f"🍽️ Dining & Pubs ({n_food})",
                    f"💊 Healthcare ({n_health})",
                    f"🛍️ Retail & Services ({n_retail})",
                    f"🏫 Schools ({len(schools)}) & 🌳 Parks ({len(parks)})",
                ])
                with tab1:
                    items = cats.get("🛒 Supermarkets & Groceries", [])
                    if items:
                        df_g = pd.DataFrame(items)[["name", "type"]].value_counts().reset_index(name="Count")
                        df_g.columns = ["Name", "Type", "Locations"]
                        st.dataframe(df_g, use_container_width=True, hide_index=True)
                    else:
                        st.write("No supermarkets or grocery stores mapped within 800m.")
                with tab2:
                    items = cats.get("🍽️ Restaurants, Cafés & Pubs", [])
                    if items:
                        c_a, c_b = st.columns([1, 2])
                        with c_a:
                            st.write("**By Venue Type:**")
                            st.dataframe(
                                pd.DataFrame(items)["type"].value_counts().rename_axis("Venue Type").reset_index(name="Count"),
                                use_container_width=True,
                                hide_index=True,
                            )
                        with c_b:
                            st.write("**Named Venues (Sample):**")
                            named = [x for x in items if x["name"] != x["type"]]
                            st.dataframe(
                                pd.DataFrame(named or items)[["name", "type"]].drop_duplicates().head(40).rename(columns={"name": "Venue Name", "type": "Category"}),
                                use_container_width=True,
                                hide_index=True,
                            )
                    else:
                        st.write("No restaurants or cafés mapped within 800m.")
                with tab3:
                    items = cats.get("💊 Pharmacies & Healthcare", [])
                    if items:
                        st.dataframe(
                            pd.DataFrame(items)[["name", "type"]].drop_duplicates().rename(columns={"name": "Facility Name", "type": "Category"}),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.write("No pharmacies or clinics mapped within 800m.")
                with tab4:
                    items = cats.get("🛍️ Retail, Fashion & Daily Services", [])
                    if items:
                        st.write("**Breakdown by Shop / Service Type:**")
                        st.dataframe(
                            pd.DataFrame(items)["type"].value_counts().rename_axis("Shop / Service Type").reset_index(name="Count"),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.write("No retail shops mapped within 800m.")
                with tab5:
                    col_s, col_p = st.columns(2)
                    with col_s:
                        st.write("**Schools (800m):**")
                        if schools:
                            st.dataframe(pd.DataFrame(schools)[["name"]].drop_duplicates().rename(columns={"name": "School Name"}), use_container_width=True, hide_index=True)
                        else:
                            st.write("None mapped within 800m.")
                    with col_p:
                        st.write("**Parks & Gardens (800m):**")
                        if parks:
                            st.dataframe(pd.DataFrame(parks)[["name", "type"]].drop_duplicates().rename(columns={"name": "Green Space", "type": "Type"}), use_container_width=True, hide_index=True)
                        else:
                            st.write("None mapped within 800m.")

        st.write("---")

        # 5. Easy-to-understand Street Crime Benchmark
        st.subheader("🛡️ Street-Level Safety & Crime Context (~1 mile radius, latest month)")
        crime_info = interpret_crime_level(len(crimes) if crimes is not None else None, severe)

        st.markdown(
            f"""
            <div class="info-card" style="border-left: 6px solid {crime_info['color']};">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
                    <div>
                        <span class="badge" style="background:{crime_info['bg']}; color:{crime_info['color']} !important;">
                            {crime_info['label']}
                        </span>
                        <h4 style="margin:8px 0 4px 0; color:#0f172a !important;">{crime_info['summary']}</h4>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:0.85rem; color:#334155 !important;">London Scale (0 = Quietest, 1000+ = West End)</span>
                    </div>
                </div>
                <div style="background:#cbd5e1; border-radius:999px; height:12px; width:100%; margin-top:10px; overflow:hidden;">
                    <div style="background:{crime_info['color']}; width:{crime_info['pct_bar']}%; height:100%;"></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        k = st.columns(4)
        k[0].metric("Total Monthly Incidents", f"{len(crimes):,}" if crimes is not None else "N/A")
        k[1].metric("Daily Average (within 1 mi)", f"{crime_info.get('per_day', 0):.1f} / day" if crimes is not None else "N/A")
        k[2].metric(
            "Violent / Burglary / Robbery",
            f"{severe:,} ({crime_info.get('severe_pct', 0):.0f}%)" if severe is not None else "N/A",
        )
        k[3].metric("London Residential Benchmark", "~420 / mo")

        col_map, col_tbl = st.columns([3, 2])
        with col_map:
            if CARTO_KEY:
                m = folium.Map(location=[lat, lon], zoom_start=15, tiles=None)
                folium.TileLayer(
                    tiles=f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}",
                    attr="CARTO",
                    name="CARTO",
                ).add_to(m)
            else:
                m = folium.Map(location=[lat, lon], zoom_start=15, tiles="OpenStreetMap")

            folium.Marker([lat, lon], popup="Target Address", icon=folium.Icon(color="red", icon="home")).add_to(m)
            folium.Circle(
                radius=800, location=[lat, lon], color="#0284c7", weight=2, fill=True, fill_opacity=0.05, popup="800m Radius"
            ).add_to(m)
            folium.Circle(
                radius=500,
                location=[lat, lon],
                color="#d97706",
                weight=2,
                dash_array="5, 5",
                fill=False,
                popup="500m Bus Radius",
            ).add_to(m)

            for p in parks or []:
                folium.CircleMarker([p["lat"], p["lon"]], radius=5, color="#16a34a", fill=True, popup=p["name"]).add_to(m)
            for s in schools or []:
                folium.CircleMarker([s["lat"], s["lon"]], radius=4, color="#9333ea", fill=True, popup=s["name"]).add_to(m)
            for r in rail or []:
                folium.CircleMarker([r["lat"], r["lon"]], radius=6, color="#1e40af", fill=True, popup=r.get("commonName", "Tube/Rail")).add_to(m)
            for b in bus or []:
                folium.CircleMarker([b["lat"], b["lon"]], radius=3, color="#d97706", fill=True, popup=b.get("commonName", "Bus Stop")).add_to(m)

            components.html(m.get_root().render(), height=480)
            st.caption("🔴 Target | 🔵 Tube/Rail (800m) | 🟠 Bus Stops (500m dashed ring) | 🟢 Parks | 🟣 Schools")

        with col_tbl:
            if crimes:
                df = pd.DataFrame(crimes)["category"].value_counts().reset_index()
                df.columns = ["Incident Category", "Monthly Count"]
                df["Share (%)"] = (df["Monthly Count"] / len(crimes) * 100).round(1)
                st.dataframe(df, use_container_width=True, hide_index=True, height=450)
            elif crimes is None:
                st.error("Crime data unavailable (Police.uk API timeout or error).")
            else:
                st.info("No incidents recorded in the latest available month.")
    elif res:
        st.error("Address not found. Please try a London postcode or street name.")

# ------------------------------------------------------------------ MODE 2
else:
    render_mode2(
        OPENROUTER_KEY,
        external=placeholder_external_scores() if use_placeholders else None,
        carto_key=CARTO_KEY,
    )