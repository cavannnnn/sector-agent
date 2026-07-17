"""Database - SQLite storage for historical runs and sector tracking."""
import sqlite3
import json
import os
from datetime import datetime
import pandas as pd
import numpy as np

# Cloud-ready: allow override via env var (Render persistent disk)
DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "data", "sector_agent.db")
)


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    """Create tables if not exist."""
    conn = _get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT NOT NULL,
            run_type TEXT DEFAULT 'manual',
            regime TEXT NOT NULL,
            regime_cn TEXT,
            weights TEXT,
            macro_state TEXT,
            executive_summary TEXT,
            scores_json TEXT,
            longs TEXT,
            shorts TEXT,
            reasoning_json TEXT,
            scenarios_json TEXT,
            backtest_stats TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sector_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            run_time TEXT NOT NULL,
            sector TEXT NOT NULL,
            sector_cn TEXT,
            tech_score REAL,
            fund_score REAL,
            macro_score REAL,
            composite REAL,
            direction TEXT,
            rsi REAL,
            macd REAL,
            pe REAL,
            roe REAL,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            alert_time TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT DEFAULT 'info'
        )
    """)

    conn.commit()
    conn.close()


def save_run(run_type, selection, indicators, report, backtest_stats=None):
    """Save a complete run to the database."""
    conn = _get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()

    # Main run record
    c.execute("""
        INSERT INTO runs (run_time, run_type, regime, regime_cn, weights, macro_state,
                         executive_summary, scores_json, longs, shorts,
                         reasoning_json, scenarios_json, backtest_stats)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now, run_type,
        indicators["regime"], report["regime_cn"],
        json.dumps(selection["weights"]),
        json.dumps(indicators["macro_state"], default=str),
        report["executive_summary"],
        selection["scores"].to_json(orient="index"),
        json.dumps(selection["longs"]),
        json.dumps(selection["shorts"]),
        json.dumps(report, default=str),
        json.dumps(report["scenarios"], default=str),
        json.dumps(backtest_stats, default=str) if backtest_stats else None,
    ))
    run_id = c.lastrowid

    # Per-sector scores
    tech = indicators["technical"]
    fund = indicators["fundamental"]
    scores = selection["scores"]
    SECTOR_CN = {
        "Energy": "能源", "Materials": "原材料", "Industrials": "工业",
        "Utilities": "公用事业", "HealthCare": "医疗保健", "Financials": "金融",
        "ConsumerDisc": "可选消费", "ConsumerStaples": "必需消费",
        "InfoTech": "信息技术", "CommServices": "通信服务", "RealEstate": "房地产",
    }
    for sector in scores.index:
        direction = "long" if sector in selection["longs"] else (
            "short" if sector in selection["shorts"] else "neutral"
        )
        rsi_val = float(tech.loc[sector, "RSI"]) if sector in tech.index else None
        macd_val = float(tech.loc[sector, "MACD_hist"]) if sector in tech.index else None
        pe_val = float(fund.loc[sector, "PE"]) if sector in fund.index else None
        roe_val = float(fund.loc[sector, "ROE"]) if sector in fund.index else None

        c.execute("""
            INSERT INTO sector_scores
                (run_id, run_time, sector, sector_cn, tech_score, fund_score,
                 macro_score, composite, direction, rsi, macd, pe, roe)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, now, sector, SECTOR_CN.get(sector, sector),
            float(scores.loc[sector, "Tech_score"]),
            float(scores.loc[sector, "Fund_score"]),
            float(scores.loc[sector, "Macro_score"]),
            float(scores.loc[sector, "Composite"]),
            direction, rsi_val, macd_val, pe_val, roe_val,
        ))

    # Check for alerts (regime change, selection change)
    alerts = _check_alerts(conn, run_id, now, selection, indicators)
    for alert in alerts:
        c.execute("""
            INSERT INTO alerts (run_id, alert_time, alert_type, message, severity)
            VALUES (?, ?, ?, ?, ?)
        """, (run_id, now, alert["type"], alert["message"], alert["severity"]))

    conn.commit()
    conn.close()
    return run_id, alerts


def _check_alerts(conn, run_id, now, selection, indicators):
    """Compare current run with previous to detect changes."""
    alerts = []
    c = conn.cursor()

    c.execute("""
        SELECT regime, longs, shorts FROM runs
        WHERE id < ? ORDER BY id DESC LIMIT 1
    """, (run_id,))
    row = c.fetchone()

    if row:
        prev_regime = row[0]
        prev_longs = set(json.loads(row[1]))
        prev_shorts = set(json.loads(row[2]))

        curr_regime = indicators["regime"]
        curr_longs = set(selection["longs"])
        curr_shorts = set(selection["shorts"])

        if curr_regime != prev_regime:
            REGIME_CN = {"Hiking": "加息周期", "Cutting": "降息周期",
                         "Stagflation": "滞胀", "Recovery": "复苏"}
            alerts.append({
                "type": "regime_change",
                "message": f"宏观状态变化：{REGIME_CN.get(prev_regime, prev_regime)} → {REGIME_CN.get(curr_regime, curr_regime)}",
                "severity": "warning",
            })

        new_longs = curr_longs - prev_longs
        removed_longs = prev_longs - curr_longs
        if new_longs:
            alerts.append({
                "type": "selection_change",
                "message": f"新增做多：{', '.join(new_longs)}",
                "severity": "info",
            })
        if removed_longs:
            alerts.append({
                "type": "selection_change",
                "message": f"移出做多：{', '.join(removed_longs)}",
                "severity": "info",
            })

        new_shorts = curr_shorts - prev_shorts
        removed_shorts = prev_shorts - curr_shorts
        if new_shorts:
            alerts.append({
                "type": "selection_change",
                "message": f"新增做空：{', '.join(new_shorts)}",
                "severity": "info",
            })
        if removed_shorts:
            alerts.append({
                "type": "selection_change",
                "message": f"移出做空：{', '.join(removed_shorts)}",
                "severity": "info",
            })

    return alerts


def get_latest_run():
    """Get the most recent run with all details."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_run_by_id(run_id):
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_runs(limit=20):
    """Get recent runs summary."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, run_time, run_type, regime, regime_cn, longs, shorts,
               executive_summary
        FROM runs ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_sector_history(sector, limit=30):
    """Get score history for a specific sector."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT run_time, composite, tech_score, fund_score, macro_score,
               direction, rsi, pe, roe
        FROM sector_scores
        WHERE sector = ?
        ORDER BY id DESC LIMIT ?
    """, (sector, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_alerts(limit=10):
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM alerts ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_selection_changes(limit=10):
    """Get history of 3L/3S changes over time."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT run_time, regime, regime_cn, longs, shorts
        FROM runs ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
