"""Indicator Engine - computes 18 indicators + macro regime classification."""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

SECTORS = ["Energy", "Materials", "Industrials", "Utilities", "HealthCare",
           "Financials", "ConsumerDisc", "ConsumerStaples", "InfoTech",
           "CommServices", "RealEstate"]

REPS = {
    "Energy": ["XOM", "CVX"], "Materials": ["LIN", "APD"],
    "Industrials": ["GE", "CAT"], "Utilities": ["NEE", "DUK"],
    "HealthCare": ["JNJ", "UNH"], "Financials": ["JPM", "BAC"],
    "ConsumerDisc": ["AMZN", "TSLA"], "ConsumerStaples": ["PG", "KO"],
    "InfoTech": ["AAPL", "MSFT"], "CommServices": ["GOOGL", "META"],
    "RealEstate": ["PLD", "AMT"],
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
REGIME_CN = {"Hiking": "加息周期", "Cutting": "降息周期",
             "Stagflation": "滞胀", "Recovery": "复苏"}


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


class IndicatorEngine:
    """Computes all indicators and classifies macro regime."""

    def compute_technical(self, prices, volume):
        rows = {}
        for s in SECTORS:
            if s not in prices.columns:
                continue
            px = prices[s].dropna()
            vol = volume[s].reindex(px.index).fillna(1)
            if len(px) < 50:
                continue
            last = px.iloc[-1]
            sma50 = px.rolling(50).mean().iloc[-1]
            ema20 = px.ewm(span=20, adjust=False).mean().iloc[-1]
            vwap20 = (px * vol).rolling(20).sum() / vol.rolling(20).sum()
            rows[s] = {
                "RSI": _rsi(px).iloc[-1],
                "MACD_hist": _macd_hist(px).iloc[-1],
                "Px_vs_SMA50": (last / sma50 - 1) * 100,
                "Px_vs_EMA20": (last / ema20 - 1) * 100,
                "Px_vs_VWAP20": (last / vwap20.iloc[-1] - 1) * 100,
                "Mom_1m": (last / px.iloc[-21] - 1) * 100 if len(px) > 21 else np.nan,
                "Mom_3m": (last / px.iloc[-63] - 1) * 100 if len(px) > 63 else np.nan,
                "Mom_6m": (last / px.iloc[-126] - 1) * 100 if len(px) > 126 else np.nan,
            }
        return pd.DataFrame(rows).T

    def compute_fundamentals(self, fund_df):
        rows = {}
        for s, reps in REPS.items():
            sub = fund_df.loc[[r for r in reps if r in fund_df.index]].copy()
            sub["FCFyield"] = sub["freeCashflow"] / sub["marketCap"]
            rows[s] = {
                "PE": sub["trailingPE"].median(),
                "PB": sub["priceToBook"].median(),
                "DE": sub["debtToEquity"].median(),
                "ROE": sub["returnOnEquity"].median(),
                "DivYield": sub["dividendYield"].median(),
                "FCFyield": sub["FCFyield"].median(),
                "RevGrowth": sub["revenueGrowth"].median(),
                "GrossMargin": sub["grossMargins"].median(),
                "OpMargin": sub["operatingMargins"].median(),
                "NetMargin": sub["profitMargins"].median(),
            }
        return pd.DataFrame(rows).T

    def compute_macro(self, macro_prices):
        m = macro_prices.ffill()
        state = {}

        y10 = m["US10Y"].dropna()
        y3 = m["US3M"].dropna()
        state["US10Y_level"] = float(y10.iloc[-1]) if len(y10) > 0 else 4.5
        state["US10Y_chg6m"] = float(y10.iloc[-1] - y10.iloc[-126]) if len(y10) > 126 else 0.0
        state["US3M_level"] = float(y3.iloc[-1]) if len(y3) > 0 else 4.5
        state["YieldCurve"] = float(y10.iloc[-1] - y3.iloc[-1]) if len(y10) > 0 and len(y3) > 0 else 0.0

        oil = m["Oil"].dropna()
        state["Oil_6m_ret"] = float((oil.iloc[-1] / oil.iloc[-126] - 1) * 100) if len(oil) > 126 else 0.0
        state["Oil_level"] = float(oil.iloc[-1]) if len(oil) > 0 else 75.0

        sp = m["SP500"].dropna()
        state["SP_6m_ret"] = float((sp.iloc[-1] / sp.iloc[-126] - 1) * 100) if len(sp) > 126 else 0.0

        vix = m["VIX"].dropna()
        state["VIX_level"] = float(vix.iloc[-1]) if len(vix) > 0 else 18.0

        cu = m["Copper"].dropna()
        state["Copper_6m_ret"] = float((cu.iloc[-1] / cu.iloc[-126] - 1) * 100) if len(cu) > 126 else 0.0

        gold = m["Gold"].dropna()
        state["Gold_6m_ret"] = float((gold.iloc[-1] / gold.iloc[-126] - 1) * 100) if len(gold) > 126 else 0.0

        return state

    def classify_regime(self, state):
        y10 = state["US10Y_level"]
        y10chg = state["US10Y_chg6m"]
        curve = state["YieldCurve"]
        oil6 = state["Oil_6m_ret"]
        sp6 = state["SP_6m_ret"]
        vix = state["VIX_level"]

        rates_rising = y10chg > 0.3
        rates_falling = y10chg < -0.3
        curve_inverted = curve < 0
        growth_ok = sp6 > 3
        growth_weak = sp6 < 0
        inflation_hot = oil6 > 10

        if rates_rising and (inflation_hot or y10 > 4) and not growth_weak:
            return "Hiking"
        elif rates_falling and growth_ok:
            return "Recovery"
        elif (inflation_hot or y10 > 4) and growth_weak:
            return "Stagflation"
        elif rates_falling and growth_weak:
            return "Cutting"
        elif curve_inverted and rates_rising:
            return "Hiking"
        else:
            return "Hiking" if y10chg >= 0 else "Recovery"

    def macro_fit_scores(self, regime):
        idx = REGIME_IDX[regime]
        return {s: SENSITIVITY[s][idx] for s in SECTORS}

    def standardize(self, tech, fund, fit):
        tech_cols = ["RSI", "MACD_hist", "Px_vs_SMA50", "Px_vs_EMA20", "Px_vs_VWAP20"]
        tech_z = tech[tech_cols].apply(_zscore)

        fund_z = fund.apply(_zscore)
        for c in ["PE", "PB", "DE"]:
            if c in fund_z.columns:
                fund_z[c] = -fund_z[c]

        fit_df = pd.Series(fit, name="MacroFit").to_frame()
        fit_z = fit_df.apply(_zscore)

        return tech_z, fund_z, fit_z

    def run(self, data):
        """Full pipeline: returns all indicators + regime + z-scores."""
        prices = data["sector_prices"]
        volume = data["sector_volume"]
        macro_prices = data["macro_prices"]
        fund_df = data["fundamentals"]

        tech = self.compute_technical(prices, volume)
        fund = self.compute_fundamentals(fund_df)
        macro_state = self.compute_macro(macro_prices)
        regime = self.classify_regime(macro_state)
        fit = self.macro_fit_scores(regime)
        tech_z, fund_z, fit_z = self.standardize(tech, fund, fit)

        return {
            "technical": tech,
            "fundamental": fund,
            "macro_state": macro_state,
            "regime": regime,
            "regime_cn": REGIME_CN[regime],
            "macro_fit": fit,
            "z_technical": tech_z,
            "z_fundamental": fund_z,
            "z_macrofit": fit_z,
            "sensitivity": SENSITIVITY,
        }
