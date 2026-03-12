"""M5. Early Warning Center - 조기경보 센터"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db.models import SessionLocal, RiskItem, KPIValue, Project, EVMMonthly
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


# ════════════════════════════════════════════════
# EVM 기반 조기 경보
# ════════════════════════════════════════════════
st.divider()
st.subheader("📐 EVM 프로젝트 조기 경보")
st.caption("CPI/SPI < 0.95 주의, < 0.90 경고 | TCPI > 1.10 달성 곤란 | EAC > BAC 원가 초과")


@st.cache_data(ttl=300)
def load_evm_alerts():
    session = SessionLocal()
    try:
        projects = session.query(Project).all()
        alerts = []
        for proj in projects:
            evm_records = session.query(EVMMonthly).filter(
                EVMMonthly.project_id == proj.id
            ).order_by(EVMMonthly.month_seq.desc()).first()

            if not evm_records:
                continue

            e = evm_records
            proj_alerts = []

            # SPI 경보
            if e.spi < 0.90:
                proj_alerts.append(("🔴", "SPI 경고", f"SPI={e.spi:.3f} (공정 심각 지연)"))
            elif e.spi < 0.95:
                proj_alerts.append(("🟡", "SPI 주의", f"SPI={e.spi:.3f} (공정 지연)"))

            # CPI 경보
            if e.cpi < 0.90:
                proj_alerts.append(("🔴", "CPI 경고", f"CPI={e.cpi:.3f} (원가 심각 초과)"))
            elif e.cpi < 0.95:
                proj_alerts.append(("🟡", "CPI 주의", f"CPI={e.cpi:.3f} (원가 초과)"))

            # SPI(t) 경보
            if e.es_spi_t < 0.90:
                proj_alerts.append(("🔴", "SPI(t) 경고", f"SPI(t)={e.es_spi_t:.3f} (ES 기반 심각 지연)"))
            elif e.es_spi_t < 0.95:
                proj_alerts.append(("🟡", "SPI(t) 주의", f"SPI(t)={e.es_spi_t:.3f} (ES 기반 지연)"))

            # TCPI 경보
            if e.tcpi > 1.10:
                proj_alerts.append(("🔴", "TCPI 경고", f"TCPI={e.tcpi:.3f} (예산 내 완료 곤란)"))
            elif e.tcpi > 1.05:
                proj_alerts.append(("🟡", "TCPI 주의", f"TCPI={e.tcpi:.3f} (예산 여유 부족)"))

            # EAC > BAC
            if e.vac < 0:
                pct = (e.eac / proj.bac - 1) * 100
                severity = "🔴" if pct > 10 else "🟡"
                proj_alerts.append((severity, "EAC 초과",
                                    f"EAC={e.eac:,.0f}억 > BAC={proj.bac:,.0f}억 ({pct:+.1f}%)"))

            for icon, alert_type, detail in proj_alerts:
                alerts.append({
                    "심각도": icon,
                    "프로젝트": proj.name,
                    "경보 유형": alert_type,
                    "상세": detail,
                    "공정률": f"{e.ev_rate:.1f}%",
                    "경과월": f"{e.month_seq}개월",
                })

        return pd.DataFrame(alerts) if alerts else pd.DataFrame()
    finally:
        session.close()


evm_alert_df = load_evm_alerts()

if not evm_alert_df.empty:
    # 요약
    red_count = (evm_alert_df["심각도"] == "🔴").sum()
    yellow_count = (evm_alert_df["심각도"] == "🟡").sum()
    alert_projects = evm_alert_df["프로젝트"].nunique()

    acol1, acol2, acol3 = st.columns(3)
    acol1.metric("경고 (🔴)", f"{red_count}건")
    acol2.metric("주의 (🟡)", f"{yellow_count}건")
    acol3.metric("경보 프로젝트", f"{alert_projects}건")

    st.dataframe(
        evm_alert_df.sort_values("심각도"),
        use_container_width=True, hide_index=True,
    )
else:
    st.success("EVM 기반 경보가 없습니다. 모든 프로젝트가 정상 범위 내입니다.")
