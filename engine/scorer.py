"""Scoring Engine - weighted composite scoring, 3L/3S selection, rolling backtest."""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

SECTORS = ["Energy", "Materials", "Industrials", "Utilities", "HealthCare",
           "Financials", "ConsumerDisc", "ConsumerStaples", "InfoTech",
           "CommServices", "RealEstate"]

REGIME_WEIGHTS = {
    "Hiking":      [0.25, 0.35, 0.40],
    "Cutting":     [0.35, 0.30, 0.35],
    "Stagflation": [0.20, 0.40, 0.40],
    "Recovery":    [0.40, 0.25, 0.35],
}

SENSITIVITY = {
    "Energy":         [0.85, 0.35, 0.80, 0.55],
    "Materials":      [0.55, 0.45, 0.50, 0.70],
    "Industrials":    [0.50, 0.45, 0.35, 0.80],
    "Utilities":      [0.25, 0.80, 0.60, 0.40],
    "HealthCare":     [0.55, 0.70, 0.65, 0.60],
    "Financials":     [0.80, 0.40, 0.45, 0.65],
    "ConsumerDisc":   [0.35, 0.75, 0.25, 0.85],
    "ConsumerStaples":[0.45, 0.80, 0.70, 0.50],
    "InfoTech":       [0.40, 0.70, 0.35, 0.80],
    "CommServices":   [0.45, 0.70, 0.40, 0.75],
    "RealEstate":     [0.20, 0.75, 0.40, 0.55],
}
REGIME_IDX = {"Hiking": 0, "Cutting": 1, "Stagflation": 2, "Recovery": 3}


def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd_hist(series, fast=12, slow=26, signal=9):
    ema_f = series.ewm(span=fast, adjust=False).mean()
    ema_s = series.ewm(span=slow, adjust=False).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd - sig


def _zscore(s):
    s = s.astype(float)
    return (s - s.mean()) / s.std(ddof=0)


def _detect_regime(y10_now, y10_chg6m, curve, oil6, sp6, vix):
    rates_rising = y10_chg6m > 0.3
    rates_falling = y10_chg6m < -0.3
    curve_inverted = curve < 0
    growth_ok = sp6 > 3
    growth_weak = sp6 < 0
    inflation_hot = oil6 > 10
    if rates_rising and (inflation_hot or y10_now > 4) and not growth_weak:
        return "Hiking"
    if rates_falling and growth_ok:
        return "Recovery"
    if (inflation_hot or y10_now > 4) and growth_weak:
        return "Stagflation"
    if rates_falling and growth_weak:
        return "Cutting"
    if curve_inverted and rates_rising:
        return "Hiking"
    return "Hiking" if y10_chg6m >= 0 else "Recovery"


class ScoringEngine:
    """Computes composite scores, selects 3L/3S, runs backtest."""

    def score(self, indicators, custom_weights=None):
        regime = indicators["regime"]
        w = custom_weights or REGIME_WEIGHTS[regime]

        tech_s = indicators["z_technical"].mean(axis=1)
        fund_s = indicators["z_fundamental"].mean(axis=1)
        macro_s = indicators["z_macrofit"].mean(axis=1)

        comp = w[0] * tech_s + w[1] * fund_s + w[2] * macro_s
        detail = pd.DataFrame({
            "Tech_score": tech_s,
            "Fund_score": fund_s,
            "Macro_score": macro_s,
            "Composite": comp,
        }).sort_values("Composite", ascending=False)

        longs = list(detail.head(3).index)
        shorts = list(detail.tail(3).index)

        return {
            "scores": detail,
            "longs": longs,
            "shorts": shorts,
            "weights": {"Tech": w[0], "Fund": w[1], "Macro": w[2]},
            "regime": regime,
        }

    def backtest(self, data, max_months=36):
        prices = data["sector_prices"]
        volume = data["sector_volume"]
        macro = data["macro_prices"]
        fund = data["fundamentals"]

        from .indicators import IndicatorEngine
        ie = IndicatorEngine()
        fund_indicators = ie.compute_fundamentals(fund)

        px_m = prices.resample("ME").last()
        rebal_dates = px_m.index[6:-1]
        daily_idx = prices.index
        records = []

        for dt in rebal_dates:
            end = daily_idx.searchsorted(dt, side="right") - 1
            if end < 130:
                continue

            tech_vals = {}
            for s in SECTORS:
                px = prices[s].iloc[:end + 1].dropna()
                vol = volume[s].iloc[:end + 1].reindex(px.index).fillna(1)
                if len(px) < 50:
                    continue
                last = px.iloc[-1]
                sma50 = px.rolling(50).mean().iloc[-1]
                ema20 = px.ewm(span=20, adjust=False).mean().iloc[-1]
                vwap20 = (px * vol).rolling(20).sum() / vol.rolling(20).sum()
                tech_vals[s] = {
                    "RSI": _rsi(px).iloc[-1],
                    "MACD_hist": _macd_hist(px).iloc[-1],
                    "Px_vs_SMA50": (last / sma50 - 1) * 100,
                    "Px_vs_EMA20": (last / ema20 - 1) * 100,
                    "Px_vs_VWAP20": (last / vwap20.iloc[-1] - 1) * 100,
                }
            tech_df = pd.DataFrame(tech_vals).T

            y10 = macro["US10Y"].iloc[:end + 1].dropna()
            y3 = macro["US3M"].iloc[:end + 1].dropna()
            oil = macro["Oil"].iloc[:end + 1].dropna()
            sp = macro["SP500"].iloc[:end + 1].dropna()
            vix = macro["VIX"].iloc[:end + 1].dropna()
            if len(y10) < 130:
                continue

            regime = _detect_regime(
                y10.iloc[-1], y10.iloc[-1] - y10.iloc[-126],
                y10.iloc[-1] - y3.iloc[-1],
                (oil.iloc[-1] / oil.iloc[-126] - 1) * 100 if len(oil) > 126 else 0,
                (sp.iloc[-1] / sp.iloc[-126] - 1) * 100 if len(sp) > 126 else 0,
                vix.iloc[-1]
            )

            tech_z = tech_df.apply(_zscore)
            fund_z = fund_indicators.apply(_zscore)
            for c in ["PE", "PB", "DE"]:
                if c in fund_z.columns:
                    fund_z[c] = -fund_z[c]
            macro_fit = pd.Series(
                {s: SENSITIVITY[s][REGIME_IDX[regime]] for s in SECTORS}
            )
            macro_z = _zscore(macro_fit)

            w = REGIME_WEIGHTS[regime]
            comp = w[0] * tech_z.mean(axis=1) + w[1] * fund_z.mean(axis=1) + w[2] * macro_z
            comp = comp.sort_values(ascending=False)
            longs = list(comp.head(3).index)
            shorts = list(comp.tail(3).index)

            loc = px_m.index.get_loc(dt)
            if loc + 1 >= len(px_m):
                continue
            nxt = px_m.index[loc + 1]
            fwd_ret = px_m.loc[nxt] / px_m.loc[dt] - 1
            ls_ret = fwd_ret[longs].mean() - fwd_ret[shorts].mean()

            records.append({
                "date": dt, "regime": regime,
                "longs": ",".join(longs), "shorts": ",".join(shorts),
                "ls_ret": ls_ret, "eq_ret": fwd_ret.mean(),
            })

        bt = pd.DataFrame(records).set_index("date")
        if len(bt) == 0:
            return {"bt_df": bt, "stats": {}}
        bt["ls_cum"] = (1 + bt["ls_ret"]).cumprod()
        bt["eq_cum"] = (1 + bt["eq_ret"]).cumprod()

        n = len(bt)
        stats = {
            "n_months": n,
            "ls_annualized": bt["ls_ret"].mean() * 12 * 100,
            "eq_annualized": bt["eq_ret"].mean() * 12 * 100,
            "ls_sharpe": (bt["ls_ret"].mean() / bt["ls_ret"].std() * np.sqrt(12)
                          if bt["ls_ret"].std() > 0 else 0),
            "hit_rate": (bt["ls_ret"] > 0).mean() * 100,
            "ls_cumulative": (bt["ls_cum"].iloc[-1] - 1) * 100,
            "eq_cumulative": (bt["eq_cum"].iloc[-1] - 1) * 100,
            "ls_series": [round(float(v) * 100, 2) for v in bt["ls_cum"].values],
            "eq_series": [round(float(v) * 100, 2) for v in bt["eq_cum"].values],
            "dates": [d.strftime("%Y-%m") for d in bt.index],
        }
        return {"bt_df": bt, "stats": stats}
