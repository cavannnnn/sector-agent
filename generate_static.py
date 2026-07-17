"""Generate a standalone static HTML snapshot of the dashboard for public deployment."""
import json
import os
import sys
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import database as db

SECTOR_CN = {
    "Energy": "能源", "Materials": "原材料", "Industrials": "工业",
    "Utilities": "公用事业", "HealthCare": "医疗保健", "Financials": "金融",
    "ConsumerDisc": "可选消费", "ConsumerStaples": "必需消费",
    "InfoTech": "信息技术", "CommServices": "通信服务", "RealEstate": "房地产",
}

REGIME_CN = {"Hiking": "加息周期", "Cutting": "降息周期",
             "Stagflation": "滞胀", "Recovery": "复苏"}


def _zscore_color(val):
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


def generate():
    latest = db.get_latest_run()
    if not latest:
        print("No data in database. Run scheduler.py first.")
        return

    scores = json.loads(latest["scores_json"])
    import pandas as pd
    scores_df = pd.DataFrame.from_dict(scores, orient="index")
    scores_df = scores_df.sort_values("Composite", ascending=False)

    longs = json.loads(latest["longs"])
    shorts = json.loads(latest["shorts"])
    macro = json.loads(latest["macro_state"])
    reasoning = json.loads(latest["reasoning_json"])
    scenarios = json.loads(latest["scenarios_json"])
    bt = json.loads(latest["backtest_stats"]) if latest["backtest_stats"] else None

    # Build chart data
    score_labels = [SECTOR_CN.get(s, s) for s in scores_df.index.tolist()]
    score_data = [round(float(scores_df.loc[s, "Composite"]), 3) for s in scores_df.index]
    score_colors = ["#A32D2D" if s in longs else ("#27500A" if s in shorts else "#888780")
                    for s in scores_df.index]

    bd_labels = score_labels
    bd_tech = [round(float(scores_df.loc[s, "Tech_score"]), 3) for s in scores_df.index]
    bd_fund = [round(float(scores_df.loc[s, "Fund_score"]), 3) for s in scores_df.index]
    bd_macro = [round(float(scores_df.loc[s, "Macro_score"]), 3) for s in scores_df.index]

    # Heatmap
    heatmap_rows = []
    for s in scores_df.index:
        direction = "long" if s in longs else ("short" if s in shorts else "neutral")
        tech_v = float(scores_df.loc[s, "Tech_score"])
        fund_v = float(scores_df.loc[s, "Fund_score"])
        macro_v = float(scores_df.loc[s, "Macro_score"])
        comp_v = float(scores_df.loc[s, "Composite"])
        cells = []
        for v in [tech_v, fund_v, macro_v]:
            bg, color = _zscore_color(v)
            cells.append({"text": f"{v:.2f}", "bg": bg, "color": color})
        comp_bg, comp_color = _zscore_color(comp_v)
        heatmap_rows.append({
            "sector_cn": SECTOR_CN.get(s, s),
            "direction": direction,
            "cells": cells,
            "composite_text": f"{comp_v:.2f}",
            "composite_bg": comp_bg,
            "composite_color": comp_color,
        })

    # Longs/shorts detail
    longs_detail = reasoning.get("longs", [])
    shorts_detail = reasoning.get("shorts", [])

    # Build HTML
    regime_cn = REGIME_CN.get(latest["regime"], latest["regime"])
    run_time = latest["run_time"][:19].replace("T", " ")

    # Embed all data as JSON
    data_json = json.dumps({
        "score_labels": score_labels,
        "score_data": score_data,
        "score_colors": score_colors,
        "bd_labels": bd_labels,
        "bd_tech": bd_tech,
        "bd_fund": bd_fund,
        "bd_macro": bd_macro,
        "bt_labels": bt.get("dates", []) if bt else [],
        "bt_ls": bt.get("ls_series", []) if bt else [],
        "bt_eq": bt.get("eq_series", []) if bt else [],
        "longs_detail": longs_detail,
        "shorts_detail": shorts_detail,
        "scenarios": scenarios,
        "heatmap_rows": heatmap_rows,
    }, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>板块轮动 AI 智能体 - 实时推荐</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{ --red:#A32D2D; --green:#27500A; --blue:#185FA5; --orange:#BA7517; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans SC",sans-serif; background:#f5f6fa; }}
.navbar {{ background: linear-gradient(135deg, #185FA5, #0C447C); }}
.navbar-brand {{ font-weight:700; font-size:1.3rem; }}
.card {{ border:none; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,0.06); margin-bottom:16px; }}
.card-header {{ background:#fff; border-bottom:2px solid #f0f0f0; font-weight:600; border-radius:12px 12px 0 0 !important; }}
.tag-long {{ background:#fcebeb; color:var(--red); padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }}
.tag-short {{ background:#eaf3de; color:var(--green); padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }}
.regime-badge {{ font-size:1.1rem; padding:6px 16px; border-radius:20px; font-weight:700; }}
.regime-Hiking {{ background:#fae7d6; color:#854f0b; }}
.regime-Cutting {{ background:#d6eaf8; color:#185FA5; }}
.regime-Stagflation {{ background:#fcebeb; color:#A32D2D; }}
.regime-Recovery {{ background:#eaf3de; color:#27500A; }}
.metric-card {{ text-align:center; padding:16px; }}
.metric-value {{ font-size:1.8rem; font-weight:700; }}
.metric-label {{ font-size:0.8rem; color:#888; margin-top:4px; }}
.reason-item {{ padding:8px 0; border-bottom:1px solid #f5f5f5; }}
.reason-item:last-child {{ border-bottom:none; }}
.hero {{ background:linear-gradient(135deg,#185FA5,#0C447C); color:#fff; border-radius:16px; padding:32px; margin-bottom:24px; }}
.hero h1 {{ font-size:2rem; font-weight:800; margin-bottom:8px; }}
.hero p {{ opacity:0.9; font-size:1rem; margin-bottom:0; }}
.chart-container {{ position:relative; height:300px; width:100%; }}
.bt-chart-container {{ position:relative; height:350px; width:100%; }}
</style>
</head>
<body>

<nav class="navbar navbar-expand-lg navbar-dark mb-4">
    <div class="container">
        <a class="navbar-brand" href="#">
            <i class="bi bi-graph-up-arrow"></i> 板块轮动 AI 智能体
        </a>
        <span class="text-light" style="font-size:0.85rem; opacity:0.8;">
            Sector Rotation AI Agent
        </span>
    </div>
</nav>

<div class="container mb-5">

<!-- Hero -->
<div class="hero">
    <h1><i class="bi bi-robot"></i> AI 驱动的美股板块轮动系统</h1>
    <p>11 个 GICS 板块 · 18 项指标 · 宏观状态自动识别 · 多空配置推荐</p>
</div>

<!-- Current Recommendation -->
<div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
        <span><i class="bi bi-lightning-charge"></i> 当前推荐</span>
        <span class="regime-badge regime-{latest['regime']}">{regime_cn}</span>
    </div>
    <div class="card-body">
        <p class="text-muted mb-3" style="font-size:0.85rem;">
            <i class="bi bi-clock"></i> 数据更新：{run_time}
            &nbsp;|&nbsp; <i class="bi bi-database"></i> 数据源：Yahoo Finance · FRED
            &nbsp;|&nbsp; <i class="bi bi-cpu"></i> 18 指标加权评分
        </p>
        <p>{latest['executive_summary']}</p>
        <div class="row mt-3">
            <div class="col-md-6">
                <h6><span class="tag-long">做多 (Long)</span></h6>
                {''.join(f'''<div class="d-flex justify-content-between align-items-center py-1">
                    <span><strong>{l["sector_cn"]}</strong> ({l["sector"]})</span>
                    <span class="text-danger fw-bold">{l["score"]:.3f}</span>
                </div>''' for l in longs_detail)}
            </div>
            <div class="col-md-6">
                <h6><span class="tag-short">做空 (Short)</span></h6>
                {''.join(f'''<div class="d-flex justify-content-between align-items-center py-1">
                    <span><strong>{s["sector_cn"]}</strong> ({s["sector"]})</span>
                    <span class="text-success fw-bold">{s["score"]:.3f}</span>
                </div>''' for s in shorts_detail)}
            </div>
        </div>
    </div>
</div>

<!-- Charts -->
<div class="row">
    <div class="col-md-7">
        <div class="card">
            <div class="card-header"><i class="bi bi-bar-chart"></i> 11 板块综合得分</div>
            <div class="card-body">
                <div class="chart-container"><canvas id="scoreChart"></canvas></div>
            </div>
        </div>
    </div>
    <div class="col-md-5">
        <div class="card">
            <div class="card-header"><i class="bi bi-pie-chart"></i> 三类得分分解</div>
            <div class="card-body">
                <div class="chart-container"><canvas id="breakdownChart"></canvas></div>
            </div>
        </div>
    </div>
</div>

<!-- Macro Dashboard -->
<div class="card">
    <div class="card-header"><i class="bi bi-globe"></i> 宏观状态仪表盘</div>
    <div class="card-body">
        <div class="row text-center">
            <div class="col metric-card">
                <div class="metric-value text-danger">{macro.get('US10Y_level', 0):.2f}%</div>
                <div class="metric-label">10年期国债收益率</div>
                <div class="text-muted" style="font-size:0.75rem;">6月变动 {'+' if macro.get('US10Y_chg6m',0)>0 else ''}{macro.get('US10Y_chg6m', 0):.2f}pp</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value text-warning">${macro.get('Oil_level', 0):.1f}</div>
                <div class="metric-label">原油价格 (USD)</div>
                <div class="text-muted" style="font-size:0.75rem;">6月涨幅 +{macro.get('Oil_6m_ret', 0):.1f}%</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value text-success">+{macro.get('SP_6m_ret', 0):.1f}%</div>
                <div class="metric-label">标普500 (6月)</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value" style="color:#534AB7">{macro.get('VIX_level', 0):.1f}</div>
                <div class="metric-label">VIX 恐慌指数</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value text-info">{macro.get('YieldCurve', 0):.2f}%</div>
                <div class="metric-label">收益率曲线 (10Y-3M)</div>
            </div>
        </div>
    </div>
</div>

<!-- Heatmap -->
<div class="card">
    <div class="card-header"><i class="bi bi-grid-3x3"></i> 板块 × 指标热力图 (z-score)</div>
    <div class="card-body" style="overflow-x:auto;">
        <table class="table table-sm text-center" style="font-size:0.8rem;">
            <thead><tr><th>板块</th><th>技术面</th><th>基本面</th><th>宏观面</th><th>综合</th></tr></thead>
            <tbody id="heatmapBody"></tbody>
        </table>
        <div class="text-muted text-center" style="font-size:0.75rem;">
            红色 = 高于平均（利好做多），绿色 = 低于平均（利好做空）
        </div>
    </div>
</div>

<!-- Reasoning -->
<div class="row">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header text-danger"><i class="bi bi-arrow-up-circle"></i> 做多推理</div>
            <div class="card-body" id="longsReasoning"></div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header text-success"><i class="bi bi-arrow-down-circle"></i> 做空推理</div>
            <div class="card-body" id="shortsReasoning"></div>
        </div>
    </div>
</div>

<!-- Scenarios -->
<div class="card">
    <div class="card-header"><i class="bi bi-shuffle"></i> 情景分析</div>
    <div class="card-body">
        <table class="table table-sm">
            <thead><tr><th>情景</th><th>触发条件</th><th>受益板块</th><th>受损板块</th></tr></thead>
            <tbody id="scenarioBody"></tbody>
        </table>
    </div>
</div>

<!-- Backtest -->
{'' if not bt else f'''
<div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
        <span><i class="bi bi-graph-down"></i> 回测表现</span>
        <span class="text-muted" style="font-size:0.8rem;">滚动 {bt["n_months"]} 个月 · 每月再平衡</span>
    </div>
    <div class="card-body">
        <div class="row text-center mb-3">
            <div class="col metric-card">
                <div class="metric-value">{bt["n_months"]}</div>
                <div class="metric-label">回测月数</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value {'text-danger' if bt['ls_annualized']>0 else 'text-success'}">{bt["ls_annualized"]:.2f}%</div>
                <div class="metric-label">多空年化收益</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value text-success">{bt["eq_annualized"]:.2f}%</div>
                <div class="metric-label">等权年化收益</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value">{bt["hit_rate"]:.0f}%</div>
                <div class="metric-label">胜率</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value">{bt["ls_sharpe"]:.2f}</div>
                <div class="metric-label">夏普比率</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value {'text-danger' if bt['ls_cumulative']>0 else 'text-success'}">{bt["ls_cumulative"]:.1f}%</div>
                <div class="metric-label">多空累计收益</div>
            </div>
            <div class="col metric-card">
                <div class="metric-value text-success">{bt["eq_cumulative"]:.1f}%</div>
                <div class="metric-label">等权累计收益</div>
            </div>
        </div>
        <div class="bt-chart-container"><canvas id="backtestChart"></canvas></div>
        <div class="mt-3" style="overflow-x:auto;">
            <table class="table table-sm text-center" style="font-size:0.78rem;">
                <thead><tr><th>月份</th><th>多空收益</th><th>等权收益</th><th>多空累计</th><th>等权累计</th></tr></thead>
                <tbody id="btTableBody"></tbody>
            </table>
        </div>
        <div class="text-muted mt-2" style="font-size:0.78rem;">
            <i class="bi bi-info-circle"></i> 回测说明：每月末根据框架打分选择 3 做多 + 3 做空板块，持有至下月末。多空收益 = 做多平均收益 - 做空平均收益。等权基准 = 11 板块等权持有。2024–2026 为强牛市环境，做空端受 beta 拖累。
        </div>
    </div>
</div>
'''}

<!-- Footer -->
<div class="text-center text-muted py-4" style="font-size:0.85rem;">
    <p><i class="bi bi-shield-check"></i> 数据来源：Yahoo Finance (yfinance) · 全部公开免费数据</p>
    <p><i class="bi bi-github"></i> 技术栈：Python · Flask · Chart.js · SQLite · Bootstrap 5</p>
    <p>本系统仅供研究学习，不构成投资建议。投资有风险，入市需谨慎。</p>
</div>

</div>

<script>
const D = {data_json};

// ===== Score Chart =====
new Chart(document.getElementById('scoreChart'), {{
    type: 'bar',
    data: {{
        labels: D.score_labels,
        datasets: [{{ label: '综合得分', data: D.score_data, backgroundColor: D.score_colors, borderWidth: 0, borderRadius: 4 }}]
    }},
    options: {{
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => '得分: ' + c.parsed.x.toFixed(3) }} }} }} }},
        scales: {{ x: {{ grid: {{ color: '#f0f0f0' }} }} }}
    }}
}});

// ===== Breakdown Chart =====
new Chart(document.getElementById('breakdownChart'), {{
    type: 'bar',
    data: {{
        labels: D.bd_labels,
        datasets: [
            {{ label: '技术面', data: D.bd_tech, backgroundColor: '#378ADD', borderRadius: 3 }},
            {{ label: '基本面', data: D.bd_fund, backgroundColor: '#BA7517', borderRadius: 3 }},
            {{ label: '宏观面', data: D.bd_macro, backgroundColor: '#1D9E75', borderRadius: 3 }},
        ]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12 }} }} }} }},
        scales: {{ x: {{ grid: {{ display: false }} }}, y: {{ grid: {{ color: '#f0f0f0' }} }} }}
    }}
}});

// ===== Backtest Chart =====
{'null; // no backtest' if not bt else '''
const btCtx = document.getElementById('backtestChart').getContext('2d');
const lsGrad = btCtx.createLinearGradient(0, 0, 0, 350);
lsGrad.addColorStop(0, 'rgba(163,45,45,0.25)'); lsGrad.addColorStop(1, 'rgba(163,45,45,0.02)');
const eqGrad = btCtx.createLinearGradient(0, 0, 0, 350);
eqGrad.addColorStop(0, 'rgba(24,95,165,0.25)'); eqGrad.addColorStop(1, 'rgba(24,95,165,0.02)');
new Chart(btCtx, {{
    type: 'line',
    data: {{
        labels: D.bt_labels,
        datasets: [
            {{ label: '多空策略 (L/S)', data: D.bt_ls, borderColor: '#A32D2D', backgroundColor: lsGrad, borderWidth: 2.5, fill: true, tension: 0.3, pointRadius: 3, pointHoverRadius: 6, pointBackgroundColor: '#A32D2D' }},
            {{ label: '等权基准 (11板块)', data: D.bt_eq, borderColor: '#185FA5', backgroundColor: eqGrad, borderWidth: 2.5, fill: true, tension: 0.3, pointRadius: 3, pointHoverRadius: 6, pointBackgroundColor: '#185FA5' }},
        ]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false, interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
            legend: {{ position: 'bottom', labels: {{ boxWidth: 14, font: {{ size: 13 }} }} }},
            tooltip: {{ backgroundColor: 'rgba(33,37,41,0.95)', callbacks: {{ label: c => c.dataset.label + ': ' + c.parsed.y.toFixed(2) + ' (基期=100)' }} }}
        }},
        scales: {{
            x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }}, maxRotation: 45 }} }},
            y: {{ grid: {{ color: '#f0f0f0' }}, ticks: {{ font: {{ size: 11 }}, callback: v => v.toFixed(0) }}, title: {{ display: true, text: '累计净值 (基期=100)', font: {{ size: 12 }} }} }}
        }}
    }}
}});

// Backtest table
const btBody = document.getElementById('btTableBody');
if (btBody && D.bt_labels.length > 0) {{
    let h = '';
    for (let i = 0; i < D.bt_labels.length; i++) {{
        const lsM = i === 0 ? 0 : (D.bt_ls[i] / D.bt_ls[i-1] - 1) * 100;
        const eqM = i === 0 ? 0 : (D.bt_eq[i] / D.bt_eq[i-1] - 1) * 100;
        h += '<tr><td>' + D.bt_labels[i] + '</td>' +
            '<td style="color:' + (lsM >= 0 ? '#A32D2D' : '#27500A') + ';font-weight:600;">' + (lsM >= 0 ? '+' : '') + lsM.toFixed(2) + '%</td>' +
            '<td style="color:#185FA5;">' + (eqM >= 0 ? '+' : '') + eqM.toFixed(2) + '%</td>' +
            '<td>' + D.bt_ls[i].toFixed(2) + '</td>' +
            '<td>' + D.bt_eq[i].toFixed(2) + '</td></tr>';
    }}
    btBody.innerHTML = h;
}}
'''}

// ===== Heatmap =====
const hmBody = document.getElementById('heatmapBody');
if (hmBody) {{
    let h = '';
    for (const row of D.heatmap_rows) {{
        const tag = row.direction === 'long' ? '<span class="tag-long">多</span> ' :
                     row.direction === 'short' ? '<span class="tag-short">空</span> ' : '';
        let cells = '';
        for (const c of row.cells) {{
            cells += '<td style="background:' + c.bg + ';color:' + c.color + ';">' + c.text + '</td>';
        }}
        h += '<tr><td class="text-start fw-bold">' + tag + row.sector_cn + '</td>' + cells +
             '<td style="background:' + row.composite_bg + ';color:' + row.composite_color + ';font-weight:700;">' + row.composite_text + '</td></tr>';
    }}
    hmBody.innerHTML = h;
}}

// ===== Reasoning =====
const lrBody = document.getElementById('longsReasoning');
if (lrBody) {{
    let h = '';
    for (const l of D.longs_detail) {{
        h += '<div class="mb-3"><h6><span class="tag-long">做多</span> ' + l.sector_cn + ' (' + l.sector + ') — 得分 ' + l.score.toFixed(3) + '</h6>';
        for (const r of l.reasons) h += '<div class="reason-item" style="font-size:0.88rem;">' + r + '</div>';
        h += '</div>';
    }}
    lrBody.innerHTML = h;
}}
const srBody = document.getElementById('shortsReasoning');
if (srBody) {{
    let h = '';
    for (const s of D.shorts_detail) {{
        h += '<div class="mb-3"><h6><span class="tag-short">做空</span> ' + s.sector_cn + ' (' + s.sector + ') — 得分 ' + s.score.toFixed(3) + '</h6>';
        for (const r of s.reasons) h += '<div class="reason-item" style="font-size:0.88rem;">' + r + '</div>';
        h += '</div>';
    }}
    srBody.innerHTML = h;
}}

// ===== Scenarios =====
const scBody = document.getElementById('scenarioBody');
if (scBody) {{
    let h = '';
    for (const sc of D.scenarios) {{
        h += '<tr><td><strong>' + sc.label + '</strong>：' + sc.name + '</td><td>' + sc.trigger + '</td>' +
             '<td class="text-danger">' + sc.winners + '</td><td class="text-success">' + sc.losers + '</td></tr>';
    }}
    scBody.innerHTML = h;
}}
</script>
</body>
</html>"""

    out_path = os.path.join(BASE, "static_site", "index.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Static site generated: {out_path}")
    print(f"File size: {os.path.getsize(out_path) / 1024:.1f} KB")
    return out_path


if __name__ == "__main__":
    generate()
