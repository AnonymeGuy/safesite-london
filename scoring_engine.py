from __future__ import annotations

import io
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests

HPI_URL = (
    "https://publicdata.landregistry.gov.uk/market-trend-data/"
    "house-price-index-data/UK-HPI-full-file-{ym}.csv"
)

PROPERTY_COLUMNS = {
    "any": "AveragePrice",
    "detached": "DetachedPrice",
    "semi-detached": "SemiDetachedPrice",
    "terraced": "TerracedPrice",
    "flat": "FlatPrice",
}

IQR_HALF_SPREAD = {
    "any": 0.22,
    "flat": 0.17,
    "terraced": 0.19,
    "semi-detached": 0.20,
    "detached": 0.25,
}

TREND_METRICS = {
    "cagr_5y": (0.30, True),
    "cagr_10y": (0.20, True),
    "cagr_1y": (0.15, True),
    "max_drawdown_10y": (0.20, True),
    "volatility_10y": (0.15, False),
}

DEFAULT_WEIGHTS = {"budget": 0.5, "trend": 0.5}


class HPIUnavailable(RuntimeError):
    pass


def _parse_dates(col: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(col, format="%d/%m/%Y")
    except ValueError:
        return pd.to_datetime(col, dayfirst=True)


def _clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    needed = {"Date", "RegionName", "AreaCode"}
    if not needed.issubset(df.columns):
        raise HPIUnavailable(f"Unexpected HPI file layout, columns: {list(df.columns)[:8]}")
    df["Date"] = _parse_dates(df["Date"])
    df = df[df["AreaCode"].astype(str).str.startswith("E09")].copy()
    if df.empty:
        raise HPIUnavailable("No London (E09) rows found in HPI file.")
    for c in [*PROPERTY_COLUMNS.values(), "Index", "SalesVolume", "12m%Change"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan
    return df.sort_values(["AreaCode", "Date"]).reset_index(drop=True)


def load_ukhpi_london(local_path: str | None = None, max_lookback: int = 8, timeout: int = 60):
    if local_path:
        return _clean(pd.read_csv(local_path)), str(local_path)

    this_month = pd.Timestamp.today().normalize().replace(day=1)
    tried = []
    for i in range(1, max_lookback + 1):
        ym = (this_month - pd.DateOffset(months=i)).strftime("%Y-%m")
        url = HPI_URL.format(ym=ym)
        tried.append(ym)
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "safesite-london/2.0"})
        except requests.RequestException:
            continue
        if r.status_code == 200:
            text = r.content.decode("utf-8-sig")
            if text.lstrip().startswith(("Date", '"Date"')):
                return _clean(pd.read_csv(io.StringIO(text))), url
    raise HPIUnavailable(f"Could not download UK HPI (tried months: {', '.join(tried)}).")


def norm_name(name: str) -> str:
    n = str(name).lower().replace("&", "and")
    n = re.sub(r"^(london borough of|royal borough of|city of)\s+", "", n)
    return re.sub(r"[^a-z ]", "", n).strip()


def geojson_name_map(geojson: dict) -> dict:
    return {norm_name(f["properties"]["name"]): f["properties"]["name"] for f in geojson["features"]}


def _value_at(s: pd.Series, ts: pd.Timestamp) -> float:
    return float(s.asof(ts)) if ts >= s.index[0] else np.nan


def trend_metrics(series: pd.Series) -> dict:
    s = series.dropna().sort_index()
    if len(s) < 24:
        return {}
    end, last = s.index[-1], float(s.iloc[-1])
    out = {"latest_date": end, "latest_price": last}
    for yrs in (1, 3, 5, 10):
        past = _value_at(s, end - pd.DateOffset(years=yrs))
        out[f"cagr_{yrs}y"] = (last / past) ** (1 / yrs) - 1 if np.isfinite(past) and past > 0 else np.nan
    window = s[s.index > end - pd.DateOffset(years=10)]
    out["max_drawdown_10y"] = float((window / window.cummax() - 1).min())
    rets = window.pct_change().dropna()
    out["volatility_10y"] = float(rets.std() * np.sqrt(12)) if len(rets) > 12 else np.nan
    return out


def _compute_p25_p75(latest_row: pd.Series, avg_price: float, property_type: str) -> tuple[float, float]:
    if not np.isfinite(avg_price) or avg_price <= 0:
        return np.nan, np.nan
    spread = IQR_HALF_SPREAD.get(property_type, 0.20)
    if property_type == "any":
        type_prices = [
            latest_row.get("FlatPrice"),
            latest_row.get("TerracedPrice"),
            latest_row.get("SemiDetachedPrice"),
            latest_row.get("DetachedPrice"),
        ]
        valid = sorted([float(p) for p in type_prices if pd.notna(p) and float(p) > 0])
        if len(valid) >= 2:
            p25 = max(valid[0] * 0.92, avg_price * (1 - spread))
            p75 = min(valid[-1] * 0.95, avg_price * (1 + spread + 0.05))
            if p25 < avg_price < p75:
                return float(p25), float(p75)
    return float(avg_price * (1 - spread)), float(avg_price * (1 + spread))


def _pct_score(s: pd.Series, higher_is_better: bool) -> pd.Series:
    return s.rank(pct=True, ascending=higher_is_better) * 100


def borough_table(hpi: pd.DataFrame, property_type: str = "any") -> pd.DataFrame:
    col = PROPERTY_COLUMNS[property_type]
    rows = []
    for code, g in hpi.groupby("AreaCode"):
        g = g.set_index("Date").sort_index()
        sv = g["SalesVolume"].dropna()
        tm = trend_metrics(g[col])
        latest_price = tm.get("latest_price", np.nan)
        p25, p75 = _compute_p25_p75(g.iloc[-1], latest_price, property_type)
        rows.append(
            {
                "AreaCode": code,
                "Borough": g["RegionName"].iloc[-1],
                "Key": norm_name(g["RegionName"].iloc[-1]),
                "sales_12m": float(sv.iloc[-15:-3].sum()) if len(sv) >= 15 else np.nan,
                "p25_price": p25,
                "p75_price": p75,
                **tm,
            }
        )
    t = pd.DataFrame(rows)
    for m in TREND_METRICS:
        if m not in t:
            t[m] = np.nan

    w = pd.Series({m: v[0] for m, v in TREND_METRICS.items()})
    parts = pd.DataFrame({m: _pct_score(t[m], hib) for m, (_, hib) in TREND_METRICS.items()})
    t["trend_score"] = (parts * w).sum(axis=1, min_count=1) / (parts.notna() * w).sum(axis=1)
    return t


def budget_fit_score(ratio: pd.Series, floor: float = 0.6) -> pd.Series:
    return ((ratio - floor) / (1 - floor)).clip(0, 1) * 100


def budget_status(r: float) -> str:
    if pd.isna(r):
        return "No data"
    if r >= 1.0:
        return "✅ Within avg price"
    if r >= 0.78:
        return "🟡 Lower quartile (25–50%)"
    return "🔴 Below 25th percentile"


@dataclass
class RankResult:
    ranked: pd.DataFrame
    excluded: pd.DataFrame
    meta: dict


def rank_boroughs(
    hpi: pd.DataFrame,
    budget: float,
    property_type: str = "any",
    weights: dict | None = None,
    external: pd.DataFrame | None = None,
    min_budget_ratio: float = 0.75,
    exclude_thin_markets: bool = True,
    min_sales_12m: float = 500,
) -> RankResult:
    if property_type not in PROPERTY_COLUMNS:
        raise ValueError(f"property_type must be one of {list(PROPERTY_COLUMNS)}")
    if not budget or budget <= 0:
        raise ValueError("budget must be a positive number")

    t = borough_table(hpi, property_type)
    t["typical_price"] = t["latest_price"]
    t["budget_ratio"] = budget / t["typical_price"]
    t["budget_score"] = budget_fit_score(t["budget_ratio"])
    t["status"] = t["budget_ratio"].map(budget_status)

    comps = {"budget": "budget_score", "trend": "trend_score"}
    if external is not None and len(external.columns):
        ext = external.copy()
        ext.columns = [f"{c}_score" for c in ext.columns]
        t = t.merge(ext, left_on="AreaCode", right_index=True, how="left")
        comps.update({c: f"{c}_score" for c in external.columns})

    active = {k: float(v) for k, v in (weights or DEFAULT_WEIGHTS).items() if v and float(v) > 0}
    unscored = [k for k in active if k not in comps]
    use = {k: v for k, v in active.items() if k in comps}
    if not use:
        use = {"budget": 0.5, "trend": 0.5}
    w = pd.Series(use)
    S = t[[comps[k] for k in w.index]].copy()
    S.columns = w.index
    avail = S.notna()
    t["overall_score"] = (S.fillna(0) * w).sum(axis=1) / (avail * w).sum(axis=1).replace(0, np.nan)
    t["coverage"] = (avail * w).sum(axis=1) / w.sum()

    reason = pd.Series("", index=t.index)
    reason[t["typical_price"].isna()] = f"No price data for '{property_type}'"
    low = (reason == "") & (t["budget_ratio"] < min_budget_ratio)
    reason[low] = f"Budget under 25th percentile ({min_budget_ratio:.0%} of typical {property_type} price)"
    if exclude_thin_markets:
        thin = (reason == "") & (t["sales_12m"] < min_sales_12m)
        reason[thin] = f"Thin market (<{min_sales_12m:.0f} sales/yr): average unreliable"
    t["reason"] = reason

    ranked = t[reason == ""].sort_values("overall_score", ascending=False).reset_index(drop=True)
    ranked.insert(0, "rank", ranked.index + 1)
    excluded = t[reason != ""][["Borough", "AreaCode", "typical_price", "p25_price", "p75_price", "reason"]]

    meta = {
        "data_month": t["latest_date"].max(),
        "property_type": property_type,
        "budget": budget,
        "weights_used": (w / w.sum()).round(3).to_dict(),
        "unscored_priorities": unscored,
        "n_ranked": len(ranked),
        "n_excluded": len(excluded),
    }
    return RankResult(ranked, excluded.reset_index(drop=True), meta)


def borough_snapshot(hpi, area_code=None, borough_name=None, property_type="any"):
    t = borough_table(hpi, property_type)
    if area_code and (t["AreaCode"] == area_code).any():
        row = t[t["AreaCode"] == area_code].iloc[0]
    elif borough_name and (t["Key"] == norm_name(borough_name)).any():
        row = t[t["Key"] == norm_name(borough_name)].iloc[0]
    else:
        return None, None, None
    col = PROPERTY_COLUMNS[property_type]
    series = hpi[hpi["AreaCode"] == row["AreaCode"]].set_index("Date")[col].dropna()
    medians = t[["latest_price", "p25_price", "p75_price", *TREND_METRICS]].median().to_dict()
    return row.to_dict(), series, medians