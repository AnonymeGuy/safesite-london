import json
import re

import folium
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

import scoring_engine as se


# ---------------------------------------------------------------- PART A
@st.cache_data(ttl=24 * 3600, show_spinner="Loading UK HPI (HM Land Registry)...")
def get_hpi():
    df, source = se.load_ukhpi_london()
    return df, source


@st.cache_data(ttl=7 * 24 * 3600)
def load_london_geojson():
    url = "[https://raw.githubusercontent.com/radoi90/housequest-data/master/london_boroughs.geojson](https://raw.githubusercontent.com/radoi90/housequest-data/master/london_boroughs.geojson)"
    try:
        return requests.get(url, timeout=10).json()
    except Exception:
        return None


# ---------------------------------------------------------------- PART B (Mode 1 — Responsive Price Cards)
def render_borough_hpi(borough: str, borough_code: str | None, property_type: str = "any"):
    try:
        hpi, source = get_hpi()
    except se.HPIUnavailable as e:
        st.warning(f"Price data unavailable: {e}")
        return
    row, series, med = se.borough_snapshot(hpi, borough_code, borough, property_type)
    if row is None:
        st.warning(f"No HPI match for '{borough}'.")
        return

    st.markdown(f"#### 💷 Borough Property Pricing & 25%–75% Range ({row['Borough']})")

    d1 = (row["cagr_1y"] - med["cagr_1y"]) * 100
    d5 = (row["cagr_5y"] - med["cagr_5y"]) * 100
    d10 = (row["cagr_10y"] - med["cagr_10y"]) * 100

    st.markdown(
        f'<div class="kpi-grid">'
        f'<div class="kpi-box"><div class="kpi-label">Average Price</div><div class="kpi-value">£{row["latest_price"]:,.0f}</div><div class="kpi-sub">Borough mean ({row["latest_date"]:%b %Y})</div></div>'
        f'<div class="kpi-box" style="border-left-color:#10b981;"><div class="kpi-label">25%–75% Typical Range</div><div class="kpi-value">£{row["p25_price"]/1000:,.0f}k – £{row["p75_price"]/1000:,.0f}k</div><div class="kpi-sub">Entry to upper quartile</div></div>'
        f'<div class="kpi-box" style="border-left-color:#6366f1;"><div class="kpi-label">1-Yr Growth</div><div class="kpi-value">{row["cagr_1y"]:.1%}</div><div class="kpi-sub">{d1:+.1f} pts vs London median</div></div>'
        f'<div class="kpi-box" style="border-left-color:#f59e0b;"><div class="kpi-label">5-Yr Growth / yr</div><div class="kpi-value">{row["cagr_5y"]:.1%}</div><div class="kpi-sub">{d5:+.1f} pts vs London median</div></div>'
        f'<div class="kpi-box" style="border-left-color:#0d9488;"><div class="kpi-label">10-Yr Growth / yr</div><div class="kpi-value">{row["cagr_10y"]:.1%}</div><div class="kpi-sub">{d10:+.1f} pts vs London median</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    chart_df = pd.DataFrame(
        {
            "25th Percentile (£)": series * (row["p25_price"] / row["latest_price"]),
            "Average Price (£)": series,
            "75th Percentile (£)": series * (row["p75_price"] / row["latest_price"]),
        }
    )
    st.line_chart(chart_df, color=["#93c5fd", "#0284c7", "#10b981"], height=240)


# ---------------------------------------------------------------- PART C (Mode 2 — Dynamic Multi-Factor + Smart Context Engine)
ALL_WEIGHT_KEYS = [
    "budget",
    "trend",
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

SYSTEM_PROMPT = """You are SafeSite's London Property Intelligence Engine.
You translate the user's base form inputs AND their free-text 'extra_notes' into a dynamic multi-dimensional scoring configuration across all 33 London boroughs.

Available scoring dimensions (weights 0 to 10):
- budget: Affordability / price fit
- trend: Historical price appreciation & investment growth
- safety: Low crime rate
- transport: Public transport (Tube/Rail/Bus PTAL)
- flood: Low flood risk
- car_friendly: Driving suitability, parking ease, low traffic congestion (IMPORTANT: if user says they drive a car / don't need public transport, set car_friendly=9 and set transport=0!)
- green_space: Parks, woodlands, outdoor space
- schools: Primary & secondary school quality (Ofsted)
- quietness: Low road/rail/nightlife noise, peaceful residential streets
- air_quality: Clean air / low NO2 & PM2.5
- family_vibe: Family-friendly suburban housing & gardens

You can ALSO award direct bonus or penalty points (-25 to +25) to specific boroughs in `borough_boosts` (keyed by lowercase borough name, e.g., {"richmond upon thames": 15, "westminster": -15}) if the user mentions specific areas (e.g., "South West London", "East London", "Elizabeth line", "near Canary Wharf", "avoid central London").

Reply ONLY with valid JSON:
{
  "reply_text": "Clear 2-sentence explanation of exactly which dimensions and borough adjustments were activated from their note.",
  "adjusted_requirements": {
    "budget_gbp": <number>,
    "property_type": "any|detached|semi-detached|terraced|flat",
    "weights": {
      "budget": <0-10>, "trend": <0-10>, "safety": <0-10>, "transport": <0-10>, "flood": <0-10>,
      "car_friendly": <0-10>, "green_space": <0-10>, "schools": <0-10>, "quietness": <0-10>,
      "air_quality": <0-10>, "family_vibe": <0-10>
    },
    "borough_boosts": {"<borough name lowercase>": <-25 to +25>}
  }
}"""


def _local_smart_context_parser(base_req: dict, extra_notes: str) -> tuple[dict, str]:
    """
    Built-in deterministic NLP rule engine so that even WITHOUT an OpenRouter API key,
    user requests like 'we have a car, no public transport, quiet area with parks and schools'
    dynamically change the active scoring columns and rankings!
    """
    txt = extra_notes.lower()
    w = dict(base_req.get("weights") or {})
    boosts = {}
    actions = []

    # 1. Car / Traffic / No public transport detection
    if any(p in txt for p in ["no public transport", "don't need tube", "dont need tube", "don't need public", "no tube", "have a car", "drive", "car", "parking", "traffic"]):
        w["car_friendly"] = 9.0
        actions.append("activated **Car & Low-Traffic Suitability (9/10)**")
        if any(p in txt for p in ["no public", "don't need", "dont need", "no tube", "not transport", "instead of public"]):
            w.pop("transport", None)
            actions.append("disabled **Public Transport weight (0/10)**")

    # 2. Quiet / Low Noise
    if any(p in txt for p in ["quiet", "peaceful", "calm", "no noise", "low noise", "tranquil"]):
        w["quietness"] = 9.0
        actions.append("activated **Quietness & Low Noise (9/10)**")

    # 3. Green space / Parks / Dogs / Nature
    if any(p in txt for p in ["park", "green", "nature", "dog", "garden", "wood", "outdoor", "forest"]):
        w["green_space"] = 8.5
        actions.append("activated **Green Spaces & Parks (8.5/10)**")

    # 4. Schools / Kids / Family
    if any(p in txt for p in ["school", "kid", "child", "family", "families", "ofsted", "education"]):
        w["schools"] = 9.0
        w["family_vibe"] = 8.0
        actions.append("activated **Schools (9/10)** & **Family Suitability (8/10)**")

    # 5. Clean Air / Pollution / Asthma
    if any(p in txt for p in ["air", "pollution", "clean air", "asthma", "breathing"]):
        w["air_quality"] = 8.5
        actions.append("activated **Clean Air Quality (8.5/10)**")

    # 6. Safety / Crime
    if any(p in txt for p in ["safe", "safest", "crime", "security", "low crime"]):
        w["safety"] = 9.5
        actions.append("boosted **Safety & Low Crime (9.5/10)**")

    # 7. Investment / Growth
    if any(p in txt for p in ["invest", "growth", "appreciation", "capital", "return", "resale"]):
        w["trend"] = 9.0
        actions.append("boosted **Price Growth Trend (9/10)**")

    # 8. Flood
    if any(p in txt for p in ["flood", "dry", "water", "elevated"]):
        w["flood"] = 9.0
        actions.append("boosted **Flood Safety (9/10)**")

    # 9. Geographic sub-region preferences
    if "south west" in txt or "southwest" in txt:
        for b in ["richmond upon thames", "kingston upon thames", "wandsworth", "merton", "sutton"]:
            boosts[b] = 12.0
        actions.append("applied **+12 pt regional boost to South West London boroughs**")
    elif "north" in txt:
        for b in ["barnet", "enfield", "haringey", "harrow", "camden", "islington"]:
            boosts[b] = 10.0
        actions.append("applied **+10 pt regional boost to North London boroughs**")
    elif "east" in txt:
        for b in ["redbridge", "waltham forest", "havering", "barking and dagenham", "newham", "tower hamlets", "hackney"]:
            boosts[b] = 10.0
        actions.append("applied **+10 pt regional boost to East London boroughs**")
    elif "west" in txt:
        for b in ["ealing", "hillingdon", "hounslow", "hammersmith and fulham", "kensington and chelsea", "brent"]:
            boosts[b] = 10.0
        actions.append("applied **+10 pt regional boost to West London boroughs**")

    merged = dict(base_req)
    merged["weights"] = w
    merged["borough_boosts"] = boosts
    if actions:
        summary = "Smart Context Engine parsed your note and " + ", ".join(actions) + "."
    else:
        summary = "Evaluated your note alongside your selected priority sliders."
    return merged, summary


def _refine_with_llm(base_req: dict, extra_notes: str, key: str) -> tuple[dict, str]:
    # First run local smart parser so baseline rules are always captured
    local_req, local_msg = _local_smart_context_parser(base_req, extra_notes)
    if not key:
        return local_req, local_msg

    prompt = f"Base form inputs: {json.dumps(base_req)}\nUser extra notes: {extra_notes}"
    res = requests.post(
        "[https://openrouter.ai/api/v1/chat/completions](https://openrouter.ai/api/v1/chat/completions)",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "google/gemini-2.5-flash",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=20,
    )
    data = res.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "OpenRouter API Error"))
    parsed = json.loads(data["choices"][0]["message"]["content"])
    adj = parsed.get("adjusted_requirements") or {}
    merged = dict(local_req)
    if adj.get("budget_gbp") and float(adj["budget_gbp"]) >= 50000:
        merged["budget_gbp"] = float(adj["budget_gbp"])
    if adj.get("property_type") in se.PROPERTY_COLUMNS:
        merged["property_type"] = adj["property_type"]
    if isinstance(adj.get("weights"), dict):
        w = {k: float(v) for k, v in adj["weights"].items() if k in ALL_WEIGHT_KEYS and float(v) > 0}
        if w:
            merged["weights"] = w
    if isinstance(adj.get("borough_boosts"), dict):
        merged["borough_boosts"] = {
            se.norm_name(k): float(v) for k, v in adj["borough_boosts"].items() if v
        }
    return merged, parsed.get("reply_text", local_msg)


def render_ranking(result: se.RankResult, carto_key: str = ""):
    m, df = result.meta, result.ranked
    active_w_str = ", ".join([f"{k.replace('_', ' ').title()}: {v*100:.0f}%" for k, v in m["weights_used"].items()])
    st.markdown(
        f'<div class="ss-card" style="border-left: 5px solid #10b981 !important; background:#ffffff !important;">'
        f'<div style="font-weight:800; font-size:1.05rem; color:#0f172a !important;">'
        f'✅ Ranked {m["n_ranked"]} Matching London Boroughs <span style="font-weight:500; color:#64748b !important;">(UK HPI to {m["data_month"]:%B %Y} + Live Flood & Air Feeds)</span>'
        f'</div>'
        f'<div style="font-size:0.88rem; color:#334155 !important; margin-top:4px;">'
        f'Target Budget: <b>£{m["budget"]:,.0f}</b> &nbsp;|&nbsp; '
        f'Property Type: <b>{m["property_type"].title()}</b> &nbsp;|&nbsp; '
        f'Active Scoring Dimensions: <b>{active_w_str}</b>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    geo = load_london_geojson()
    if geo is not None:
        names = se.geojson_name_map(geo)
        df = df.assign(GeoName=df["Key"].map(names))
        mf = df.dropna(subset=["GeoName"])

        if carto_key:
            fmap = folium.Map(location=[51.5074, -0.1278], zoom_start=10, tiles=None)
            folium.TileLayer(
                tiles=f"[https://basemaps.cartocdn.com/rastertiles/voyager/](https://basemaps.cartocdn.com/rastertiles/voyager/){{z}}/{{x}}/{{y}}.png?key={carto_key}",
                attr="CARTO",
                name="CARTO",
            ).add_to(fmap)
        else:
            fmap = folium.Map(location=[51.5074, -0.1278], zoom_start=10, tiles="OpenStreetMap")

        folium.Choropleth(
            geo_data=geo,
            data=mf,
            columns=["GeoName", "overall_score"],
            key_on="feature.properties.name",
            fill_color="YlGnBu",
            fill_opacity=0.75,
            line_opacity=0.3,
            legend_name="Overall Match Score (0-100)",
            missing_kwds={"color": "#cbd5e1", "fill_opacity": 0.3},
        ).add_to(fmap)

        components.html(fmap.get_root().render(), height=420)

    df["price_range_25_75"] = df.apply(
        lambda r: f"£{r['p25_price'] / 1000:,.0f}k – £{r['p75_price'] / 1000:,.0f}k", axis=1
    )

    base_cols = [
        "rank",
        "Borough",
        "overall_score",
        "typical_price",
        "price_range_25_75",
        "budget_score",
        "trend_score",
    ]
    ext_cols = [
        c
        for c in [
            "safety_score",
            "transport_score",
            "car_friendly_score",
            "green_space_score",
            "schools_score",
            "quietness_score",
            "air_quality_score",
            "flood_score",
        ]
        if c in df.columns
    ]
    tail_cols = ["cagr_1y", "cagr_5y", "status"]

    show = df[base_cols + ext_cols + tail_cols].copy()
    for c in ["cagr_1y", "cagr_5y"]:
        show[c] = show[c] * 100

    st.dataframe(
        show.set_index("rank"),
        use_container_width=True,
        column_config={
            "overall_score": st.column_config.ProgressColumn("Match Score", min_value=0, max_value=100, format="%d"),
            "typical_price": st.column_config.NumberColumn("Avg Price", format="£%d"),
            "price_range_25_75": st.column_config.TextColumn("25%–75% Price Range"),
            "budget_score": st.column_config.NumberColumn("Budget Fit", format="%d"),
            "trend_score": st.column_config.NumberColumn("Growth", format="%d"),
            "safety_score": st.column_config.NumberColumn("🛡️ Safety", format="%d"),
            "transport_score": st.column_config.NumberColumn("🚇 Transit", format="%d"),
            "car_friendly_score": st.column_config.NumberColumn("🚗 Car/Traffic", format="%d"),
            "green_space_score": st.column_config.NumberColumn("🌳 Green", format="%d"),
            "schools_score": st.column_config.NumberColumn("🎓 Schools", format="%d"),
            "quietness_score": st.column_config.NumberColumn("🔇 Quiet", format="%d"),
            "air_quality_score": st.column_config.NumberColumn("🌬️ Clean Air", format="%d"),
            "flood_score": st.column_config.NumberColumn("🌊 Flood Safe", format="%d"),
            "cagr_1y": st.column_config.NumberColumn("1y Growth", format="%.1f%%"),
            "cagr_5y": st.column_config.NumberColumn("5y / yr", format="%.1f%%"),
            "status": st.column_config.TextColumn("Affordability"),
        },
    )
    if len(result.excluded):
        with st.expander(f"ℹ️ {len(result.excluded)} boroughs excluded due to budget stretch (click to view)"):
            excl = result.excluded.copy()
            excl["typical_price"] = excl["typical_price"].map(lambda x: f"£{x:,.0f}" if pd.notna(x) else "N/A")
            st.dataframe(excl, use_container_width=True, hide_index=True)


def render_mode2(openrouter_key: str, external: pd.DataFrame | None = None, carto_key: str = ""):
    st.markdown(
        '<div class="ss-card" style="background:linear-gradient(135deg, #142438 0%, #1e3a8a 100%) !important; border:none !important;">'
        '<h2 style="margin:0; color:#ffffff !important;">⚖️ SafeSite Dynamic Borough Shortlist & Comparison</h2>'
        '<p style="margin:6px 0 0 0; color:#e2e8f0 !important; font-size:0.95rem;">'
        'Powered by HM Land Registry UK HPI, Live Environment Agency Flood Alerts, Live Open-Meteo Air Quality, and 9 Borough Lifestyle Dimensions.'
        '</p></div>',
        unsafe_allow_html=True,
    )

    with st.form("borough_finder_form"):
        st.markdown("#### 1️⃣ Budget & Property Type")
        col_b, col_p = st.columns([2, 2])
        with col_b:
            budget_gbp = st.number_input(
                "Maximum Purchase Budget (£)",
                min_value=150000,
                max_value=5000000,
                value=550000,
                step=25000,
            )
        with col_p:
            prop_label_map = {
                "Any Residential Property": "any",
                "Flat / Maisonette": "flat",
                "Terraced House": "terraced",
                "Semi-Detached House": "semi-detached",
                "Detached House": "detached",
            }
            prop_choice = st.selectbox("Property Type", list(prop_label_map.keys()), index=2)
            property_type = prop_label_map[prop_choice]

        st.markdown("#### 2️⃣ Core Risk & Lifestyle Priorities (Tick & Set Importance 1–10)")
        r1 = st.columns(4)
        with r1[0]:
            chk_budget = st.checkbox("💷 Budget Fit", value=True)
            w_budget = st.slider("Budget weight", 1, 10, 8, label_visibility="collapsed")
        with r1[1]:
            chk_safety = st.checkbox("🛡️ Safety & Low Crime", value=True)
            w_safety = st.slider("Safety weight", 1, 10, 8, label_visibility="collapsed")
        with r1[2]:
            chk_trend = st.checkbox("📈 Price Growth Trend", value=True)
            w_trend = st.slider("Growth weight", 1, 10, 5, label_visibility="collapsed")
        with r1[3]:
            chk_transport = st.checkbox("🚇 Tube & Rail Links", value=False)
            w_transport = st.slider("Transport weight", 1, 10, 6, label_visibility="collapsed")

        r2 = st.columns(4)
        with r2[0]:
            chk_car = st.checkbox("🚗 Car-Friendly & Low Traffic", value=False)
            w_car = st.slider("Car weight", 1, 10, 7, label_visibility="collapsed")
        with r2[1]:
            chk_green = st.checkbox("🌳 Parks & Green Space", value=False)
            w_green = st.slider("Green weight", 1, 10, 7, label_visibility="collapsed")
        with r2[2]:
            chk_schools = st.checkbox("🎓 Schools & Family", value=False)
            w_schools = st.slider("Schools weight", 1, 10, 7, label_visibility="collapsed")
        with r2[3]:
            chk_quiet = st.checkbox("🔇 Quiet & Clean Air / Flood Safe", value=False)
            w_quiet = st.slider("Quiet weight", 1, 10, 7, label_visibility="collapsed")

        st.markdown("#### 3️⃣ Additional Context or Special Requests (Dynamic AI & Smart Context Engine)")
        extra_notes = st.text_area(
            "Describe your lifestyle in your own words — this dynamically activates Car/Traffic, Quietness, Schools, Green Space, or Regional boosts:",
            placeholder="e.g. We have a car and don't need public transport, we want low traffic, quiet streets, parks for our dog, and good schools in South West London...",
            height=80,
        )

        submitted = st.form_submit_button("🔍 Dynamically Rank London Boroughs", use_container_width=True)

    if submitted or "mode2_reqs" not in st.session_state:
        weights = {}
        if chk_budget:
            weights["budget"] = float(w_budget)
        if chk_safety:
            weights["safety"] = float(w_safety)
        if chk_trend:
            weights["trend"] = float(w_trend)
        if chk_transport:
            weights["transport"] = float(w_transport)
        if chk_car:
            weights["car_friendly"] = float(w_car)
        if chk_green:
            weights["green_space"] = float(w_green)
        if chk_schools:
            weights["schools"] = float(w_schools)
            weights["family_vibe"] = float(w_schools) * 0.7
        if chk_quiet:
            weights["quietness"] = float(w_quiet)
            weights["air_quality"] = float(w_quiet) * 0.8
            weights["flood"] = float(w_quiet) * 0.8
        if not weights:
            weights = {"budget": 5.0, "trend": 5.0}

        base_req = {
            "budget_gbp": float(budget_gbp),
            "property_type": property_type,
            "weights": weights,
            "borough_boosts": {},
        }

        ai_note = None
        if submitted and extra_notes.strip():
            with st.spinner("🤖 Dynamically adjusting scoring dimensions from your custom request..."):
                try:
                    base_req, ai_note = _refine_with_llm(base_req, extra_notes.strip(), openrouter_key)
                except Exception:
                    base_req, ai_note = _local_smart_context_parser(base_req, extra_notes.strip())

        st.session_state.mode2_reqs = base_req
        st.session_state.mode2_ai_note = ai_note

    reqs = st.session_state.get("mode2_reqs")
    if st.session_state.get("mode2_ai_note"):
        st.info(f"🧠 **Dynamic Context Applied:** {st.session_state.mode2_ai_note}")

    if reqs:
        try:
            hpi, _ = get_hpi()
            ranking = se.rank_boroughs(
                hpi,
                reqs["budget_gbp"],
                reqs["property_type"],
                reqs["weights"],
                external=external,
                borough_boosts=reqs.get("borough_boosts"),
            )
            render_ranking(ranking, carto_key=carto_key)
        except se.HPIUnavailable as e:
            st.error(f"Price data unavailable: {e}")
        except Exception as e:
            st.error(f"Error computing ranking: {e}")
