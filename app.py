"""Flask Web Dashboard for Sector Rotation AI Agent."""
import os
import sys
import json
import logging
import threading
import time
from datetime import datetime

# Add project root to path
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from flask import Flask, render_template, redirect, url_for, request, jsonify

import database as db
from engine.collector import DataCollector
from engine.indicators import IndicatorEngine
from engine.scorer import ScoringEngine
from engine.reporter import ReportGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Background refresh state ---
_refresh_lock = threading.Lock()
_refresh_status = {
    "running": False,
    "progress": "",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "last_refresh_time": None,
}

SECTOR_CN = {
    "Energy": "能源", "Materials": "原材料", "Industrials": "工业",
    "Utilities": "公用事业", "HealthCare": "医疗保健", "Financials": "金融",
    "ConsumerDisc": "可选消费", "ConsumerStaples": "必需消费",
    "InfoTech": "信息技术", "CommServices": "通信服务", "RealEstate": "房地产",
}

REGIME_CN = {"Hiking": "加息周期", "Cutting": "降息周期",
             "Stagflation": "滞胀", "Recovery": "复苏"}

REGIME_WEIGHTS = {
    "Hiking":      [0.25, 0.35, 0.40],
    "Cutting":     [0.35, 0.30, 0.35],
    "Stagflation": [0.20, 0.40, 0.40],
    "Recovery":    [0.40, 0.25, 0.35],
}


def run_pipeline(run_type="manual", custom_weights=None):
    """Full pipeline: collect → indicators → score → report → save."""
    logger.info(f"Starting pipeline run (type={run_type})...")

    collector = DataCollector()
    data = collector.collect()
    logger.info("Data collected.")

    ie = IndicatorEngine()
    indicators = ie.run(data)
    logger.info(f"Indicators computed. Regime: {indicators['regime']}")

    se = ScoringEngine()
    selection = se.score(indicators, custom_weights=custom_weights)
    bt = se.backtest(data)
    logger.info(f"Selection: longs={selection['longs']}, shorts={selection['shorts']}")

    rg = ReportGenerator()
    report = rg.generate_full_report(selection, indicators)
    logger.info("Report generated.")

    run_id, alerts = db.save_run(run_type, selection, indicators, report,
                                  bt["stats"] if bt else None)
    logger.info(f"Saved to database. Run ID: {run_id}. Alerts: {len(alerts)}")

    return run_id, selection, indicators, report, bt, alerts


def _do_background_refresh():
    """Run pipeline in a background thread. Updates _refresh_status."""
    global _refresh_status
    try:
        _refresh_status["progress"] = "正在采集市场数据..."
        collector = DataCollector()
        data = collector.collect()

        _refresh_status["progress"] = "正在计算 18 项指标..."
        ie = IndicatorEngine()
        indicators = ie.run(data)

        _refresh_status["progress"] = "正在打分选板块..."
        se = ScoringEngine()
        selection = se.score(indicators)
        bt = se.backtest(data)

        _refresh_status["progress"] = "正在生成推理报告..."
        rg = ReportGenerator()
        report = rg.generate_full_report(selection, indicators)

        run_id, alerts = db.save_run("manual", selection, indicators, report,
                                      bt["stats"] if bt else None)

        _refresh_status["running"] = False
        _refresh_status["progress"] = ""
        _refresh_status["finished_at"] = datetime.now().isoformat()
        _refresh_status["last_refresh_time"] = _refresh_status["finished_at"]
        _refresh_status["error"] = None
        logger.info(f"Background refresh complete. Run ID: {run_id}")
    except Exception as e:
        _refresh_status["running"] = False
        _refresh_status["progress"] = ""
        _refresh_status["error"] = str(e)
        _refresh_status["finished_at"] = datetime.now().isoformat()
        logger.error(f"Background refresh failed: {e}", exc_info=True)


def _zscore_color(val):
    """Return background color for z-score value."""
    if val is None or (isinstance(val, float) and (val != val)):
        return "#f8f9fa", "#666"
    if val > 1.5:
        return "#A32D2D", "#fff"
    elif val > 0.8:
        return "#F0997B", "#222"
    elif val > 0.3:
        return "#FCD9CA", "#222"
    elif val > -0.3:
        return "#F1EFE8", "#222"
    elif val > -0.8:
        return "#C8E6A0", "#222"
    elif val > -1.5:
        return "#97C459", "#222"
    else:
        return "#27500A", "#fff"


@app.route("/")
def dashboard():
    latest = db.get_latest_run()
    if not latest:
        return render_template("dashboard.html", latest=None)

    scores = json.loads(latest["scores_json"])
    import pandas as pd
    # to_json(orient="index") gives {sector: {col: val, ...}, ...}
    scores_df = pd.DataFrame.from_dict(scores, orient="index")
    scores_df = scores_df.sort_values("Composite", ascending=False)

    longs = json.loads(latest["longs"])
    shorts = json.loads(latest["shorts"])
    macro = json.loads(latest["macro_state"])
    reasoning = json.loads(latest["reasoning_json"])
    scenarios = json.loads(latest["scenarios_json"])
    bt_stats = json.loads(latest["backtest_stats"]) if latest["backtest_stats"] else None

    # Longs/shorts detail with reasons
    longs_detail = []
    for l in reasoning.get("longs", []):
        longs_detail.append({
            "sector": l["sector"],
            "sector_cn": l["sector_cn"],
            "score": f"{l['score']:.3f}",
            "reasons": l["reasons"],
        })
    shorts_detail = []
    for s in reasoning.get("shorts", []):
        shorts_detail.append({
            "sector": s["sector"],
            "sector_cn": s["sector_cn"],
            "score": f"{s['score']:.3f}",
            "reasons": s["reasons"],
        })

    # Score chart data
    score_labels = json.dumps([SECTOR_CN.get(s, s) for s in scores_df.index.tolist()])
    score_data = json.dumps([round(scores_df.loc[s, "Composite"], 3) for s in scores_df.index])
    score_colors = json.dumps([
        "#A32D2D" if s in longs else ("#27500A" if s in shorts else "#888780")
        for s in scores_df.index
    ])

    # Breakdown chart
    bd_labels = json.dumps([SECTOR_CN.get(s, s) for s in scores_df.index])
    bd_tech = json.dumps([round(scores_df.loc[s, "Tech_score"], 3) for s in scores_df.index])
    bd_fund = json.dumps([round(scores_df.loc[s, "Fund_score"], 3) for s in scores_df.index])
    bd_macro = json.dumps([round(scores_df.loc[s, "Macro_score"], 3) for s in scores_df.index])

    # Heatmap
    from engine.indicators import IndicatorEngine, SENSITIVITY, REGIME_IDX
    # Reconstruct z-scores from the stored data - use the scores_df
    heatmap_cols = ["RSI", "MACD", "SMA50", "EMA20", "VWAP20",
                    "PE", "PB", "ROE", "DivY", "FCF", "RevGr", "Margin",
                    "MacroFit"]
    # For simplicity, use the three category scores as heatmap
    heatmap_cols = ["技术面", "基本面", "宏观面"]
    heatmap_rows = []
    for s in scores_df.index:
        direction = "long" if s in longs else ("short" if s in shorts else "neutral")
        tech_v = scores_df.loc[s, "Tech_score"]
        fund_v = scores_df.loc[s, "Fund_score"]
        macro_v = scores_df.loc[s, "Macro_score"]
        comp_v = scores_df.loc[s, "Composite"]
        vals = []
        for v in [tech_v, fund_v, macro_v]:
            bg, color = _zscore_color(v)
            vals.append({"text": f"{v:.2f}", "bg": bg, "color": color})
        comp_bg, comp_color = _zscore_color(comp_v)
        heatmap_rows.append({
            "sector_cn": SECTOR_CN.get(s, s),
            "direction": direction,
            "cells": vals,
            "composite_text": f"{comp_v:.2f}",
            "composite_bg": comp_bg,
            "composite_color": comp_color,
        })

    # Backtest data
    bt_labels = "[]"
    bt_ls = "[]"
    bt_eq = "[]"
    if bt_stats and "n_months" in bt_stats and bt_stats.get("n_months", 0) > 0:
        bt_labels = json.dumps(bt_stats.get("dates", []))
        bt_ls = json.dumps(bt_stats.get("ls_series", []))
        bt_eq = json.dumps(bt_stats.get("eq_series", []))

    # Alerts
    alerts = db.get_alerts(limit=5)

    return render_template("dashboard.html",
                           latest=latest,
                           longs_detail=longs_detail,
                           shorts_detail=shorts_detail,
                           macro=macro,
                           scenarios=scenarios,
                           backtest=bt_stats,
                           alerts=alerts,
                           score_chart_labels=score_labels,
                           score_chart_data=score_data,
                           score_chart_colors=score_colors,
                           breakdown_labels=bd_labels,
                           breakdown_tech=bd_tech,
                           breakdown_fund=bd_fund,
                           breakdown_macro=bd_macro,
                           heatmap_cols=heatmap_cols,
                           heatmap_rows=heatmap_rows,
                           bt_labels=bt_labels,
                           bt_ls=bt_ls,
                           bt_eq=bt_eq)


@app.route("/update")
def update():
    """Legacy: trigger sync refresh (redirect)."""
    try:
        run_pipeline(run_type="manual")
        return redirect(url_for("dashboard"))
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return f"<div class='container mt-5'><div class='alert alert-danger'>更新失败: {e}</div><a href='/' class='btn btn-primary'>返回</a></div>", 500


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Trigger background data refresh. Returns immediately."""
    global _refresh_status
    with _refresh_lock:
        if _refresh_status["running"]:
            return jsonify({"status": "already_running", "message": "刷新正在进行中，请等待..."}), 409

        # Rate limit: max 1 refresh per 10 minutes
        if _refresh_status["last_refresh_time"]:
            last = datetime.fromisoformat(_refresh_status["last_refresh_time"])
            elapsed = (datetime.now() - last).total_seconds()
            if elapsed < 600:
                remaining = int(600 - elapsed)
                return jsonify({
                    "status": "rate_limited",
                    "message": f"刷新太频繁，请 {remaining} 秒后再试",
                    "retry_after": remaining
                }), 429

        _refresh_status["running"] = True
        _refresh_status["progress"] = "正在初始化..."
        _refresh_status["started_at"] = datetime.now().isoformat()
        _refresh_status["finished_at"] = None
        _refresh_status["error"] = None

        thread = threading.Thread(target=_do_background_refresh, daemon=True)
        thread.start()

    return jsonify({
        "status": "started",
        "message": "数据刷新已启动，预计需要 2-3 分钟",
        "started_at": _refresh_status["started_at"]
    })


@app.route("/api/refresh-status")
def api_refresh_status():
    """Check background refresh progress."""
    return jsonify(_refresh_status)


@app.route("/history")
def history():
    runs_raw = db.get_recent_runs(limit=30)
    runs = []
    for r in runs_raw:
        r["longs_list"] = json.loads(r["longs"]) if r["longs"] else []
        r["shorts_list"] = json.loads(r["shorts"]) if r["shorts"] else []
        runs.append(r)

    sc_raw = db.get_selection_changes(limit=20)
    selection_changes = []
    for sc in sc_raw:
        sc["longs_list"] = json.loads(sc["longs"]) if sc["longs"] else []
        sc["shorts_list"] = json.loads(sc["shorts"]) if sc["shorts"] else []
        selection_changes.append(sc)

    return render_template("history.html", runs=runs, selection_changes=selection_changes)


@app.route("/run/<int:run_id>")
def run_detail(run_id):
    run = db.get_run_by_id(run_id)
    if not run:
        return "Not found", 404
    run["longs_list"] = json.loads(run["longs"]) if run["longs"] else []
    run["shorts_list"] = json.loads(run["shorts"]) if run["shorts"] else []
    return render_template("history.html", runs=[run], selection_changes=[])


@app.route("/settings", methods=["GET", "POST"])
def settings():
    latest = db.get_latest_run()
    current_regime = latest["regime"] if latest else "Hiking"
    current_regime_cn = REGIME_CN.get(current_regime, current_regime)
    default_weights = REGIME_WEIGHTS.get(current_regime, [0.25, 0.35, 0.40])

    custom_result = None
    custom_weights = default_weights

    if request.method == "POST":
        tech_w = float(request.form.get("tech_w", 25)) / 100
        fund_w = float(request.form.get("fund_w", 35)) / 100
        macro_w = float(request.form.get("macro_w", 40)) / 100
        total = tech_w + fund_w + macro_w
        if abs(total - 1.0) > 0.01:
            return render_template("settings.html",
                                   current_regime=current_regime,
                                   current_regime_cn=current_regime_cn,
                                   default_weights=default_weights,
                                   custom_weights=default_weights,
                                   custom_result=None,
                                   error="权重总和必须等于100%")
        custom_weights = [tech_w, fund_w, macro_w]

        # Use stored data to recompute with custom weights
        if latest:
            import pandas as pd
            scores = json.loads(latest["scores_json"])
            scores_df = pd.DataFrame.from_dict(scores, orient="index")

            # We need the z-scores to recompute
            # For simplicity, use the stored category scores
            tech_s = scores_df["Tech_score"]
            fund_s = scores_df["Fund_score"]
            macro_s = scores_df["Macro_score"]
            comp = tech_w * tech_s + fund_w * fund_s + macro_w * macro_s
            scores_df["Composite_custom"] = comp
            scores_df = scores_df.sort_values("Composite_custom", ascending=False)

            longs = list(scores_df.head(3).index)
            shorts = list(scores_df.tail(3).index)

            scores_list = []
            for s in scores_df.index:
                direction = "long" if s in longs else ("short" if s in shorts else "neutral")
                scores_list.append({
                    "sector_cn": SECTOR_CN.get(s, s),
                    "tech": f"{scores_df.loc[s, 'Tech_score']:.3f}",
                    "fund": f"{scores_df.loc[s, 'Fund_score']:.3f}",
                    "macro": f"{scores_df.loc[s, 'Macro_score']:.3f}",
                    "composite": f"{scores_df.loc[s, 'Composite_custom']:.3f}",
                    "direction": direction,
                })

            custom_result = {
                "scores_list": scores_list,
                "longs": [SECTOR_CN.get(s, s) for s in longs],
                "shorts": [SECTOR_CN.get(s, s) for s in shorts],
            }

    return render_template("settings.html",
                           current_regime=current_regime,
                           current_regime_cn=current_regime_cn,
                           default_weights=default_weights,
                           custom_weights=custom_weights,
                           custom_result=custom_result)


@app.route("/alerts")
def alerts():
    alerts = db.get_alerts(limit=50)
    return render_template("alerts.html", alerts=alerts)


@app.route("/report")
def report():
    """Generate and download a full HTML report."""
    latest = db.get_latest_run()
    if not latest:
        return redirect(url_for("dashboard"))

    reasoning = json.loads(latest["reasoning_json"])
    bt_stats = json.loads(latest["backtest_stats"]) if latest["backtest_stats"] else None
    macro = json.loads(latest["macro_state"])

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>板块轮动报告 - {latest['run_time'][:10]}</title>
<style>
body {{ font-family:sans-serif; max-width:800px; margin:0 auto; padding:20px; line-height:1.6; }}
h1 {{ color:#185FA5; border-bottom:2px solid #185FA5; padding-bottom:10px; }}
h2 {{ color:#185FA5; margin-top:30px; }}
h3 {{ margin-top:20px; }}
.long {{ color:#A32D2D; font-weight:bold; }}
.short {{ color:#27500A; font-weight:bold; }}
table {{ width:100%; border-collapse:collapse; margin:10px 0; }}
th,td {{ border:1px solid #ddd; padding:8px; text-align:left; }}
th {{ background:#f8f9fa; }}
.regime {{ display:inline-block; padding:4px 12px; border-radius:12px; font-weight:bold; }}
.meta {{ color:#888; font-size:0.9rem; }}
</style></head><body>
<h1>板块轮动推荐报告</h1>
<p class="meta">生成时间：{latest['run_time'][:19]} | 宏观状态：<span class="regime">{reasoning['regime_cn']}</span></p>

<h2>执行摘要</h2>
<p>{reasoning['executive_summary']}</p>

<h2>推荐</h2>
<h3 class="long">做多</h3>
<table><tr><th>板块</th><th>得分</th><th>理由</th></tr>"""
    for l in reasoning.get("longs", []):
        reasons_html = "<br>".join([f"• {r}" for r in l["reasons"]])
        html += f"<tr><td>{l['sector_cn']} ({l['sector']})</td><td>{l['score']:.3f}</td><td>{reasons_html}</td></tr>"
    html += "</table>"

    html += '<h3 class="short">做空</h3><table><tr><th>板块</th><th>得分</th><th>理由</th></tr>'
    for s in reasoning.get("shorts", []):
        reasons_html = "<br>".join([f"• {r}" for r in s["reasons"]])
        html += f"<tr><td>{s['sector_cn']} ({s['sector']})</td><td>{s['score']:.3f}</td><td>{reasons_html}</td></tr>"
    html += "</table>"

    html += "<h2>情景分析</h2><table><tr><th>情景</th><th>触发条件</th><th>受益</th><th>受损</th></tr>"
    for sc in reasoning.get("scenarios", []):
        html += f"<tr><td>{sc['label']}: {sc['name']}</td><td>{sc['trigger']}</td><td class='long'>{sc['winners']}</td><td class='short'>{sc['losers']}</td></tr>"
    html += "</table>"

    if bt_stats:
        html += f"""<h2>回测统计</h2>
<table>
<tr><td>回测月数</td><td>{bt_stats.get('n_months', 0)}</td></tr>
<tr><td>多空年化收益</td><td>{bt_stats.get('ls_annualized', 0):.2f}%</td></tr>
<tr><td>等权年化收益</td><td>{bt_stats.get('eq_annualized', 0):.2f}%</td></tr>
<tr><td>夏普比率</td><td>{bt_stats.get('ls_sharpe', 0):.2f}</td></tr>
<tr><td>命中率</td><td>{bt_stats.get('hit_rate', 0):.0f}%</td></tr>
</table>"""

    html += "</body></html>"

    return html


@app.route("/api/latest")
def api_latest():
    """JSON API for latest recommendations."""
    latest = db.get_latest_run()
    if not latest:
        return jsonify({"error": "no data"}), 404
    return jsonify({
        "run_time": latest["run_time"],
        "regime": latest["regime"],
        "regime_cn": latest["regime_cn"],
        "longs": json.loads(latest["longs"]),
        "shorts": json.loads(latest["shorts"]),
        "macro_state": json.loads(latest["macro_state"]),
        "summary": latest["executive_summary"],
    })


# Initialize database on import (gunicorn compatibility)
db.init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    logger.info(f"Starting Sector Rotation AI Agent on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
