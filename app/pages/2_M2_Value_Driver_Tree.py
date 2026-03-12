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
        kpi_alias_map = {
            "UTIL": "O-011", "CCC": "O-021", "FX_RISK": "R-002",
            "ESG_SCORE": "R-004", "SAFETY": "R-006", "IRR": "I-003",
        }
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
tab1, tab2, tab3 = st.tabs(["Driver Tree (Interactive)", "EBITDA Waterfall", "KPI Drill-down"])


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
            tree_df = tree_df[tree_df["category"] == area_filter]

        # KPI별 Gap 데이터 집계 (전사 평균)
        gap_map = {}
        if not kpi_vals_df.empty:
            for kpi_id, grp in kpi_vals_df.groupby("kpi_id"):
                gap_map[kpi_id] = {
                    "avg_gap": round(grp["gap_pct"].mean(), 1),
                    "actual_avg": round(grp["actual"].mean(), 2),
                    "plan_avg": round(grp["plan"].mean(), 2),
                }

        # 재무 데이터에서 파생 KPI 값 계산
        if not current.empty:
            c = current
            p = previous if not previous.empty else current
            c_sum = c[["revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit",
                        "capex", "operating_cf", "backlog", "plan_revenue", "plan_ebitda"]].sum()
            p_sum = p[["revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit",
                        "capex", "operating_cf", "backlog", "plan_revenue", "plan_ebitda"]].sum()

            # 재무 파생 KPI
            fin_derived = {
                "P-001": {"val": c_sum["ebitda"], "gap": (c_sum["ebitda"]/c_sum["plan_ebitda"]-1)*100 if c_sum["plan_ebitda"] else 0, "unit": "억원"},
                "P-011": {"val": c_sum["revenue"], "gap": (c_sum["revenue"]/c_sum["plan_revenue"]-1)*100 if c_sum["plan_revenue"] else 0, "unit": "억원"},
                "P-012": {"val": c_sum["cogs"], "gap": ((c_sum["cogs"]/c_sum["revenue"])-(p_sum["cogs"]/p_sum["revenue"]))*100 if p_sum["revenue"] else 0, "unit": "억원"},
                "P-013": {"val": round((c_sum["gross_profit"]/c_sum["revenue"])*100, 1) if c_sum["revenue"] else 0, "gap": 0, "unit": "%"},
                "P-014": {"val": round((c_sum["opex"]/c_sum["revenue"])*100, 1) if c_sum["revenue"] else 0, "gap": 0, "unit": "%"},
                "P-004": {"val": c_sum["operating_cf"] - c_sum["capex"], "gap": 0, "unit": "억원"},
                "O-023": {"val": c_sum["backlog"], "gap": 0, "unit": "억원"},
            }
            # 사업부별 매출
            for bu_id, bu_info in BUSINESS_UNITS.items():
                bu_data = current[current["bu_id"] == bu_id]
                if not bu_data.empty:
                    bu_map = {"EPC_Hitech": "P-021", "GreenEnergy": "P-022", "Recycling": "P-023", "Solution": "P-024"}
                    if bu_id in bu_map:
                        rev = bu_data["revenue"].sum()
                        plan_rev = bu_data["plan_revenue"].sum()
                        fin_derived[bu_map[bu_id]] = {
                            "val": rev,
                            "gap": round((rev/plan_rev - 1)*100, 1) if plan_rev else 0,
                            "unit": "억원",
                        }
        else:
            fin_derived = {}

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
    orient = "TB" if is_single_area else "LR"
    chart_height = 700 if is_single_area else 900

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
            "symbolSize": [120, 40] if is_single_area else [100, 35],
            "edgeShape": "polyline",
            "edgeForkPosition": "63%",
            "initialTreeDepth": 3 if is_single_area else 2,
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

        # 재무 기반 추세 (성과 KPI)
        fin_kpi_map = {
            "P-001": "ebitda", "P-004": None,  # FCF = operating_cf - capex
            "O-023": "backlog",
        }

        if selected_kpi in fin_kpi_map:
            col_name = fin_kpi_map[selected_kpi]
            if col_name:
                trend_data = fin_df.groupby("period")[col_name].sum().reset_index()
                trend_data.columns = ["period", "value"]
            elif selected_kpi == "P-004":  # FCF
                trend_data = fin_df.groupby("period").agg(
                    ocf=("operating_cf", "sum"), capex=("capex", "sum")
                ).reset_index()
                trend_data["value"] = trend_data["ocf"] - trend_data["capex"]
                trend_data = trend_data[["period", "value"]]
            else:
                trend_data = pd.DataFrame()

            if not trend_data.empty:
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(
                    x=trend_data["period"], y=trend_data["value"],
                    mode="lines+markers", name=kpi_info["name"],
                    line=dict(color="#2F5496", width=2),
                    marker=dict(size=6),
                ))
                fig_trend.update_layout(
                    height=300, margin=dict(t=20, b=20),
                    yaxis_title=f"{kpi_info['unit']}",
                    xaxis_title="",
                )
                st.plotly_chart(fig_trend, use_container_width=True)

        # KPI 값이 있는 경우 사업부별 비교
        if not kpi_vals_df.empty:
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
                        name="실적", marker_color="#2F5496",
                    ))
                    fig_bar.update_layout(
                        barmode="group", height=300,
                        margin=dict(t=20, b=20),
                        yaxis_title=kpi_info["unit"],
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

                with col_table:
                    display_df = kpi_data[["bu_name", "actual", "plan", "gap_pct"]].rename(columns={
                        "bu_name": "사업부", "actual": "실적", "plan": "계획", "gap_pct": "Gap(%)"
                    })
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Driver 하위 구조 표시
        children = tree_df[tree_df["parent"] == selected_kpi]
        if not children.empty:
            st.markdown("#### Driver 분해 구조")
            for _, child in children.iterrows():
                # 값 표시
                val_str = ""
                if not kpi_vals_df.empty:
                    child_data = kpi_vals_df[kpi_vals_df["kpi_id"] == child["id"]]
                    if not child_data.empty:
                        avg_actual = child_data["actual"].mean()
                        avg_gap = child_data["gap_pct"].mean()
                        val_str = f"  |  실적: {avg_actual:.1f} {child['unit']} (Gap: {avg_gap:+.1f}%)"

                grandchildren = tree_df[tree_df["parent"] == child["id"]]

                with st.expander(f"L1: {child['name']} ({child['id']}){val_str}", expanded=True):
                    st.markdown(f"**산식:** {child['formula']}  |  **단위:** {child['unit']}")

                    if not grandchildren.empty:
                        for _, gc in grandchildren.iterrows():
                            gc_val_str = ""
                            if not kpi_vals_df.empty:
                                gc_data = kpi_vals_df[kpi_vals_df["kpi_id"] == gc["id"]]
                                if not gc_data.empty:
                                    gc_val_str = f" -> 실적: {gc_data['actual'].mean():.1f} (Gap: {gc_data['gap_pct'].mean():+.1f}%)"
                            st.markdown(f"- **L2: {gc['name']}** ({gc['id']}): {gc['formula']}{gc_val_str}")

                    # 사업부별 상세
                    if not kpi_vals_df.empty:
                        child_vals = kpi_vals_df[kpi_vals_df["kpi_id"] == child["id"]]
                        if not child_vals.empty:
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
