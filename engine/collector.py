"""Data Collector - fetches fresh sector ETF prices, macro proxies, and fundamentals."""
import yfinance as yf
import pandas as pd
import numpy as np
import time
import logging

logger = logging.getLogger(__name__)

SECTORS = {
    "Energy": "XLE", "Materials": "XLB", "Industrials": "XLI",
    "Utilities": "XLU", "HealthCare": "XLV", "Financials": "XLF",
    "ConsumerDisc": "XLY", "ConsumerStaples": "XLP", "InfoTech": "XLK",
    "CommServices": "XLC", "RealEstate": "XLRE",
}

REPS = {
    "Energy": ["XOM", "CVX"], "Materials": ["LIN", "APD"],
    "Industrials": ["GE", "CAT"], "Utilities": ["NEE", "DUK"],
    "HealthCare": ["JNJ", "UNH"], "Financials": ["JPM", "BAC"],
    "ConsumerDisc": ["AMZN", "TSLA"], "ConsumerStaples": ["PG", "KO"],
    "InfoTech": ["AAPL", "MSFT"], "CommServices": ["GOOGL", "META"],
    "RealEstate": ["PLD", "AMT"],
}

MACRO = {
    "US10Y": "^TNX", "US3M": "^IRX", "SP500": "^GSPC",
    "Oil": "CL=F", "Gold": "GC=F", "Dollar": "DX-Y.NYB",
    "VIX": "^VIX", "Copper": "HG=F",
}


class DataCollector:
    """Fetches all raw data needed for the scoring engine."""

    def __init__(self, period="3y"):
        self.period = period
        self.sector_prices = None
        self.sector_volume = None
        self.macro_prices = None
        self.fundamentals = None

    def _fetch_price(self, tickers):
        out = {}
        for name, tk in tickers.items():
            for attempt in range(3):
                try:
                    df = yf.download(tk, period=self.period, interval="1d",
                                     progress=False, auto_adjust=True)
                    if df is not None and len(df) > 20:
                        out[name] = df
                        break
                    time.sleep(1)
                except Exception as e:
                    logger.warning(f"Fetch error {name} ({tk}): {e}")
                    time.sleep(2)
            time.sleep(0.3)
        return out

    def _fetch_fundamentals(self, tickers):
        fields = ["trailingPE", "priceToBook", "debtToEquity", "returnOnEquity",
                  "dividendYield", "freeCashflow", "revenueGrowth",
                  "grossMargins", "operatingMargins", "profitMargins",
                  "marketCap", "totalRevenue"]
        out = {}
        for tk in tickers:
            for attempt in range(3):
                try:
                    info = yf.Tickers(tk).tickers[tk].info
                    out[tk] = {f: info.get(f, np.nan) for f in fields}
                    break
                except Exception as e:
                    logger.warning(f"Fund error {tk}: {e}")
                    time.sleep(1)
            time.sleep(0.3)
        return out

    @staticmethod
    def _get_col(df, name):
        """Extract a column as a 1-d Series from potentially multi-indexed DataFrame."""
        if name in df.columns:
            s = df[name]
            return s.squeeze() if hasattr(s, 'squeeze') else s
        # Handle multi-level columns from newer yfinance
        if isinstance(df.columns, pd.MultiIndex):
            try:
                s = df[name]
                return s.squeeze() if hasattr(s, 'squeeze') else s
            except Exception:
                pass
        # Try lowercase
        for col in df.columns:
            col_name = col if isinstance(col, str) else col[0]
            if col_name == name:
                s = df[col]
                return s.squeeze() if hasattr(s, 'squeeze') else s
        return None

    def collect(self):
        """Fetch all data. Returns dict of DataFrames."""
        logger.info("Fetching sector ETF prices...")
        etf_data = self._fetch_price(SECTORS)

        # Build price panel
        price_dict = {}
        vol_dict = {}
        for n, df in etf_data.items():
            close_col = self._get_col(df, "Close")
            vol_col = self._get_col(df, "Volume")
            if close_col is not None:
                price_dict[n] = pd.Series(close_col.values.ravel(), index=df.index)
            if vol_col is not None:
                vol_dict[n] = pd.Series(vol_col.values.ravel(), index=df.index)

        self.sector_prices = pd.DataFrame(price_dict).dropna(how="all")
        self.sector_volume = pd.DataFrame(vol_dict).reindex(self.sector_prices.index)

        logger.info("Fetching macro proxies...")
        macro_data = self._fetch_price(MACRO)
        macro_dict = {}
        for n, df in macro_data.items():
            close_col = self._get_col(df, "Close")
            if close_col is not None:
                s = pd.Series(close_col.values.ravel(), index=df.index)
                # Forward-fill: index tickers like ^TNX may have NaN on latest date
                s = s.ffill().dropna()
                macro_dict[n] = s
        self.macro_prices = pd.DataFrame(macro_dict)

        # Align macro and sector prices to common date range
        common_idx = self.sector_prices.index.intersection(self.macro_prices.index)
        if len(common_idx) > 100:
            self.sector_prices = self.sector_prices.loc[common_idx]
            self.sector_volume = self.sector_volume.loc[common_idx]
            self.macro_prices = self.macro_prices.loc[common_idx]

        # Final safety: forward-fill any remaining NaN
        self.sector_prices = self.sector_prices.ffill().dropna(how="all")
        self.macro_prices = self.macro_prices.ffill()

        logger.info(f"Data aligned: {len(self.sector_prices)} rows, "
                     f"{self.sector_prices.index[0].date()} to {self.sector_prices.index[-1].date()}")
        logger.info(f"Macro NaN after ffill: {self.macro_prices.isna().sum().sum()}")

        logger.info("Fetching fundamentals...")
        all_tickers = [t for ts in REPS.values() for t in ts]
        self.fundamentals = pd.DataFrame(self._fetch_fundamentals(all_tickers)).T

        # Fill NaN with sector median
        self.fundamentals = self.fundamentals.apply(
            lambda col: col.fillna(col.median()), axis=0
        )

        return {
            "sector_prices": self.sector_prices,
            "sector_volume": self.sector_volume,
            "macro_prices": self.macro_prices,
            "fundamentals": self.fundamentals,
            "sectors": SECTORS,
            "reps": REPS,
            "macro": MACRO,
        }
