"""M4. Scenario / What-if Simulation"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db.models import SessionLocal, Financial
from config.settings import BUSINESS_UNITS

st.set_page_config(page_title="M4. Scenario Simulation", page_icon="🔮", layout="wide")
st.title("🔮 M4. Scenario / What-if Simulation")
st.caption("변수를 조정하여 미래 시나리오를 시뮬레이션하고 최적안 도출")

@st.cache_data(ttl=300)
def load_base_data():
    session = SessionLocal()
    try:
        fins = session.query(Financial).order_by(Financial.period).all()
        df = pd.DataFrame([{
            "bu_id": r.bu_id, "period": r.period,
            "revenue": r.revenue, "cogs": r.cogs, "opex": r.opex,
            "ebitda": r.ebitda, "capex": r.capex,
        } for r in fins])
        return df
    finally:
        session.close()

df = load_base_data()
if df.empty:
    st.warning("데이터가 없습니다.")
    st.stop()

df["period"] = pd.to_datetime(df["period"])

# 최근 6개월 평균을 Base로 사용
recent = df[df["period"] >= df["period"].max() - pd.DateOffset(months=5)]
base = recent.groupby("bu_id")[["revenue", "cogs", "opex", "ebitda", "capex"]].mean()

st.subheader("시나리오 변수 설정")
st.markdown("슬라이더를 조정하여 변수 변동에 따른 영향을 확인하세요.")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**외부 환경 변수**")
    fx_change = st.slider("환율 변동 (%)", -20.0, 20.0, 0.0, 1.0)
    material_change = st.slider("원자재가격 변동 (%)", -30.0, 30.0, 0.0, 1.0)
    demand_change = st.slider("수요 변동 (%)", -20.0, 20.0, 0.0, 1.0)

with col2:
    st.markdown("**내부 운영 변수**")
    cost_reduction = st.slider("비용 절감 목표 (%)", 0.0, 20.0, 0.0, 1.0)
    capex_adjust = st.slider("CAPEX 조정 (%)", -30.0, 30.0, 0.0, 1.0)
    price_adjust = st.slider("판매가격 조정 (%)", -10.0, 10.0, 0.0, 0.5)

st.divider()

# 시뮬레이션 계산
st.subheader("시뮬레이션 결과")

results = []
for bu_id, row in base.iterrows():
    bu_name = BUSINESS_UNITS.get(bu_id, {}).get("name", bu_id)
    bu_type = BUSINESS_UNITS.get(bu_id, {}).get("type", "")

    # 사업부 유형별 민감도 차이 반영
    fx_sensitivity = 0.3 if bu_type == "project" else 0.15  # EPC는 환율 영향 높음
    material_sensitivity = 0.5 if bu_type == "project" else 0.2

    new_revenue = row["revenue"] * (1 + demand_change / 100 + price_adjust / 100)
    new_cogs = row["cogs"] * (1 + material_change / 100 * material_sensitivity - cost_reduction / 100)
    new_cogs *= (1 + fx_change / 100 * fx_sensitivity)  # 환율 → 원가 영향
    new_opex = row["opex"] * (1 - cost_reduction / 100 * 0.5)
    new_ebitda = new_revenue - new_cogs - new_opex + row["ebitda"] - (row["revenue"] - row["cogs"] - row["opex"])
    new_capex = row["capex"] * (1 + capex_adjust / 100)

    results.append({
        "사업부": bu_name,
        "Base 매출": round(row["revenue"], 1),
        "시나리오 매출": round(new_revenue, 1),
        "매출 변동(%)": round((new_revenue / row["revenue"] - 1) * 100, 1),
        "Base EBITDA": round(row["ebitda"], 1),
        "시나리오 EBITDA": round(new_ebitda, 1),
        "EBITDA 변동(%)": round((new_ebitda / row["ebitda"] - 1) * 100, 1) if row["ebitda"] != 0 else 0,
        "CAPEX": round(new_capex, 1),
    })

result_df = pd.DataFrame(results)

# 전사 합계
totals = result_df[["Base 매출", "시나리오 매출", "Base EBITDA", "시나리오 EBITDA", "CAPEX"]].sum()

c1, c2, c3 = st.columns(3)
rev_delta = totals["시나리오 매출"] - totals["Base 매출"]
ebitda_delta = totals["시나리오 EBITDA"] - totals["Base EBITDA"]
c1.metric("전사 매출 (월평균)", f'{totals["시나리오 매출"]:,.0f} 억원', f"{rev_delta:+,.0f}")
c2.metric("전사 EBITDA (월평균)", f'{totals["시나리오 EBITDA"]:,.0f} 억원', f"{ebitda_delta:+,.0f}")
c3.metric("전사 CAPEX (월평균)", f'{totals["CAPEX"]:,.0f} 억원')

st.dataframe(result_df, use_container_width=True, hide_index=True)

# 시나리오 비교 차트
col1, col2 = st.columns(2)
with col1:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=result_df["사업부"], y=result_df["Base EBITDA"], name="Base", marker_color="#D6E4F0"))
    fig.add_trace(go.Bar(x=result_df["사업부"], y=result_df["시나리오 EBITDA"], name="시나리오", marker_color="#2F5496"))
    fig.update_layout(title="EBITDA 비교 (Base vs 시나리오)", barmode="group", height=350)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    # 민감도 히트맵
    variables = ["환율", "원자재", "수요", "비용절감", "CAPEX", "판매가"]
    bus = list(result_df["사업부"])

    # 간단한 민감도 계산 (±5% 영향도)
    sensitivity = np.array([
        [0.3, 0.5, 0.8, 0.3, 0.2, 0.7],   # EPC
        [0.15, 0.2, 0.6, 0.4, 0.7, 0.5],   # Green
        [0.15, 0.3, 0.5, 0.5, 0.5, 0.4],   # Recycling
        [0.1, 0.15, 0.7, 0.3, 0.2, 0.8],   # Solution
    ])
    fig2 = go.Figure(go.Heatmap(
        z=sensitivity, x=variables, y=bus,
        colorscale="RdYlGn_r", text=np.round(sensitivity, 2), texttemplate="%{text}",
    ))
    fig2.update_layout(title="민감도 히트맵 (변수 → 사업부 영향도)", height=350)
    st.plotly_chart(fig2, use_container_width=True)
