"""Report Generator - auto-generates natural language reasoning for each selection."""
import logging

logger = logging.getLogger(__name__)

SECTOR_CN = {
    "Energy": "能源", "Materials": "原材料", "Industrials": "工业",
    "Utilities": "公用事业", "HealthCare": "医疗保健", "Financials": "金融",
    "ConsumerDisc": "可选消费", "ConsumerStaples": "必需消费",
    "InfoTech": "信息技术", "CommServices": "通信服务", "RealEstate": "房地产",
}

REGIME_CN = {
    "Hiking": "加息周期", "Cutting": "降息周期",
    "Stagflation": "滞胀", "Recovery": "复苏",
}

REGIME_DESC = {
    "Hiking": "利率上升、通胀升温但经济未衰退。金融和能源板块通常受益，房地产和公用事业受压。",
    "Cutting": "美联储降息以刺激经济。成长型板块（科技、可选消费）和利率敏感板块（房地产、公用事业）通常受益。",
    "Stagflation": "经济停滞 + 通胀高企。能源和必需消费抗通胀能力强，工业和金融受压。",
    "Recovery": "经济从低谷回升。工业、可选消费和科技率先反弹，公用事业和必需消费表现落后。",
}

SCENARIO_MAP = {
    "Hiking": {
        "base": ("加息持续", "10Y收益率维持4%以上，油价坚挺，经济未衰退",
                 "金融、能源、通信服务", "科技、公用事业、可选消费"),
        "alt1": ("转为降息", "美联储因经济放缓开始降息",
                 "科技、可选消费、公用事业", "金融、能源"),
        "alt2": ("滞胀风险", "油价暴涨叠加经济减速",
                 "能源、必需消费、公用事业", "金融、房地产、工业"),
    },
    "Cutting": {
        "base": ("降息持续", "美联储继续降息，经济逐步复苏",
                 "科技、可选消费、房地产", "能源、金融"),
        "alt1": ("通胀反弹", "降息过快导致通胀回升",
                 "能源、必需消费、材料", "科技、可选消费"),
        "alt2": ("经济衰退", "降息不足以阻止衰退",
                 "公用事业、必需消费、医疗", "工业、金融、可选消费"),
    },
    "Stagflation": {
        "base": ("滞胀持续", "高通胀 + 低增长延续",
                 "能源、必需消费、公用事业", "金融、房地产、工业"),
        "alt1": ("通胀回落", "大宗商品价格回落，通胀降温",
                 "科技、可选消费、工业", "能源、必需消费"),
        "alt2": ("衰退加深", "经济进一步恶化",
                 "公用事业、医疗、必需消费", "金融、工业、材料"),
    },
    "Recovery": {
        "base": ("复苏持续", "经济稳步回升，就业改善",
                 "工业、可选消费、科技", "公用事业、必需消费"),
        "alt1": ("过热风险", "复苏过快导致通胀抬头",
                 "能源、材料、金融", "科技、公用事业"),
        "alt2": ("二次探底", "复苏乏力，经济再次下滑",
                 "公用事业、必需消费、医疗", "工业、可选消费、金融"),
    },
}


class ReportGenerator:
    """Generates natural language reasoning for sector selections."""

    def generate_reasoning(self, sector, direction, scores, indicators):
        """Generate 3-point reasoning for a sector selection."""
        tech = indicators["technical"]
        fund = indicators["fundamental"]
        macro_fit = indicators["macro_fit"]
        regime = indicators["regime"]
        regime_cn = REGIME_CN[regime]
        sector_cn = SECTOR_CN.get(sector, sector)

        reasons = []

        # 1. Macro angle
        fit_score = macro_fit.get(sector, 0.5)
        if direction == "long":
            if fit_score >= 0.7:
                reasons.append(
                    f"宏观利好：在{regime_cn}中，{sector_cn}板块的宏观适配度高达 {fit_score:.2f}，"
                    f"是当前环境下的直接受益者。{REGIME_DESC[regime]}"
                )
            elif fit_score >= 0.5:
                reasons.append(
                    f"宏观中性偏正：{sector_cn}在{regime_cn}中的适配度为 {fit_score:.2f}，"
                    f"虽非最强受益者，但综合其他因素仍具吸引力。"
                )
            else:
                reasons.append(
                    f"宏观逆风但其他因素占优：{sector_cn}在{regime_cn}中适配度仅 {fit_score:.2f}，"
                    f"但技术和基本面表现突出，弥补了宏观劣势。"
                )
        else:
            if fit_score <= 0.3:
                reasons.append(
                    f"宏观利空：在{regime_cn}中，{sector_cn}板块的宏观适配度仅 {fit_score:.2f}，"
                    f"是当前环境的直接受害者。{REGIME_DESC[regime]}"
                )
            elif fit_score <= 0.5:
                reasons.append(
                    f"宏观偏弱：{sector_cn}在{regime_cn}中的适配度为 {fit_score:.2f}，"
                    f"叠加其他不利因素，综合排名靠后。"
                )
            else:
                reasons.append(
                    f"宏观尚可但技术/基本面恶化：{sector_cn}适配度 {fit_score:.2f}，"
                    f"但近期走势和估值因素拖累了综合表现。"
                )

        # 2. Fundamental angle
        if sector in fund.index:
            pe = fund.loc[sector, "PE"]
            roe = fund.loc[sector, "ROE"]
            margin = fund.loc[sector, "NetMargin"]
            if direction == "long":
                if pe and pe < 25:
                    reasons.append(
                        f"估值合理：板块 PE {pe:.1f} 倍，ROE {roe*100:.1f}%，"
                        f"净利润率 {margin*100:.1f}%，财务健康且估值有吸引力。"
                    )
                else:
                    reasons.append(
                        f"盈利能力强：ROE {roe*100:.1f}%，净利润率 {margin*100:.1f}%，"
                        f"虽然 PE {pe:.1f} 偏高，但高增长支撑估值。"
                    )
            else:
                if pe and pe > 50:
                    reasons.append(
                        f"估值过高：板块 PE 高达 {pe:.1f} 倍，远高于市场平均，"
                        f"容错空间极小，任何不及预期都会引发大幅回调。"
                    )
                elif pe and pe < 15:
                    reasons.append(
                        f"估值虽低但有原因：PE {pe:.1f} 倍看似便宜，"
                        f"但 ROE 仅 {roe*100:.1f}%，市场可能在定价结构性问题。"
                    )
                else:
                    reasons.append(
                        f"基本面走弱：PE {pe:.1f}，ROE {roe*100:.1f}%，"
                        f"利润率 {margin*100:.1f}%，综合财务指标在 11 板块中排名靠后。"
                    )

        # 3. Technical angle
        if sector in tech.index:
            rsi = tech.loc[sector, "RSI"]
            mom6 = tech.loc[sector, "Mom_6m"]
            px_sma = tech.loc[sector, "Px_vs_SMA50"]
            if direction == "long":
                if rsi > 65:
                    reasons.append(
                        f"技术面强势：RSI {rsi:.0f}（偏强），"
                        f"价格高于 50 日均线 {px_sma:.1f}%，6 个月涨幅 {mom6:.1f}%，"
                        f"动量明确向上。"
                    )
                else:
                    reasons.append(
                        f"技术面健康：RSI {rsi:.0f}（中性），"
                        f"价格高于 50 日均线 {px_sma:.1f}%，走势稳健。"
                    )
            else:
                if rsi < 45:
                    reasons.append(
                        f"技术面走弱：RSI {rsi:.0f}（偏弱），"
                        f"价格偏离 50 日均线 {px_sma:.1f}%，短期下行压力明显。"
                    )
                elif px_sma < 0:
                    reasons.append(
                        f"价格跌破均线：当前价低于 50 日均线 {abs(px_sma):.1f}%，"
                        f"趋势转弱信号。"
                    )
                else:
                    reasons.append(
                        f"技术面钝化：RSI {rsi:.0f}，虽然 6 个月涨 {mom6:.1f}%，"
                        f"但近期动能减弱，可能出现趋势反转。"
                    )

        return reasons

    def generate_scenarios(self, regime):
        """Generate 3 scenario analyses based on current regime."""
        scenarios = SCENARIO_MAP.get(regime, SCENARIO_MAP["Hiking"])
        result = []
        for key, (name, trigger, winners, losers) in scenarios.items():
            label = "基准情景" if key == "base" else ("乐观情景" if key == "alt1" else "悲观情景")
            result.append({
                "label": label,
                "name": name,
                "trigger": trigger,
                "winners": winners,
                "losers": losers,
            })
        return result

    def generate_executive_summary(self, selection, indicators):
        """Generate a one-paragraph executive summary."""
        regime = indicators["regime"]
        regime_cn = REGIME_CN[regime]
        state = indicators["macro_state"]
        longs = selection["longs"]
        shorts = selection["shorts"]
        longs_cn = "、".join([SECTOR_CN.get(s, s) for s in longs])
        shorts_cn = "、".join([SECTOR_CN.get(s, s) for s in shorts])

        summary = (
            f"当前宏观状态判定为{regime_cn}。"
            f"10年期国债收益率 {state['US10Y_level']:.2f}%，"
            f"6个月变动 {state['US10Y_chg6m']:+.2f}个百分点；"
            f"油价6个月涨幅 {state['Oil_6m_ret']:.1f}%；"
            f"标普500六个月涨幅 {state['SP_6m_ret']:.1f}%；"
            f"VIX恐慌指数 {state['VIX_level']:.1f}。"
            f"基于{regime_cn}权重配置（技术{selection['weights']['Tech']*100:.0f}%/"
            f"基本面{selection['weights']['Fund']*100:.0f}%/"
            f"宏观{selection['weights']['Macro']*100:.0f}%），"
            f"综合得分排名前三的板块为{longs_cn}（做多），"
            f"排名后三的为{shorts_cn}（做空）。"
        )
        return summary

    def generate_full_report(self, selection, indicators):
        """Generate complete report with all reasoning and scenarios."""
        report = {
            "executive_summary": self.generate_executive_summary(selection, indicators),
            "regime": indicators["regime"],
            "regime_cn": REGIME_CN[indicators["regime"]],
            "regime_desc": REGIME_DESC[indicators["regime"]],
            "longs": [],
            "shorts": [],
            "scenarios": self.generate_scenarios(indicators["regime"]),
        }

        for s in selection["longs"]:
            report["longs"].append({
                "sector": s,
                "sector_cn": SECTOR_CN.get(s, s),
                "score": float(selection["scores"].loc[s, "Composite"]),
                "reasons": self.generate_reasoning(s, "long", selection["scores"], indicators),
            })

        for s in selection["shorts"]:
            report["shorts"].append({
                "sector": s,
                "sector_cn": SECTOR_CN.get(s, s),
                "score": float(selection["scores"].loc[s, "Composite"]),
                "reasons": self.generate_reasoning(s, "short", selection["scores"], indicators),
            })

        return report
