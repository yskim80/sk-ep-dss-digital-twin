"""M1. Executive Dashboard - 경영진 종합 대시보드"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db.models import SessionLocal, Financial, BusinessUnit
from config.settings import BUSINESS_UNITS

st.set_page_config(page_title="M1. Executive Dashboard", page_icon="📊", layout="wide")
st.title("📊 M1. Executive Dashboard")
st.caption("경영진 핵심 재무/운영 지표 통합 대시보드")

@st.cache_data(ttl=300)
def load_financials():
    session = SessionLocal()
    try:
        rows = session.query(Financial).order_by(Financial.period).all()
        data = [{
            "bu_id": r.bu_id, "period": r.period,
            "revenue": r.revenue, "cogs": r.cogs, "gross_profit": r.gross_profit,
            "opex": r.opex, "ebitda": r.ebitda, "ebit": r.ebit,
            "capex": r.capex, "operating_cf": r.operating_cf, "backlog": r.backlog,
            "plan_revenue": r.plan_revenue, "plan_ebitda": r.plan_ebitda,
        } for r in rows]
        return pd.DataFrame(data)
    finally:
        session.close()

df = load_financials()
if df.empty:
    st.warning("데이터가 없습니다. seed_data.py를 먼저 실행하세요.")
    st.stop()

df["period"] = pd.to_datetime(df["period"])
df["bu_name"] = df["bu_id"].map({k: v["name"] for k, v in BUSINESS_UNITS.items()})

# Filters
col_f1, col_f2 = st.columns([1, 3])
with col_f1:
    selected_bus = st.multiselect(
        "사업부 선택", options=list(BUSINESS_UNITS.keys()),
        default=list(BUSINESS_UNITS.keys()),
        format_func=lambda x: BUSINESS_UNITS[x]["name"]
    )

filtered = df[df["bu_id"].isin(selected_bus)]

# Latest month summary
latest = filtered[filtered["period"] == filtered["period"].max()]
prev_month = filtered["period"].max() - pd.DateOffset(months=1)
prev = filtered[filtered["period"] == prev_month]

st.subheader("전사 핵심 지표 (최신 월)")
c1, c2, c3, c4, c5 = st.columns(5)

def calc_delta(curr_df, prev_df, col):
    curr_val = curr_df[col].sum()
    prev_val = prev_df[col].sum() if not prev_df.empty else curr_val
    delta = curr_val - prev_val
    return curr_val, delta

rev, rev_d = calc_delta(latest, prev, "revenue")
ebitda_v, ebitda_d = calc_delta(latest, prev, "ebitda")
ebit_v, ebit_d = calc_delta(latest, prev, "ebit")
capex_v, capex_d = calc_delta(latest, prev, "capex")
backlog_v, backlog_d = calc_delta(latest, prev, "backlog")

c1.metric("매출", f"{rev:,.0f} 억원", f"{rev_d:+,.0f}")
c2.metric("EBITDA", f"{ebitda_v:,.0f} 억원", f"{ebitda_d:+,.0f}")
c3.metric("영업이익", f"{ebit_v:,.0f} 억원", f"{ebit_d:+,.0f}")
c4.metric("CAPEX", f"{capex_v:,.0f} 억원", f"{capex_d:+,.0f}", delta_color="inverse")
c5.metric("수주잔고", f"{backlog_v:,.0f} 억원", f"{backlog_d:+,.0f}")

st.divider()

# Charts
col1, col2 = st.columns(2)

with col1:
    st.subheader("사업부별 매출 추이")
    monthly = filtered.groupby(["period", "bu_name"])["revenue"].sum().reset_index()
    fig1 = px.line(monthly, x="period", y="revenue", color="bu_name",
                   labels={"revenue": "매출 (억원)", "period": "", "bu_name": "사업부"})
    fig1.update_layout(height=350, margin=dict(t=20, b=20))
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.subheader("EBITDA: 실적 vs 계획")
    total_monthly = filtered.groupby("period")[["ebitda", "plan_ebitda"]].sum().reset_index()
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=total_monthly["period"], y=total_monthly["plan_ebitda"],
                          name="계획", marker_color="#D6E4F0"))
    fig2.add_trace(go.Bar(x=total_monthly["period"], y=total_monthly["ebitda"],
                          name="실적", marker_color="#2F5496"))
    fig2.update_layout(barmode="overlay", height=350, margin=dict(t=20, b=20),
                       yaxis_title="EBITDA (억원)")
    st.plotly_chart(fig2, use_container_width=True)

col3, col4 = st.columns(2)

with col3:
    st.subheader("사업부별 수익성 비교 (최신 월)")
    if not latest.empty:
        latest_summary = latest.groupby("bu_name").agg(
            revenue=("revenue", "sum"),
            ebitda=("ebitda", "sum"),
        ).reset_index()
        latest_summary["margin"] = (latest_summary["ebitda"] / latest_summary["revenue"] * 100).round(1)
        fig3 = px.bar(latest_summary, x="bu_name", y="margin", color="bu_name",
                      labels={"margin": "EBITDA Margin (%)", "bu_name": ""},
                      text="margin")
        fig3.update_layout(height=350, margin=dict(t=20, b=20), showlegend=False)
        st.plotly_chart(fig3, use_container_width=True)

with col4:
    st.subheader("매출 계획 달성률")
    if not latest.empty:
        achieve = latest.groupby("bu_name").agg(
            actual=("revenue", "sum"),
            plan=("plan_revenue", "sum"),
        ).reset_index()
        achieve["달성률"] = (achieve["actual"] / achieve["plan"] * 100).round(1)
        fig4 = px.bar(achieve, x="bu_name", y="달성률", color="bu_name",
                      text="달성률", labels={"bu_name": ""})
        fig4.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="목표 100%")
        fig4.update_layout(height=350, margin=dict(t=20, b=20), showlegend=False)
        st.plotly_chart(fig4, use_container_width=True)

# Gap Alert Table
st.subheader("⚠️ Gap Alert - 계획 대비 미달 항목")
if not latest.empty:
    gap_df = latest[["bu_name", "revenue", "plan_revenue", "ebitda", "plan_ebitda"]].copy()
    gap_df["매출 Gap"] = gap_df["revenue"] - gap_df["plan_revenue"]
    gap_df["매출 Gap(%)"] = ((gap_df["revenue"] / gap_df["plan_revenue"] - 1) * 100).round(1)
    gap_df["EBITDA Gap"] = gap_df["ebitda"] - gap_df["plan_ebitda"]
    gap_df["EBITDA Gap(%)"] = ((gap_df["ebitda"] / gap_df["plan_ebitda"] - 1) * 100).round(1)
    display_cols = ["bu_name", "revenue", "plan_revenue", "매출 Gap(%)", "ebitda", "plan_ebitda", "EBITDA Gap(%)"]
    gap_df = gap_df[display_cols].rename(columns={
        "bu_name": "사업부", "revenue": "매출(실적)", "plan_revenue": "매출(계획)",
        "ebitda": "EBITDA(실적)", "plan_ebitda": "EBITDA(계획)"
    })
    st.dataframe(gap_df, use_container_width=True, hide_index=True)
