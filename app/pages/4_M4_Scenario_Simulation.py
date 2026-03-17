"""M4. Scenario / What-if Simulation - 지주사 관점"""
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
st.caption("SK네트웍스 지주사 - 변수를 조정하여 계열사 포트폴리오 시나리오 시뮬레이션")

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
st.markdown("슬라이더를 조정하여 변수 변동에 따른 계열사별 영향을 확인하세요.")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**외부 환경 변수**")
    economy_change = st.slider("경기변동 영향 (%)", -15.0, 15.0, 0.0, 1.0, help="소비 심리, 경기 순환 영향")
    interest_change = st.slider("금리 변동 (%p)", -2.0, 2.0, 0.0, 0.25, help="기준금리 변동 → 렌탈/리스 수요 영향")
    competition = st.slider("경쟁 심화 (%)", -20.0, 0.0, 0.0, 1.0, help="시장 점유율 방어/잠식 효과")

with col2:
    st.markdown("**내부 운영 변수**")
    churn_improve = st.slider("이탈률 개선 (%)", -5.0, 5.0, 0.0, 0.5, help="고객 유지 정책 효과")
    cost_reduction = st.slider("비용 절감 목표 (%)", 0.0, 20.0, 0.0, 1.0)
    new_biz_invest = st.slider("신사업 추가 투자 (억원/월)", 0.0, 100.0, 0.0, 10.0)

st.divider()

# 시뮬레이션 계산
st.subheader("시뮬레이션 결과")

# 계열사별 민감도 설정
sensitivity = {
    "SK_Magic": {"economy": 0.3, "interest": 0.15, "competition": 0.5, "churn": 0.6},
    "SK_Rentacar": {"economy": 0.4, "interest": 0.4, "competition": 0.3, "churn": 0.4},
    "Mintit": {"economy": 0.5, "interest": 0.1, "competition": 0.4, "churn": 0.2},
    "Walkerhill": {"economy": 0.7, "interest": 0.1, "competition": 0.3, "churn": 0.1},
    "SKN_Service": {"economy": 0.2, "interest": 0.05, "competition": 0.4, "churn": 0.3},
}

results = []
for bu_id, row in base.iterrows():
    bu_name = BUSINESS_UNITS.get(bu_id, {}).get("name", bu_id)
    sens = sensitivity.get(bu_id, {"economy": 0.3, "interest": 0.2, "competition": 0.3, "churn": 0.3})

    # 매출 영향 계산
    rev_impact = (economy_change / 100 * sens["economy"]
                  + interest_change / 10 * sens["interest"] * -1  # 금리 상승 → 수요 감소
                  + competition / 100 * sens["competition"]
                  + churn_improve / 100 * sens["churn"] * -1)  # 이탈 개선 → 매출 증가

    new_revenue = row["revenue"] * (1 + rev_impact)
    new_cogs = row["cogs"] * (1 - cost_reduction / 100 * 0.3)
    new_opex = row["opex"] * (1 - cost_reduction / 100 * 0.5)
    new_ebitda = new_revenue - new_cogs - new_opex + row["ebitda"] - (row["revenue"] - row["cogs"] - row["opex"])
    new_capex = row["capex"] + new_biz_invest / len(BUSINESS_UNITS)

    results.append({
        "계열사": bu_name,
        "Base 매출": round(row["revenue"], 1),
        "시나리오 매출": round(new_revenue, 1),
        "매출 변동(%)": round((new_revenue / row["revenue"] - 1) * 100, 1),
        "Base EBITDA": round(row["ebitda"], 1),
        "시나리오 EBITDA": round(new_ebitda, 1),
        "EBITDA 변동(%)": round((new_ebitda / row["ebitda"] - 1) * 100, 1) if row["ebitda"] != 0 else 0,
        "CAPEX": round(new_capex, 1),
    })

result_df = pd.DataFrame(results)

# 연결 합계
totals = result_df[["Base 매출", "시나리오 매출", "Base EBITDA", "시나리오 EBITDA", "CAPEX"]].sum()

c1, c2, c3 = st.columns(3)
rev_delta = totals["시나리오 매출"] - totals["Base 매출"]
ebitda_delta = totals["시나리오 EBITDA"] - totals["Base EBITDA"]
c1.metric("연결매출 (월평균)", f'{totals["시나리오 매출"]:,.0f} 억원', f"{rev_delta:+,.0f}")
c2.metric("연결EBITDA (월평균)", f'{totals["시나리오 EBITDA"]:,.0f} 억원', f"{ebitda_delta:+,.0f}")
c3.metric("연결CAPEX (월평균)", f'{totals["CAPEX"]:,.0f} 억원')

st.dataframe(result_df, use_container_width=True, hide_index=True)

# 시나리오 비교 차트
col1, col2 = st.columns(2)
with col1:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=result_df["계열사"], y=result_df["Base EBITDA"], name="Base", marker_color="#D6E4F0"))
    fig.add_trace(go.Bar(x=result_df["계열사"], y=result_df["시나리오 EBITDA"], name="시나리오", marker_color="#2F5496"))
    fig.update_layout(title="EBITDA 비교 (Base vs 시나리오)", barmode="group", height=350)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    # 민감도 히트맵 (지주사 맞춤)
    variables = ["경기변동", "금리", "경쟁심화", "이탈률", "비용절감"]
    bus = list(result_df["계열사"])

    sensitivity_matrix = np.array([
        [0.3, 0.15, 0.5, 0.6, 0.4],  # SK매직
        [0.4, 0.40, 0.3, 0.4, 0.3],  # SK렌터카
        [0.5, 0.10, 0.4, 0.2, 0.3],  # 민팃
        [0.7, 0.10, 0.3, 0.1, 0.5],  # 워커힐
        [0.2, 0.05, 0.4, 0.3, 0.3],  # SK네트웍스서비스
    ])
    fig2 = go.Figure(go.Heatmap(
        z=sensitivity_matrix, x=variables, y=bus,
        colorscale="RdYlGn_r", text=np.round(sensitivity_matrix, 2), texttemplate="%{text}",
    ))
    fig2.update_layout(title="민감도 히트맵 (변수 → 계열사 영향도)", height=350)
    st.plotly_chart(fig2, use_container_width=True)
