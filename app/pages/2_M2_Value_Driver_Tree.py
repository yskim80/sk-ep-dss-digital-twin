"""M2. Value Driver & Drill-down - 인터랙티브 Driver Tree + KPI 분해"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db.models import SessionLocal, Financial, KPIDefinition, KPIValue
from config.settings import BUSINESS_UNITS, DECISION_AREAS

st.set_page_config(page_title="M2. Value Driver Tree", page_icon="<C2><AC>", layout="wide")
st.title("M2. Value Driver & Drill-down")
st.caption("KPI 변동의 근본원인을 인터랙티브 Driver Tree로 분해/추적")


# ── Data Loading ──
@st.cache_data(ttl=300)
def load_data():
    session = SessionLocal()
    try:
        fins = session.query(Financial).order_by(Financial.period).all()
        kpis = session.query(KPIDefinition).order_by(KPIDefinition.id).all()
        fin_df = pd.DataFrame([{
            "bu_id": r.bu_id, "period": r.period,
            "bu_name": BUSINESS_UNITS.get(r.bu_id, {}).get("name", r.bu_id),
            "revenue": r.revenue, "cogs": r.cogs, "gross_profit": r.gross_profit,
            "opex": r.opex, "ebitda": r.ebitda, "ebit": r.ebit,
            "capex": r.capex, "operating_cf": r.operating_cf, "backlog": r.backlog,
            "plan_revenue": r.plan_revenue, "plan_ebitda": r.plan_ebitda,
        } for r in fins])
        kpi_list = [{
            "id": k.id, "name": k.name, "parent": k.parent_kpi_id,
            "level": k.level, "category": k.category, "unit": k.unit,
            "formula": k.formula or "",
        } for k in kpis]
        return fin_df, kpi_list
    finally:
        session.close()

@st.cache_data(ttl=300)
def load_kpi_values(period_str):
    session = SessionLocal()
    try:
        from datetime import date
        period = date.fromisoformat(period_str)
        vals = session.query(KPIValue).filter(KPIValue.period == period).all()
        kpi_alias_map = {}
        records = []
        for v in vals:
            records.append({
                "kpi_id": kpi_alias_map.get(v.kpi_id, v.kpi_id),
                "bu_id": v.bu_id,
                "bu_name": BUSINESS_UNITS.get(v.bu_id, {}).get("name", v.bu_id),
                "actual": v.actual, "plan": v.plan,
                "gap_pct": round(v.gap_pct * 100, 1) if v.gap_pct else 0,
            })
        return pd.DataFrame(records) if records else pd.DataFrame()
    finally:
        session.close()


fin_df, kpi_tree = load_data()
if fin_df.empty:
    st.warning("데이터가 없습니다.")
    st.stop()

fin_df["period"] = pd.to_datetime(fin_df["period"])

# ── Controls ──
col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 1, 2])
with col_ctrl1:
    analysis_month = st.selectbox(
        "분석 월", options=sorted(fin_df["period"].unique(), reverse=True)[:12],
        format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m")
    )
with col_ctrl2:
    selected_bu = st.selectbox(
        "사업부", ["전사"] + [v["name"] for v in BUSINESS_UNITS.values()]
    )

current = fin_df[fin_df["period"] == analysis_month]
prev_month = pd.Timestamp(analysis_month) - pd.DateOffset(months=1)
previous = fin_df[fin_df["period"] == prev_month]

if selected_bu != "전사":
    bu_id = [k for k, v in BUSINESS_UNITS.items() if v["name"] == selected_bu][0]
    current = current[current["bu_id"] == bu_id]
    previous = previous[previous["bu_id"] == bu_id]

# ════════════════════════════════════════════════
# TAB 구조
# ════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Driver Tree (Interactive)", "EBITDA Waterfall", "KPI Drill-down",
    "SG&A Cost Pool 분석", "생산성 Driver 분석", "투자성과·ROIC 분석"
])


# ════════════════════════════════════════════════
# TAB 1: ECharts Interactive Driver Tree
# ════════════════════════════════════════════════
with tab1:
    st.subheader("인터랙티브 KPI Driver Tree")

    # 영역 선택
    area_options = {"전체": None, "성과 (Performance)": "performance", "운영 (Operation)": "operation",
                    "투자 (Investment)": "investment", "리스크 (Risk)": "risk"}
    tree_area = st.radio("영역 선택", list(area_options.keys()), horizontal=True)
    selected_area = area_options[tree_area]

    # KPI 값 로드
    kpi_vals_df = load_kpi_values(str(pd.Timestamp(analysis_month).date()))

    # Build ECharts tree data
    def build_echarts_tree(kpi_tree, kpi_vals_df, area_filter=None):
        """KPI 정의를 ECharts tree 노드 구조로 변환"""
        tree_df = pd.DataFrame(kpi_tree)
        if area_filter:
            # 영역 필터 시 해당 영역 + 자식 KPI 모두 포함
            area_kpis = tree_df[tree_df["category"] == area_filter]["id"].tolist()
            all_ids = set(area_kpis)
            for _ in range(3):  # 최대 3레벨 깊이
                children_ids = tree_df[tree_df["parent"].isin(all_ids)]["id"].tolist()
                all_ids.update(children_ids)
            tree_df = tree_df[tree_df["id"].isin(all_ids) | tree_df["category"].eq(area_filter)]

        # KPI별 Gap 데이터 집계 (전사 평균)
        # load_kpi_values에서 이미 gap_pct * 100 처리됨 → 그대로 사용
        gap_map = {}
        if not kpi_vals_df.empty:
            for kpi_id, grp in kpi_vals_df.groupby("kpi_id"):
                gap_map[kpi_id] = {
                    "avg_gap": round(grp["gap_pct"].mean(), 1),
                    "actual_avg": round(grp["actual"].mean(), 2),
                    "plan_avg": round(grp["plan"].mean(), 2),
                }

        # 재무 데이터에서 파생 KPI 값 계산 (현재 KPI ID 기준)
        fin_derived = {}
        if not current.empty:
            c = current
            p = previous if not previous.empty else current
            c_sum = c[["revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit",
                        "capex", "operating_cf", "backlog", "plan_revenue", "plan_ebitda"]].sum()
            p_sum = p[["revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit",
                        "capex", "operating_cf", "backlog", "plan_revenue", "plan_ebitda"]].sum()

            fin_derived = {
                "EBITDA": {"val": c_sum["ebitda"], "gap": (c_sum["ebitda"]/c_sum["plan_ebitda"]-1)*100 if c_sum["plan_ebitda"] else 0, "unit": "억원"},
                "REV": {"val": c_sum["revenue"], "gap": (c_sum["revenue"]/c_sum["plan_revenue"]-1)*100 if c_sum["plan_revenue"] else 0, "unit": "억원"},
                "COGS": {"val": c_sum["cogs"], "gap": ((c_sum["cogs"]/c_sum["revenue"])-(p_sum["cogs"]/p_sum["revenue"]))*100 if p_sum["revenue"] else 0, "unit": "억원"},
                "OPEX": {"val": c_sum["opex"], "gap": ((c_sum["opex"]/c_sum["revenue"])-(p_sum["opex"]/p_sum["revenue"]))*100 if p_sum["revenue"] else 0, "unit": "억원"},
                "DA": {"val": c_sum["ebitda"] - c_sum["ebit"], "gap": 0, "unit": "억원"},
                "ROIC": {"val": round((c_sum["ebit"]*0.75)/(c_sum["revenue"]*1.2)*100, 1) if c_sum["revenue"] else 0, "gap": 0, "unit": "%"},
                "FCF": {"val": c_sum["operating_cf"] - c_sum["capex"], "gap": 0, "unit": "억원"},
                "BACKLOG": {"val": c_sum["backlog"], "gap": round((c_sum["backlog"]/p_sum["backlog"]-1)*100, 1) if p_sum["backlog"] else 0, "unit": "억원"},
                "CAPEX": {"val": c_sum["capex"], "gap": round((c_sum["capex"]/p_sum["capex"]-1)*100, 1) if p_sum["capex"] else 0, "unit": "억원"},
            }
            # 사업부별 매출
            bu_rev_map = {"EPC_Hitech": "REV_EPC", "GreenEnergy": "REV_GREEN",
                          "Recycling": "REV_RECYCLE", "Solution": "REV_SOL"}
            for bu_id, kpi_id in bu_rev_map.items():
                bu_data = current[current["bu_id"] == bu_id]
                if not bu_data.empty:
                    rev = bu_data["revenue"].sum()
                    plan_rev = bu_data["plan_revenue"].sum()
                    fin_derived[kpi_id] = {
                        "val": rev,
                        "gap": round((rev/plan_rev - 1)*100, 1) if plan_rev else 0,
                        "unit": "억원",
                    }

        def make_node(row):
            kpi_id = row["id"]
            name = row["name"]
            unit = row["unit"]
            formula = row["formula"]
            level = row["level"]

            # 값 & Gap 결정
            val_str = ""
            gap_val = 0
            if kpi_id in fin_derived:
                d = fin_derived[kpi_id]
                val_str = f"{d['val']:,.0f}" if isinstance(d['val'], (int, float)) and abs(d['val']) > 10 else f"{d['val']}"
                gap_val = d["gap"]
            elif kpi_id in gap_map:
                g = gap_map[kpi_id]
                val_str = f"{g['actual_avg']}"
                gap_val = g["avg_gap"]

            # 노드 색상 (Gap 기반)
            if gap_val < -5:
                item_color = "#C00000"  # red - 미달
            elif gap_val < -2:
                item_color = "#F58220"  # orange - 주의
            elif gap_val > 2:
                item_color = "#2F5496"  # blue - 초과달성
            else:
                item_color = "#548235"  # green - 정상

            # 노드 크기 (레벨별)
            symbol_size = [50, 38, 28][min(level, 2)]

            # 라벨 (값 포함)
            label_text = f"{name}"
            if val_str:
                label_text += f"\\n{val_str} {unit}"
            if gap_val != 0:
                label_text += f"\\n({gap_val:+.1f}%)"

            node = {
                "name": label_text,
                "value": gap_val,
                "itemStyle": {"color": item_color, "borderColor": item_color, "borderWidth": 2},
                "symbolSize": symbol_size,
                "label": {"fontSize": 10 if level > 0 else 12},
                "children": [],
            }

            # 자식 노드 추가
            children_rows = tree_df[tree_df["parent"] == kpi_id]
            for _, child_row in children_rows.iterrows():
                node["children"].append(make_node(child_row))

            return node

        # 루트 노드들 (L0)
        roots = tree_df[tree_df["level"] == 0]
        if len(roots) <= 5:
            # 영역 필터 시 루트가 적으면 직접 반환
            tree_data = [make_node(row) for _, row in roots.iterrows()]
        else:
            # 전체 표시 시 카테고리별 그룹핑
            cat_names = {"performance": "성과 관리", "operation": "운영 관리",
                         "investment": "투자 관리", "risk": "리스크 관리"}
            cat_colors = {"performance": "#C00000", "operation": "#2F5496",
                          "investment": "#548235", "risk": "#F58220"}
            tree_data = []
            for cat_key, cat_name in cat_names.items():
                cat_roots = roots[roots["category"] == cat_key]
                if cat_roots.empty:
                    continue
                cat_node = {
                    "name": cat_name,
                    "itemStyle": {"color": cat_colors[cat_key], "borderColor": cat_colors[cat_key]},
                    "symbolSize": 55,
                    "label": {"fontSize": 13, "fontWeight": "bold"},
                    "children": [make_node(row) for _, row in cat_roots.iterrows()],
                }
                tree_data.append(cat_node)

        return tree_data

    tree_data = build_echarts_tree(kpi_tree, kpi_vals_df, selected_area)

    # Determine layout
    is_single_area = selected_area is not None
    orient = "LR"
    if is_single_area:
        tree_tmp = pd.DataFrame(kpi_tree)
        node_count = len(tree_tmp[tree_tmp["category"] == selected_area])
        chart_height = max(700, node_count * 55)
    else:
        chart_height = 1000

    echarts_option = {
        "tooltip": {
            "trigger": "item",
            "triggerOn": "mousemove",
            "formatter": "{b}",
        },
        "series": [{
            "type": "tree",
            "data": tree_data,
            "top": "5%",
            "left": "10%" if orient == "LR" else "5%",
            "bottom": "5%",
            "right": "25%" if orient == "LR" else "5%",
            "orient": orient,
            "symbol": "roundRect",
            "symbolSize": [130, 42] if is_single_area else [100, 35],
            "edgeShape": "polyline",
            "edgeForkPosition": "63%",
            "initialTreeDepth": 4 if is_single_area else 2,
            "label": {
                "position": "inside" if is_single_area else "inside",
                "verticalAlign": "middle",
                "align": "center",
                "fontSize": 10,
                "color": "#fff",
                "rich": {},
            },
            "leaves": {
                "label": {
                    "position": "inside",
                    "verticalAlign": "middle",
                    "align": "center",
                },
            },
            "emphasis": {
                "focus": "descendant",
            },
            "expandAndCollapse": True,
            "animationDuration": 550,
            "animationDurationUpdate": 750,
            "lineStyle": {
                "color": "#999",
                "width": 1.5,
            },
        }],
    }

    # Render ECharts via HTML component
    echarts_json = json.dumps(echarts_option, ensure_ascii=False)
    html_content = f"""
    <div id="driver-tree" style="width:100%;height:{chart_height}px;"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <script>
        var chart = echarts.init(document.getElementById('driver-tree'));
        var option = {echarts_json};
        chart.setOption(option);
        window.addEventListener('resize', function() {{ chart.resize(); }});
    </script>
    """
    components.html(html_content, height=chart_height + 20, scrolling=True)

    # 범례
    legend_cols = st.columns(4)
    legends = [
        ("정상 (Gap +-2% 이내)", "#548235"),
        ("초과 달성 (Gap > +2%)", "#2F5496"),
        ("주의 (Gap -2% ~ -5%)", "#F58220"),
        ("미달 (Gap < -5%)", "#C00000"),
    ]
    for i, (label, color) in enumerate(legends):
        legend_cols[i].markdown(
            f'<span style="display:inline-block;width:14px;height:14px;background:{color};'
            f'border-radius:3px;margin-right:6px;vertical-align:middle;"></span>'
            f'<span style="font-size:13px;">{label}</span>',
            unsafe_allow_html=True
        )


# ════════════════════════════════════════════════
# TAB 2: EBITDA Waterfall
# ════════════════════════════════════════════════
with tab2:
    st.subheader("EBITDA Driver 분해 (Waterfall)")

    if not current.empty and not previous.empty:
        curr_total = current[["revenue", "cogs", "opex", "ebitda"]].sum()
        prev_total = previous[["revenue", "cogs", "opex", "ebitda"]].sum()

        changes = {
            "전월 EBITDA": prev_total["ebitda"],
            "매출 변동": curr_total["revenue"] - prev_total["revenue"],
            "원가 변동": -(curr_total["cogs"] - prev_total["cogs"]),
            "판관비 변동": -(curr_total["opex"] - prev_total["opex"]),
            "당월 EBITDA": curr_total["ebitda"],
        }

        fig = go.Figure(go.Waterfall(
            name="", orientation="v",
            measure=["absolute", "relative", "relative", "relative", "total"],
            x=list(changes.keys()),
            y=list(changes.values()),
            textposition="outside",
            text=[f"{v:+,.0f}" if 0 < i < 4 else f"{v:,.0f}" for i, v in enumerate(changes.values())],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            increasing={"marker": {"color": "#2F5496"}},
            decreasing={"marker": {"color": "#C00000"}},
            totals={"marker": {"color": "#548235"}},
        ))
        fig.update_layout(height=400, margin=dict(t=30, b=30), yaxis_title="억원")
        st.plotly_chart(fig, use_container_width=True)

        # 사업부별 기여도
        st.subheader("사업부별 EBITDA 변동 기여도")
        if selected_bu == "전사":
            c_by_bu = current.groupby("bu_name")[["ebitda"]].sum()
            p_by_bu = previous.groupby("bu_name")[["ebitda"]].sum()
            contrib = (c_by_bu["ebitda"] - p_by_bu["ebitda"]).reset_index()
            contrib.columns = ["bu_name", "delta"]
            contrib = contrib.sort_values("delta")

            colors = ["#C00000" if v < 0 else "#2F5496" for v in contrib["delta"]]
            fig2 = go.Figure(go.Bar(
                x=contrib["delta"], y=contrib["bu_name"],
                orientation="h", marker_color=colors,
                text=[f"{v:+,.0f}" for v in contrib["delta"]],
                textposition="outside"
            ))
            fig2.update_layout(height=300, margin=dict(t=20, b=20, l=120),
                               xaxis_title="EBITDA 변동 (억원)")
            st.plotly_chart(fig2, use_container_width=True)

        # EBITDA Bridge 상세 테이블
        st.subheader("상세 Bridge 데이터")
        bridge_data = []
        for bu_id, bu_info in BUSINESS_UNITS.items():
            c_bu = current[current["bu_id"] == bu_id]
            p_bu = previous[previous["bu_id"] == bu_id]
            if c_bu.empty or p_bu.empty:
                continue
            c_s = c_bu.iloc[0]
            p_s = p_bu.iloc[0]
            bridge_data.append({
                "사업부": bu_info["name"],
                "전월 매출": f"{p_s['revenue']:,.0f}",
                "당월 매출": f"{c_s['revenue']:,.0f}",
                "매출 변동": f"{c_s['revenue']-p_s['revenue']:+,.0f}",
                "전월 EBITDA": f"{p_s['ebitda']:,.0f}",
                "당월 EBITDA": f"{c_s['ebitda']:,.0f}",
                "EBITDA 변동": f"{c_s['ebitda']-p_s['ebitda']:+,.0f}",
                "마진율(%)": f"{(c_s['ebitda']/c_s['revenue']*100):.1f}" if c_s['revenue'] else "-",
            })
        if bridge_data:
            st.dataframe(pd.DataFrame(bridge_data), use_container_width=True, hide_index=True)
    else:
        st.info("비교할 전월 데이터가 없습니다.")


# ════════════════════════════════════════════════
# TAB 3: KPI Drill-down
# ════════════════════════════════════════════════
with tab3:
    st.subheader("KPI Drill-down 분석")

    kpi_vals_df = load_kpi_values(str(pd.Timestamp(analysis_month).date()))
    tree_df = pd.DataFrame(kpi_tree)

    # KPI 선택
    l0_kpis = tree_df[tree_df["level"] == 0]
    selected_kpi = st.selectbox(
        "Top KPI 선택",
        options=l0_kpis["id"].tolist(),
        format_func=lambda x: f"{x}: {tree_df[tree_df['id']==x]['name'].values[0]} ({tree_df[tree_df['id']==x]['category'].values[0]})"
    )

    if selected_kpi:
        kpi_info = tree_df[tree_df["id"] == selected_kpi].iloc[0]
        st.markdown(f"### {kpi_info['name']} ({kpi_info['id']})")
        st.markdown(f"**산식:** {kpi_info['formula']}  |  **단위:** {kpi_info['unit']}  |  **영역:** {DECISION_AREAS.get(kpi_info['category'], kpi_info['category'])}")

        # ── 재무 기반 추세 차트 ──
        fin_kpi_map = {
            "EBITDA": "ebitda", "ROIC": None, "FCF": None,
            "REV": "revenue", "COGS": "cogs", "OPEX": "opex",
            "BACKLOG": "backlog", "CAPEX": "capex",
        }

        trend_data = pd.DataFrame()
        if selected_kpi in fin_kpi_map:
            col_name = fin_kpi_map[selected_kpi]
            if col_name:
                trend_data = fin_df.groupby("period")[col_name].sum().reset_index()
                trend_data.columns = ["period", "value"]
            elif selected_kpi == "FCF":
                trend_data = fin_df.groupby("period").agg(
                    ocf=("operating_cf", "sum"), capex=("capex", "sum")
                ).reset_index()
                trend_data["value"] = trend_data["ocf"] - trend_data["capex"]
                trend_data = trend_data[["period", "value"]]
            elif selected_kpi == "ROIC":
                # ROIC = EBIT * (1-0.25) / (Revenue * 1.2) 근사
                trend_data = fin_df.groupby("period").agg(
                    ebit=("ebit", "sum"), revenue=("revenue", "sum")
                ).reset_index()
                trend_data["value"] = (trend_data["ebit"] * 0.75) / (trend_data["revenue"] * 1.2) * 100
                trend_data = trend_data[["period", "value"]]
        else:
            # KPI Values에서 추세 로드
            from db.models import SessionLocal as _SL, KPIValue as _KV
            _sess = _SL()
            try:
                all_vals = _sess.query(_KV).filter(_KV.kpi_id == selected_kpi).order_by(_KV.period).all()
                if all_vals:
                    _records = [{"period": pd.Timestamp(v.period), "value": v.actual} for v in all_vals]
                    trend_data = pd.DataFrame(_records).groupby("period")["value"].mean().reset_index()
            finally:
                _sess.close()

        if not trend_data.empty:
            # 추세 + 계획 비교 (재무 KPI의 경우 plan도 표시)
            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(
                x=trend_data["period"], y=trend_data["value"],
                mode="lines+markers", name="실적",
                line=dict(color="#4A90D9", width=2), marker=dict(size=6),
            ))
            # plan 추세 (재무 기반)
            if selected_kpi == "EBITDA":
                plan_trend = fin_df.groupby("period")["plan_ebitda"].sum().reset_index()
                plan_trend.columns = ["period", "value"]
                fig_trend.add_trace(go.Scatter(
                    x=plan_trend["period"], y=plan_trend["value"],
                    mode="lines", name="계획", line=dict(color="#888", width=1.5, dash="dash"),
                ))
            elif selected_kpi == "REV":
                plan_trend = fin_df.groupby("period")["plan_revenue"].sum().reset_index()
                plan_trend.columns = ["period", "value"]
                fig_trend.add_trace(go.Scatter(
                    x=plan_trend["period"], y=plan_trend["value"],
                    mode="lines", name="계획", line=dict(color="#888", width=1.5, dash="dash"),
                ))
            fig_trend.update_layout(
                height=300, margin=dict(t=20, b=20),
                yaxis_title=kpi_info["unit"], xaxis_title="",
            )
            st.plotly_chart(fig_trend, use_container_width=True)

        # ── 사업부별 실적 vs 계획 ──
        # 재무 기반 KPI는 Financial 테이블에서 직접 계산
        if selected_kpi in fin_kpi_map and not current.empty:
            st.markdown("#### 사업부별 실적 vs 계획")
            col_chart, col_table = st.columns([2, 1])

            bu_compare = []
            for bu_id, bu_info in BUSINESS_UNITS.items():
                c_bu = current[current["bu_id"] == bu_id]
                if c_bu.empty:
                    continue
                c_s = c_bu.iloc[0]
                if selected_kpi == "EBITDA":
                    actual_v, plan_v = c_s["ebitda"], c_s["plan_ebitda"]
                elif selected_kpi == "REV":
                    actual_v, plan_v = c_s["revenue"], c_s["plan_revenue"]
                elif selected_kpi == "COGS":
                    actual_v = c_s["cogs"]
                    plan_v = c_s["plan_revenue"] * (c_s["cogs"] / c_s["revenue"]) if c_s["revenue"] else 0
                elif selected_kpi == "OPEX":
                    actual_v = c_s["opex"]
                    plan_v = c_s["plan_revenue"] * 0.12  # 계획 판관비율 12%
                elif selected_kpi == "CAPEX":
                    actual_v = c_s["capex"]
                    plan_v = c_s["plan_revenue"] * 0.06
                elif selected_kpi == "BACKLOG":
                    actual_v = c_s["backlog"]
                    plan_v = c_s["plan_revenue"] * 5.0
                elif selected_kpi == "FCF":
                    actual_v = c_s["operating_cf"] - c_s["capex"]
                    plan_v = c_s["plan_ebitda"] * 0.6
                elif selected_kpi == "ROIC":
                    actual_v = (c_s["ebit"] * 0.75) / (c_s["revenue"] * 1.2) * 100 if c_s["revenue"] else 0
                    plan_v = (c_s["plan_ebitda"] * 0.7) / (c_s["plan_revenue"] * 1.2) * 100 if c_s["plan_revenue"] else 0
                else:
                    continue
                gap_pct = ((actual_v / plan_v) - 1) * 100 if plan_v else 0
                bu_compare.append({
                    "bu_name": bu_info["name"], "actual": round(actual_v, 1),
                    "plan": round(plan_v, 1), "gap_pct": round(gap_pct, 1),
                })

            if bu_compare:
                compare_df = pd.DataFrame(bu_compare)
                with col_chart:
                    fig_bar = go.Figure()
                    fig_bar.add_trace(go.Bar(
                        x=compare_df["bu_name"], y=compare_df["plan"],
                        name="계획", marker_color="#D6E4F0",
                    ))
                    fig_bar.add_trace(go.Bar(
                        x=compare_df["bu_name"], y=compare_df["actual"],
                        name="실적", marker_color="#4A90D9",
                    ))
                    fig_bar.update_layout(barmode="group", height=300,
                                          margin=dict(t=20, b=20), yaxis_title=kpi_info["unit"])
                    st.plotly_chart(fig_bar, use_container_width=True)
                with col_table:
                    display_df = compare_df.rename(columns={
                        "bu_name": "사업부", "actual": "실적", "plan": "계획", "gap_pct": "Gap(%)"
                    })
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

        elif not kpi_vals_df.empty:
            # KPI Values 테이블 기반
            kpi_data = kpi_vals_df[kpi_vals_df["kpi_id"] == selected_kpi]
            if not kpi_data.empty:
                st.markdown("#### 사업부별 실적 vs 계획")
                col_chart, col_table = st.columns([2, 1])
                with col_chart:
                    fig_bar = go.Figure()
                    fig_bar.add_trace(go.Bar(
                        x=kpi_data["bu_name"], y=kpi_data["plan"],
                        name="계획", marker_color="#D6E4F0",
                    ))
                    fig_bar.add_trace(go.Bar(
                        x=kpi_data["bu_name"], y=kpi_data["actual"],
                        name="실적", marker_color="#4A90D9",
                    ))
                    fig_bar.update_layout(barmode="group", height=300,
                                          margin=dict(t=20, b=20), yaxis_title=kpi_info["unit"])
                    st.plotly_chart(fig_bar, use_container_width=True)
                with col_table:
                    display_df = kpi_data[["bu_name", "actual", "plan", "gap_pct"]].rename(columns={
                        "bu_name": "사업부", "actual": "실적", "plan": "계획", "gap_pct": "Gap(%)"
                    })
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

        # ── Driver 하위 구조 표시 ──
        children = tree_df[tree_df["parent"] == selected_kpi]
        if not children.empty:
            st.markdown("#### Driver 분해 구조")
            for _, child in children.iterrows():
                # 값 결정: KPI Values 또는 재무 데이터에서
                val_str = ""
                avg_gap_val = 0
                if not kpi_vals_df.empty:
                    child_data = kpi_vals_df[kpi_vals_df["kpi_id"] == child["id"]]
                    if not child_data.empty:
                        avg_actual = child_data["actual"].mean()
                        avg_gap = child_data["gap_pct"].mean() * 100
                        avg_gap_val = avg_gap
                        val_str = f"  |  실적: {avg_actual:,.1f} {child['unit']} (Gap: {avg_gap:+.1f}%)"

                # 재무 파생 KPI 보완
                if not val_str and not current.empty:
                    fin_child_map = {
                        "REV": ("revenue", "plan_revenue"),
                        "COGS": ("cogs", None),
                        "OPEX": ("opex", None),
                        "DA": (None, None),
                        "ROIC_NOPAT": (None, None),
                        "ROIC_IC": (None, None),
                    }
                    if child["id"] in fin_child_map:
                        actual_col, plan_col = fin_child_map[child["id"]]
                        if actual_col:
                            actual_sum = current[actual_col].sum()
                            if plan_col:
                                plan_sum = current[plan_col].sum()
                                gap = ((actual_sum / plan_sum) - 1) * 100 if plan_sum else 0
                            else:
                                plan_sum = previous[actual_col].sum() if not previous.empty else actual_sum
                                gap = ((actual_sum / plan_sum) - 1) * 100 if plan_sum else 0
                            avg_gap_val = gap
                            val_str = f"  |  실적: {actual_sum:,.0f} {child['unit']} (Gap: {gap:+.1f}%)"
                        elif child["id"] == "DA":
                            da_val = current["ebitda"].sum() - current["ebit"].sum()
                            val_str = f"  |  실적: {da_val:,.0f} {child['unit']}"
                        elif child["id"] == "ROIC_NOPAT":
                            nopat = current["ebit"].sum() * 0.75
                            val_str = f"  |  실적: {nopat:,.0f} {child['unit']}"
                        elif child["id"] == "ROIC_IC":
                            ic = current["revenue"].sum() * 1.2
                            val_str = f"  |  실적: {ic:,.0f} {child['unit']}"

                # BU별 매출 KPI
                bu_rev_map = {
                    "REV_EPC": "EPC_Hitech", "REV_GREEN": "GreenEnergy",
                    "REV_RECYCLE": "Recycling", "REV_SOL": "Solution",
                }
                if not val_str and child["id"] in bu_rev_map and not current.empty:
                    bu_id = bu_rev_map[child["id"]]
                    bu_data = current[current["bu_id"] == bu_id]
                    if not bu_data.empty:
                        rev = bu_data["revenue"].sum()
                        plan_rev = bu_data["plan_revenue"].sum()
                        gap = ((rev / plan_rev) - 1) * 100 if plan_rev else 0
                        avg_gap_val = gap
                        val_str = f"  |  실적: {rev:,.0f} {child['unit']} (Gap: {gap:+.1f}%)"

                gap_icon = "🔴" if avg_gap_val < -5 else "🟡" if avg_gap_val < -2 else "🟢" if val_str else "⚪"
                grandchildren = tree_df[tree_df["parent"] == child["id"]]

                with st.expander(f"{gap_icon} L1: {child['name']} ({child['id']}){val_str}", expanded=True):
                    st.markdown(f"**산식:** {child['formula']}  |  **단위:** {child['unit']}")

                    if not grandchildren.empty:
                        for _, gc in grandchildren.iterrows():
                            gc_val_str = ""
                            gc_gap = 0
                            if not kpi_vals_df.empty:
                                gc_data = kpi_vals_df[kpi_vals_df["kpi_id"] == gc["id"]]
                                if not gc_data.empty:
                                    gc_avg = gc_data["actual"].mean()
                                    gc_gap = gc_data["gap_pct"].mean() * 100
                                    gc_val_str = f" -> 실적: {gc_avg:,.1f} (Gap: {gc_gap:+.1f}%)"
                            # BU별 매출 보완
                            if not gc_val_str and gc["id"] in bu_rev_map and not current.empty:
                                bu_id = bu_rev_map[gc["id"]]
                                bu_data = current[current["bu_id"] == bu_id]
                                if not bu_data.empty:
                                    rev = bu_data["revenue"].sum()
                                    plan_rev = bu_data["plan_revenue"].sum()
                                    gc_gap = ((rev / plan_rev) - 1) * 100 if plan_rev else 0
                                    gc_val_str = f" -> 실적: {rev:,.0f} (Gap: {gc_gap:+.1f}%)"

                            gc_icon = "🔴" if gc_gap < -5 else "🟡" if gc_gap < -2 else "🟢" if gc_val_str else "⚪"
                            st.markdown(f"- {gc_icon} **L2: {gc['name']}** ({gc['id']}): {gc['formula']}{gc_val_str}")

                    # 사업부별 상세 차트
                    child_vals = pd.DataFrame()
                    if not kpi_vals_df.empty:
                        child_vals = kpi_vals_df[kpi_vals_df["kpi_id"] == child["id"]]

                    # 재무 기반 사업부별 차트 (KPI Values 없는 경우)
                    if child_vals.empty and not current.empty and child["id"] in ["REV", "COGS", "OPEX"]:
                        fin_col = {"REV": "revenue", "COGS": "cogs", "OPEX": "opex"}[child["id"]]
                        plan_col = {"REV": "plan_revenue", "COGS": None, "OPEX": None}[child["id"]]
                        records = []
                        for bu_id, bu_info in BUSINESS_UNITS.items():
                            c_bu = current[current["bu_id"] == bu_id]
                            p_bu = previous[previous["bu_id"] == bu_id] if not previous.empty else c_bu
                            if c_bu.empty:
                                continue
                            actual_v = c_bu[fin_col].sum()
                            if plan_col:
                                plan_v = c_bu[plan_col].sum()
                            else:
                                plan_v = p_bu[fin_col].sum() if not p_bu.empty else actual_v
                            gap = ((actual_v / plan_v) - 1) * 100 if plan_v else 0
                            records.append({"bu_name": bu_info["name"], "gap_pct": gap})
                        if records:
                            child_vals = pd.DataFrame(records)

                    if not child_vals.empty and "gap_pct" in child_vals.columns:
                        fig_child = go.Figure()
                        colors = ["#C00000" if g < -5 else "#F58220" if g < -2 else "#548235" for g in child_vals["gap_pct"]]
                        fig_child.add_trace(go.Bar(
                            x=child_vals["bu_name"], y=child_vals["gap_pct"],
                            marker_color=colors,
                            text=[f"{v:+.1f}%" for v in child_vals["gap_pct"]],
                            textposition="outside",
                        ))
                        fig_child.update_layout(
                            height=250, margin=dict(t=10, b=10),
                            yaxis_title="Gap (%)", xaxis_title="",
                            showlegend=False,
                        )
                        fig_child.add_hline(y=0, line_dash="dash", line_color="gray")
                        st.plotly_chart(fig_child, use_container_width=True)


# ════════════════════════════════════════════════
# TAB 4: SG&A Cost Pool 분석
# ════════════════════════════════════════════════
with tab4:
    st.subheader("SG&A(판관비) Cost Pool 분해")
    st.caption("판관비 증가의 주요 Cost Pool과 사업부별 기여도를 분석합니다")

    kpi_vals_df4 = load_kpi_values(str(pd.Timestamp(analysis_month).date()))
    sga_ids = ["OPEX_PERSONNEL", "OPEX_OUTSOURCE", "OPEX_MARKETING", "OPEX_RND", "OPEX_GENERAL"]
    sga_names = {"OPEX_PERSONNEL": "인건비", "OPEX_OUTSOURCE": "외주용역비",
                 "OPEX_MARKETING": "영업마케팅비", "OPEX_RND": "연구개발비", "OPEX_GENERAL": "일반관리비"}
    sga_colors = ["#2F5496", "#548235", "#BF8F00", "#7030A0", "#C00000"]

    if not kpi_vals_df4.empty:
        sga_data = kpi_vals_df4[kpi_vals_df4["kpi_id"].isin(sga_ids)]

        if not sga_data.empty:
            col_pie, col_bar = st.columns(2)

            # 전사 Cost Pool 구성비 (Pie)
            with col_pie:
                st.markdown("#### Cost Pool 구성비")
                pool_totals = sga_data.groupby("kpi_id")["actual"].sum().reset_index()
                pool_totals["name"] = pool_totals["kpi_id"].map(sga_names)
                fig_pie = go.Figure(go.Pie(
                    labels=pool_totals["name"], values=pool_totals["actual"],
                    marker=dict(colors=sga_colors),
                    textinfo="label+percent", textposition="outside",
                    hole=0.4,
                ))
                fig_pie.update_layout(height=380, margin=dict(t=20, b=20), showlegend=False)
                st.plotly_chart(fig_pie, use_container_width=True)

            # Cost Pool별 계획 대비 Gap (Bar)
            with col_bar:
                st.markdown("#### Cost Pool별 계획 대비 Gap")
                pool_gap = sga_data.groupby("kpi_id").agg(
                    actual=("actual", "sum"), plan=("plan", "sum")
                ).reset_index()
                pool_gap["gap_pct"] = ((pool_gap["actual"] / pool_gap["plan"]) - 1) * 100
                pool_gap["name"] = pool_gap["kpi_id"].map(sga_names)
                pool_gap = pool_gap.sort_values("gap_pct", ascending=True)
                colors_gap = ["#C00000" if v > 5 else "#F58220" if v > 2 else "#548235" for v in pool_gap["gap_pct"]]

                fig_gap = go.Figure(go.Bar(
                    x=pool_gap["gap_pct"], y=pool_gap["name"],
                    orientation="h", marker_color=colors_gap,
                    text=[f"{v:+.1f}%" for v in pool_gap["gap_pct"]],
                    textposition="outside",
                ))
                fig_gap.update_layout(height=380, margin=dict(t=20, b=20, l=100),
                                      xaxis_title="계획 대비 Gap (%)")
                fig_gap.add_vline(x=0, line_dash="dash", line_color="gray")
                st.plotly_chart(fig_gap, use_container_width=True)

            # 사업부 × Cost Pool 히트맵
            st.markdown("#### 사업부별 SG&A Cost Pool 상세")
            pivot = sga_data.pivot_table(index="bu_name", columns="kpi_id",
                                         values="actual", aggfunc="sum").fillna(0)
            pivot.columns = [sga_names.get(c, c) for c in pivot.columns]
            pivot["합계"] = pivot.sum(axis=1)
            pivot = pivot.sort_values("합계", ascending=False)

            # 히트맵
            heat_vals = pivot.drop(columns=["합계"])
            fig_heat = go.Figure(go.Heatmap(
                z=heat_vals.values, x=heat_vals.columns.tolist(),
                y=heat_vals.index.tolist(),
                colorscale="YlOrRd", texttemplate="%{z:.0f}",
                hovertemplate="사업부: %{y}<br>항목: %{x}<br>금액: %{z:.0f}억원",
            ))
            fig_heat.update_layout(height=300, margin=dict(t=10, b=10))
            st.plotly_chart(fig_heat, use_container_width=True)

            # 조직별 증가율 테이블
            st.markdown("#### SG&A 증가 기여도 분석")
            contrib_data = []
            for bu in sga_data["bu_name"].unique():
                bu_sga = sga_data[sga_data["bu_name"] == bu]
                total_actual = bu_sga["actual"].sum()
                total_plan = bu_sga["plan"].sum()
                gap_abs = total_actual - total_plan
                gap_pct = ((total_actual / total_plan) - 1) * 100 if total_plan else 0
                top_driver = bu_sga.loc[bu_sga["actual"].idxmax()]
                contrib_data.append({
                    "사업부": bu,
                    "실적 (억원)": f"{total_actual:,.0f}",
                    "계획 (억원)": f"{total_plan:,.0f}",
                    "Gap (억원)": f"{gap_abs:+,.0f}",
                    "Gap (%)": f"{gap_pct:+.1f}%",
                    "최대 비중 항목": sga_names.get(top_driver["kpi_id"], top_driver["kpi_id"]),
                })
            st.dataframe(pd.DataFrame(contrib_data), use_container_width=True, hide_index=True)
    else:
        st.info("SG&A Cost Pool 데이터가 없습니다.")


# ════════════════════════════════════════════════
# TAB 5: 생산성 Driver 분석
# ════════════════════════════════════════════════
with tab5:
    st.subheader("생산성 저하 Driver 분석")
    st.caption("생산성 저하의 근본 원인을 수요/가동률/프로세스 3축으로 분해합니다")

    kpi_vals_df5 = load_kpi_values(str(pd.Timestamp(analysis_month).date()))

    prod_drivers = {
        "PROD_DEMAND": {"name": "수요/수주", "icon": "📦", "color": "#2F5496",
                        "children": ["DEMAND_ORDER_RATE", "DEMAND_PIPELINE"]},
        "PROD_UTIL": {"name": "설비가동률", "icon": "⚙️", "color": "#548235",
                      "children": ["UTIL_PLANNED", "UTIL_DOWNTIME"]},
        "PROD_PROCESS": {"name": "프로세스 효율", "icon": "🔧", "color": "#BF8F00",
                         "children": ["PROC_YIELD", "PROC_CYCLE", "PROC_REWORK"]},
    }
    child_names = {
        "DEMAND_ORDER_RATE": "수주전환율", "DEMAND_PIPELINE": "파이프라인",
        "UTIL_PLANNED": "계획가동시간", "UTIL_DOWNTIME": "비계획정지",
        "PROC_YIELD": "공정수율", "PROC_CYCLE": "Cycle Time", "PROC_REWORK": "재작업률",
    }

    if not kpi_vals_df5.empty:
        # 생산성 종합 스코어
        prod_total = kpi_vals_df5[kpi_vals_df5["kpi_id"] == "PRODUCTIVITY"]
        if not prod_total.empty:
            col_m1, col_m2, col_m3 = st.columns(3)
            avg_actual = prod_total["actual"].mean()
            avg_plan = prod_total["plan"].mean()
            avg_gap = ((avg_actual / avg_plan) - 1) * 100 if avg_plan else 0
            col_m1.metric("종합 생산성", f"{avg_actual:.1f}점", f"{avg_gap:+.1f}%")

            for i, (drv_id, drv_info) in enumerate(prod_drivers.items()):
                drv_data = kpi_vals_df5[kpi_vals_df5["kpi_id"] == drv_id]
                if not drv_data.empty:
                    d_actual = drv_data["actual"].mean()
                    d_plan = drv_data["plan"].mean()
                    d_gap = ((d_actual / d_plan) - 1) * 100 if d_plan else 0
                    [col_m2, col_m3][i % 2].metric(
                        f"{drv_info['icon']} {drv_info['name']}", f"{d_actual:.1f}%", f"{d_gap:+.1f}%"
                    )

        # 3축 Driver 상세
        st.divider()
        drv_cols = st.columns(3)
        for col, (drv_id, drv_info) in zip(drv_cols, prod_drivers.items()):
            with col:
                st.markdown(f"#### {drv_info['icon']} {drv_info['name']}")

                # 사업부별 Bar
                drv_data = kpi_vals_df5[kpi_vals_df5["kpi_id"] == drv_id]
                if not drv_data.empty:
                    drv_data = drv_data.sort_values("gap_pct")
                    colors_drv = ["#C00000" if g < -5 else "#F58220" if g < -2 else "#548235"
                                  for g in drv_data["gap_pct"]]
                    fig_drv = go.Figure(go.Bar(
                        x=drv_data["bu_name"], y=drv_data["actual"],
                        marker_color=colors_drv,
                        text=[f"{v:.1f}" for v in drv_data["actual"]],
                        textposition="outside",
                    ))
                    fig_drv.update_layout(height=250, margin=dict(t=10, b=10),
                                          yaxis_title="%", showlegend=False)
                    st.plotly_chart(fig_drv, use_container_width=True)

                # 하위 Driver
                for child_id in drv_info["children"]:
                    child_data = kpi_vals_df5[kpi_vals_df5["kpi_id"] == child_id]
                    if not child_data.empty:
                        avg_val = child_data["actual"].mean()
                        avg_gap = child_data["gap_pct"].mean()
                        gap_icon = "🔴" if avg_gap < -5 else "🟡" if avg_gap < -2 else "🟢"
                        st.markdown(f"{gap_icon} **{child_names.get(child_id, child_id)}**: "
                                    f"{avg_val:.1f} ({avg_gap:+.1f}%)")

        # 사업부별 생산성 레이더 차트
        st.divider()
        st.markdown("#### 사업부별 생산성 프로파일")
        radar_data = []
        categories = list(prod_drivers.keys())
        cat_names = [d["name"] for d in prod_drivers.values()]

        for bu_id, bu_info in BUSINESS_UNITS.items():
            vals = []
            for cat_id in categories:
                cat_data = kpi_vals_df5[
                    (kpi_vals_df5["kpi_id"] == cat_id) & (kpi_vals_df5["bu_name"] == bu_info["name"])
                ]
                vals.append(cat_data["actual"].mean() if not cat_data.empty else 0)
            radar_data.append({"bu": bu_info["name"], "vals": vals, "color": bu_info["color"]})

        fig_radar = go.Figure()
        for rd in radar_data:
            fig_radar.add_trace(go.Scatterpolar(
                r=rd["vals"] + [rd["vals"][0]],
                theta=cat_names + [cat_names[0]],
                name=rd["bu"], line=dict(color=rd["color"], width=2),
                fill="toself", opacity=0.15,
            ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[50, 100])),
            height=400, margin=dict(t=30, b=30),
        )
        st.plotly_chart(fig_radar, use_container_width=True)
    else:
        st.info("생산성 데이터가 없습니다.")


# ════════════════════════════════════════════════
# TAB 6: 투자성과·ROIC 분석
# ════════════════════════════════════════════════
with tab6:
    st.subheader("투자 성과 미달 원인 & ROIC 기여도 분석")

    kpi_vals_df6 = load_kpi_values(str(pd.Timestamp(analysis_month).date()))

    if not kpi_vals_df6.empty:
        # ── ROIC 사업부별 기여도 ──
        st.markdown("### 포트폴리오 ROIC 기여도")
        st.caption("어느 사업이 ROIC 하락을 주도하는가?")

        roic_ids = ["ROIC_EPC", "ROIC_GREEN", "ROIC_RECYCLE", "ROIC_SOL"]
        roic_names = {"ROIC_EPC": "Hi-tech EPC", "ROIC_GREEN": "Green Energy",
                      "ROIC_RECYCLE": "Recycling", "ROIC_SOL": "Solution"}
        roic_data = kpi_vals_df6[kpi_vals_df6["kpi_id"].isin(roic_ids)]

        if not roic_data.empty:
            col_roic1, col_roic2 = st.columns(2)

            with col_roic1:
                # 기여도 Waterfall
                roic_summary = roic_data.groupby("kpi_id").agg(
                    actual=("actual", "mean"), plan=("plan", "mean")
                ).reset_index()
                roic_summary["name"] = roic_summary["kpi_id"].map(roic_names)
                roic_summary["gap"] = roic_summary["actual"] - roic_summary["plan"]
                roic_summary = roic_summary.sort_values("gap")

                total_gap = roic_summary["gap"].sum()
                fig_roic_w = go.Figure(go.Waterfall(
                    name="", orientation="v",
                    measure=["relative"] * len(roic_summary) + ["total"],
                    x=roic_summary["name"].tolist() + ["전사 ROIC Gap"],
                    y=roic_summary["gap"].tolist() + [total_gap],
                    text=[f"{v:+.2f}%p" for v in roic_summary["gap"]] + [f"{total_gap:+.2f}%p"],
                    textposition="outside",
                    increasing={"marker": {"color": "#2F5496"}},
                    decreasing={"marker": {"color": "#C00000"}},
                    totals={"marker": {"color": "#7030A0"}},
                    connector={"line": {"color": "rgb(63,63,63)"}},
                ))
                fig_roic_w.update_layout(height=380, margin=dict(t=30, b=30),
                                          yaxis_title="ROIC Gap (%p)",
                                          title="사업부별 ROIC Gap 기여 (Waterfall)")
                st.plotly_chart(fig_roic_w, use_container_width=True)

            with col_roic2:
                # 실적 vs 계획 비교
                fig_roic_bar = go.Figure()
                fig_roic_bar.add_trace(go.Bar(
                    x=roic_summary["name"], y=roic_summary["plan"],
                    name="계획 ROIC", marker_color="#D6E4F0",
                ))
                fig_roic_bar.add_trace(go.Bar(
                    x=roic_summary["name"], y=roic_summary["actual"],
                    name="실적 ROIC", marker_color="#2F5496",
                ))
                fig_roic_bar.update_layout(height=380, margin=dict(t=30, b=30),
                                            barmode="group", yaxis_title="ROIC (%)",
                                            title="사업부별 ROIC 실적 vs 계획")
                st.plotly_chart(fig_roic_bar, use_container_width=True)

        # ── 투자 성과 미달 원인 분석 ──
        st.divider()
        st.markdown("### 투자 성과 미달 원인 분석")
        st.caption("시장/집행/원가 3축으로 투자 프로젝트 부진 원인을 진단합니다")

        inv_cause_ids = ["INV_MARKET", "INV_EXEC", "INV_COST"]
        inv_cause_names = {"INV_MARKET": "시장요인", "INV_EXEC": "집행요인", "INV_COST": "원가요인"}
        inv_cause_colors = {"INV_MARKET": "#2F5496", "INV_EXEC": "#548235", "INV_COST": "#C00000"}
        inv_cause_icons = {"INV_MARKET": "📉", "INV_EXEC": "🏗️", "INV_COST": "💸"}

        inv_data = kpi_vals_df6[kpi_vals_df6["kpi_id"].isin(inv_cause_ids)]

        if not inv_data.empty:
            # 3축 요약 Metric
            cause_cols = st.columns(3)
            for col, cause_id in zip(cause_cols, inv_cause_ids):
                with col:
                    cause_data = inv_data[inv_data["kpi_id"] == cause_id]
                    avg_actual = cause_data["actual"].mean()
                    avg_plan = cause_data["plan"].mean()
                    avg_gap = ((avg_actual / avg_plan) - 1) * 100 if avg_plan else 0
                    st.metric(
                        f"{inv_cause_icons[cause_id]} {inv_cause_names[cause_id]}",
                        f"{avg_actual:.1f}점", f"{avg_gap:+.1f}%"
                    )

            # 사업부별 원인 히트맵
            st.markdown("#### 사업부 × 원인 진단 Matrix")
            inv_pivot = inv_data.pivot_table(
                index="bu_name", columns="kpi_id", values="gap_pct", aggfunc="mean"
            ).fillna(0)
            inv_pivot.columns = [inv_cause_names.get(c, c) for c in inv_pivot.columns]

            fig_inv_heat = go.Figure(go.Heatmap(
                z=inv_pivot.values * 100,
                x=inv_pivot.columns.tolist(),
                y=inv_pivot.index.tolist(),
                colorscale=[[0, "#C00000"], [0.5, "#FFFFD4"], [1, "#2F5496"]],
                zmid=0, texttemplate="%{z:.1f}%",
                hovertemplate="사업부: %{y}<br>원인: %{x}<br>Gap: %{z:.1f}%",
            ))
            fig_inv_heat.update_layout(height=280, margin=dict(t=10, b=10))
            st.plotly_chart(fig_inv_heat, use_container_width=True)

            # 원인별 하위 Driver 상세
            st.markdown("#### 원인별 상세 Driver")
            inv_children = {
                "INV_MARKET": [("INV_MKT_DEMAND", "수요 변동"), ("INV_MKT_PRICE", "판매단가 변동"),
                               ("INV_MKT_COMPETE", "경쟁 환경")],
                "INV_EXEC": [("INV_EXEC_RATE", "투자집행률"), ("INV_EXEC_DELAY", "일정 지연"),
                              ("INV_EXEC_PERMIT", "인허가 진척")],
                "INV_COST": [("INV_COST_MAT", "원자재 원가"), ("INV_COST_LABOR", "인건비 초과"),
                              ("INV_COST_DESIGN", "설계변경 비용")],
            }

            detail_cols = st.columns(3)
            for col, (parent_id, children) in zip(detail_cols, inv_children.items()):
                with col:
                    st.markdown(f"**{inv_cause_icons[parent_id]} {inv_cause_names[parent_id]}**")
                    for child_id, child_name in children:
                        child_data = kpi_vals_df6[kpi_vals_df6["kpi_id"] == child_id]
                        if not child_data.empty:
                            avg_val = child_data["actual"].mean()
                            avg_gap = child_data["gap_pct"].mean() * 100
                            severity = "🔴" if abs(avg_gap) > 10 else "🟡" if abs(avg_gap) > 5 else "🟢"
                            st.markdown(f"{severity} {child_name}: **{avg_val:.1f}** ({avg_gap:+.1f}%)")
                        else:
                            st.markdown(f"⚪ {child_name}: 데이터 없음")
    else:
        st.info("투자 성과 데이터가 없습니다.")
