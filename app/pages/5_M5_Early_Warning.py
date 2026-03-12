"""M5. Early Warning Center - 조기경보 센터"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db.models import SessionLocal, RiskItem, KPIValue
from config.settings import BUSINESS_UNITS

st.set_page_config(page_title="M5. Early Warning", page_icon="🚨", layout="wide")
st.title("🚨 M5. Early Warning Center")
st.caption("선행지표 이탈/패턴 변화 조기 감지 및 리스크 경보")

@st.cache_data(ttl=300)
def load_risks():
    session = SessionLocal()
    try:
        risks = session.query(RiskItem).all()
        return pd.DataFrame([{
            "bu_id": r.bu_id, "category": r.category,
            "description": r.description,
            "probability": r.probability, "impact": r.impact,
            "risk_score": r.risk_score, "status": r.status,
        } for r in risks])
    finally:
        session.close()

@st.cache_data(ttl=300)
def load_kpi_alerts():
    session = SessionLocal()
    try:
        vals = session.query(KPIValue).filter(KPIValue.gap_pct < -0.05).all()
        return pd.DataFrame([{
            "kpi_id": v.kpi_id, "bu_id": v.bu_id, "period": v.period,
            "actual": v.actual, "plan": v.plan, "gap_pct": v.gap_pct
        } for v in vals])
    finally:
        session.close()

risk_df = load_risks()
alert_df = load_kpi_alerts()

# Risk Heatmap
st.subheader("Risk Heatmap (사업부 x 리스크 유형)")

if not risk_df.empty:
    risk_df["bu_name"] = risk_df["bu_id"].map({k: v["name"] for k, v in BUSINESS_UNITS.items()})

    pivot = risk_df.pivot_table(
        values="risk_score", index="bu_name", columns="category", aggfunc="max"
    ).fillna(0)

    category_labels = {"market": "시장", "operational": "운영", "regulatory": "규제", "financial": "재무"}
    pivot = pivot.rename(columns=category_labels)

    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale=[[0, "#E8F5E9"], [0.3, "#FFF9C4"], [0.6, "#FFE0B2"], [1, "#FFCDD2"]],
        text=pivot.values.round(2), texttemplate="%{text}",
        zmin=0, zmax=1,
    ))
    fig.update_layout(height=300, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Risk Details
    st.subheader("활성 리스크 항목")
    risk_display = risk_df.sort_values("risk_score", ascending=False)
    risk_display["severity"] = risk_display["risk_score"].apply(
        lambda x: "🔴 High" if x > 0.5 else ("🟡 Medium" if x > 0.25 else "🟢 Low")
    )
    st.dataframe(
        risk_display[["bu_name", "category", "description", "probability", "impact", "risk_score", "severity"]]
        .rename(columns={
            "bu_name": "사업부", "category": "유형", "description": "설명",
            "probability": "발생확률", "impact": "영향도", "risk_score": "리스크점수", "severity": "심각도"
        }),
        use_container_width=True, hide_index=True
    )

st.divider()

# KPI 이탈 경보
st.subheader("⚠️ KPI 이탈 경보 (계획 대비 -5% 이상 미달)")

if not alert_df.empty:
    alert_df["bu_name"] = alert_df["bu_id"].map({k: v["name"] for k, v in BUSINESS_UNITS.items()})
    alert_df["period"] = pd.to_datetime(alert_df["period"])

    # 최근 3개월만
    recent_alerts = alert_df[alert_df["period"] >= alert_df["period"].max() - pd.DateOffset(months=2)]

    if not recent_alerts.empty:
        alert_summary = recent_alerts.groupby(["bu_name", "kpi_id"]).agg(
            count=("gap_pct", "count"),
            avg_gap=("gap_pct", "mean"),
        ).reset_index().sort_values("avg_gap")

        alert_summary["avg_gap_pct"] = (alert_summary["avg_gap"] * 100).round(1)

        fig2 = px.bar(
            alert_summary.head(15), x="avg_gap_pct", y="kpi_id",
            color="bu_name", orientation="h",
            labels={"avg_gap_pct": "평균 Gap (%)", "kpi_id": "KPI", "bu_name": "사업부"},
        )
        fig2.update_layout(height=400, margin=dict(t=20, b=20))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.success("최근 3개월 내 심각한 KPI 이탈이 없습니다.")
else:
    st.success("KPI 이탈 경보가 없습니다.")
