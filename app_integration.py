import json

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
    url = "https://raw.githubusercontent.com/radoi90/housequest-data/master/london_boroughs.geojson"
    try:
        return requests.get(url, timeout=10).json()
    except Exception:
        return None


# ---------------------------------------------------------------- PART B (Mode 1 — Responsive Price Cards, No '...' Cutoff)
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
        f"""
        <div class="kpi-grid">
            <div class="kpi-box">
                <div class="kpi-label">Average Price</div>
                <div class="kpi-value">£{row['latest_price']:,.0f}</div>
                <div class="kpi-sub">Borough mean ({row['latest_date']:%b %Y})</div>
            </div>
            <div class="kpi-box" style="border-left-color:#10b981;">
                <div class="kpi-label">25%–75% Typical Range</div>
                <div class="kpi-value">£{row['p25_price']/1000:,.0f}k – £{row['p75_price']/1000:,.0f}k</div>
                <div class="kpi-sub">Entry to upper quartile</div>
            </div>
            <div class="kpi-box" style="border-left-color:#6366f1;">
                <div class="kpi-label">1-Yr Growth</div>
                <div class="kpi-value">{row['cagr_1y']:.1%}</div>
                <div class="kpi-sub">{d1:+.1f} pts vs London median</div>
            </div>
            <div class="kpi-box" style="border-left-color:#f59e0b;">
                <div class="kpi-label">5-Yr Growth / yr</div>
                <div class="kpi-value">{row['cagr_5y']:.1%}</div>
                <div class="kpi-sub">{d5:+.1f} pts vs London median</div>
            </div>
            <div class="kpi-box" style="border-left-color:#0d9488;">
                <div class="kpi-label">10-Yr Growth / yr</div>
                <div class="kpi-value">{row['cagr_10y']:.1%}</div>
                <div class="kpi-sub">{d10:+.1f} pts vs London median</div>
            </div>
        </div>
        """,
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


# ---------------------------------------------------------------- PART C (Mode 2)
SYSTEM_PROMPT = """You are a London property assistant refining structured search form inputs based on the user's extra notes.
Rules:
1. Only adjust budget_gbp, property_type, or weights if the user's extra note explicitly mentions them.
2. Provide a short, friendly 1-2 sentence explanation in reply_text explaining how their custom note was applied.
Reply ONLY with JSON:
{"reply_text": "...",
 "adjusted_requirements": {
    "budget_gbp": <integer or null>,
    "property_type": "any|detached|semi-detached|terraced|flat",
    "weights": {"budget": 0-1, "trend": 0-1, "safety": 0-1, "transport": 0-1, "flood": 0-1}
 }}"""


def _refine_with_llm(base_req: dict, extra_notes: str, key: str) -> tuple[dict, str]:
    prompt = f"Base form inputs: {json.dumps(base_req)}\nUser extra notes: {extra_notes}"
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
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
    merged = dict(base_req)
    if adj.get("budget_gbp") and float(adj["budget_gbp"]) >= 50000:
        merged["budget_gbp"] = float(adj["budget_gbp"])
    if adj.get("property_type") in se.PROPERTY_COLUMNS:
        merged["property_type"] = adj["property_type"]
    if isinstance(adj.get("weights"), dict):
        w = {k: float(v) for k, v in adj["weights"].items() if float(v) > 0}
        if w:
            merged["weights"] = w
    return merged, parsed.get("reply_text", "Applied your custom notes to the ranking weights.")


def render_ranking(result: se.RankResult, carto_key: str = ""):
    m, df = result.meta, result.ranked
    st.markdown(
        f"""
        <div class="ss-card" style="border-left: 5px solid #10b981 !important; background:#ffffff !important;">
            <div style="font-weight:800; font-size:1.05rem; color:#0f172a !important;">
                ✅ Ranked {m['n_ranked']} Matching London Boroughs <span style="font-weight:500; color:#64748b !important;">(UK HPI to {m['data_month']:%B %Y})</span>
            </div>
            <div style="font-size:0.88rem; color:#334155 !important; margin-top:4px;">
                Target Budget: <b>£{m['budget']:,.0f}</b> &nbsp;|&nbsp;
                Property Type: <b>{m['property_type'].title()}</b> &nbsp;|&nbsp;
                Normalized Weights: <b>{m['weights_used']}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if m["unscored_priorities"]:
        st.warning(
            "Priority checkbox not connected to data: "
            + ", ".join(m["unscored_priorities"])
            + ". Tick 'Include Borough Safety / Transport / Flood Scores' in the left sidebar to include them."
        )

    geo = load_london_geojson()
    if geo is not None:
        names = se.geojson_name_map(geo)
        df = df.assign(GeoName=df["Key"].map(names))
        mf = df.dropna(subset=["GeoName"])

        if carto_key:
            fmap = folium.Map(location=[51.5074, -0.1278], zoom_start=10, tiles=None)
            folium.TileLayer(
                tiles=f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png?key={carto_key}",
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

        components.html(fmap.get_root().render(), height=430)

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
    ext_cols = [c for c in ["safety_score", "transport_score", "flood_score"] if c in df.columns]
    tail_cols = ["cagr_1y", "cagr_5y", "cagr_10y", "status"]

    show = df[base_cols + ext_cols + tail_cols].copy()
    for c in ["cagr_1y", "cagr_5y", "cagr_10y"]:
        show[c] = show[c] * 100

    st.dataframe(
        show.set_index("rank"),
        use_container_width=True,
        column_config={
            "overall_score": st.column_config.ProgressColumn("Match Score", min_value=0, max_value=100, format="%d"),
            "typical_price": st.column_config.NumberColumn("Avg Price", format="£%d"),
            "price_range_25_75": st.column_config.TextColumn("25%–75% Price Range"),
            "budget_score": st.column_config.NumberColumn("Budget Fit", format="%d"),
            "trend_score": st.column_config.NumberColumn("Growth Score", format="%d"),
            "safety_score": st.column_config.NumberColumn("Safety", format="%d"),
            "transport_score": st.column_config.NumberColumn("Transport", format="%d"),
            "flood_score": st.column_config.NumberColumn("Flood Safety", format="%d"),
            "cagr_1y": st.column_config.NumberColumn("1y Growth", format="%.1f%%"),
            "cagr_5y": st.column_config.NumberColumn("5y / yr", format="%.1f%%"),
            "cagr_10y": st.column_config.NumberColumn("10y / yr", format="%.1f%%"),
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
        """
        <div class="ss-card" style="background:linear-gradient(135deg, #142438 0%, #1e3a8a 100%) !important; border:none !important;">
            <h2 style="margin:0; color:#ffffff !important;">⚖️ SafeSite Borough Shortlist & Comparison</h2>
            <p style="margin:6px 0 0 0; color:#e2e8f0 !important; font-size:0.95rem;">
                Configure your purchase budget, property type, and risk priorities below—or describe your ideal neighbourhood in the text box—to rank all 33 London boroughs.
            </p>
        </div>
        """,
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

        st.markdown("#### 2️⃣ Risk & Lifestyle Priorities (Tick & Set Importance 1–10)")
        p_cols = st.columns(5)
        with p_cols[0]:
            chk_budget = st.checkbox("💷 Budget Fit", value=True)
            w_budget = st.slider("Budget weight", 1, 10, 8, label_visibility="collapsed")
        with p_cols[1]:
            chk_safety = st.checkbox("🛡️ Safety & Low Crime", value=True)
            w_safety = st.slider("Safety weight", 1, 10, 8, label_visibility="collapsed")
        with p_cols[2]:
            chk_trend = st.checkbox("📈 Price Growth", value=True)
            w_trend = st.slider("Growth weight", 1, 10, 5, label_visibility="collapsed")
        with p_cols[3]:
            chk_transport = st.checkbox("🚇 Transport Links", value=False)
            w_transport = st.slider("Transport weight", 1, 10, 6, label_visibility="collapsed")
        with p_cols[4]:
            chk_flood = st.checkbox("🌊 Low Flood Risk", value=False)
            w_flood = st.slider("Flood weight", 1, 10, 5, label_visibility="collapsed")

        st.markdown("#### 3️⃣ Additional Context or Special Requests (Optional AI Refinement)")
        extra_notes = st.text_area(
            "Add any extra requirements or context (optional — uses the OpenRouter API Key in the left sidebar):",
            placeholder="e.g. We have a car so we don't need the Tube, we just want the safest and greenest borough for £500k...",
            height=80,
        )

        submitted = st.form_submit_button("🔍 Rank Best London Boroughs", use_container_width=True)

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
        if chk_flood:
            weights["flood"] = float(w_flood)
        if not weights:
            weights = {"budget": 0.5, "trend": 0.5}

        base_req = {
            "budget_gbp": float(budget_gbp),
            "property_type": property_type,
            "weights": weights,
        }

        ai_note = None
        if submitted and extra_notes.strip():
            if openrouter_key:
                with st.spinner("🤖 AI is refining your criteria..."):
                    try:
                        base_req, ai_note = _refine_with_llm(base_req, extra_notes.strip(), openrouter_key)
                    except Exception as e:
                        st.warning(f"Used your form settings directly (AI refinement skipped: {e})")
            else:
                st.info("💡 Enter an OpenRouter API Key in the left sidebar to enable AI refinement of your extra notes. Ranking using your form sliders directly.")

        st.session_state.mode2_reqs = base_req
        st.session_state.mode2_ai_note = ai_note

    reqs = st.session_state.get("mode2_reqs")
    if st.session_state.get("mode2_ai_note"):
        st.info(f"🤖 **AI Note Adjustment:** {st.session_state.mode2_ai_note}")

    if reqs:
        try:
            hpi, _ = get_hpi()
            ranking = se.rank_boroughs(
                hpi,
                reqs["budget_gbp"],
                reqs["property_type"],
                reqs["weights"],
                external=external,
            )
            render_ranking(ranking, carto_key=carto_key)
        except se.HPIUnavailable as e:
            st.error(f"Price data unavailable: {e}")
        except Exception as e:
            st.error(f"Error computing ranking: {e}")
