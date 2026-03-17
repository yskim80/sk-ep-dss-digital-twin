"""
M6. Portfolio Management - 지주사 투자 포트폴리오 관리 (AI Agent 적용)
  1) 마켓 & 딜 센싱 AI Agent
  2) 딜 스크리닝 & IC 지원 AI Agent
  3) 성과 모니터링 + Forecasting + Exit (Smart Monitoring Agent)
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys, json, hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.models import SessionLocal, PortfolioHolding, InvestmentProject, Financial, KPIValue
from config.settings import BUSINESS_UNITS

st.set_page_config(page_title="M6. Portfolio Management", page_icon="💼", layout="wide")
from db_init import ensure_db; ensure_db()
st.title("💼 M6. Portfolio Management")
st.caption("SK네트웍스 지주사 — AI 기반 투자 포트폴리오 의사결정 지원")

BU_NAME_MAP = {k: v["name"] for k, v in BUSINESS_UNITS.items()}
BU_COLOR_MAP = {v["name"]: v["color"] for v in BUSINESS_UNITS.values()}
BU_COLOR_MAP_ID = {k: v["color"] for k, v in BUSINESS_UNITS.items()}
CATEGORY_LABELS = {"core": "핵심사업", "growth": "성장사업", "new_biz": "신사업"}
STATUS_LABELS = {"planning": "기획중", "in_progress": "진행중", "completed": "완료", "on_hold": "보류"}
STAGE_LABELS = {"ideation": "아이디어", "feasibility": "타당성검토", "execution": "실행", "monitoring": "모니터링"}


# ══════════════════════════════════════════
# Data Loading
# ══════════════════════════════════════════
@st.cache_data(ttl=300)
def load_portfolio():
    session = SessionLocal()
    try:
        rows = session.query(PortfolioHolding).order_by(PortfolioHolding.period).all()
        return pd.DataFrame([{
            "bu_id": r.bu_id, "period": r.period,
            "stake_pct": r.stake_pct, "book_value": r.book_value,
            "fair_value": r.fair_value, "invested_amount": r.invested_amount,
            "equity_income": r.equity_income, "dividend_received": r.dividend_received,
            "roic": r.roic, "irr": r.irr,
            "category": r.category, "valuation_method": r.valuation_method,
        } for r in rows])
    finally:
        session.close()


@st.cache_data(ttl=300)
def load_projects():
    session = SessionLocal()
    try:
        rows = session.query(InvestmentProject).all()
        return pd.DataFrame([{
            "id": r.id, "name": r.name, "bu_id": r.bu_id,
            "category": r.category, "total_budget": r.total_budget,
            "spent_amount": r.spent_amount, "expected_irr": r.expected_irr,
            "expected_payback": r.expected_payback,
            "start_date": r.start_date, "target_completion": r.target_completion,
            "status": r.status, "risk_level": r.risk_level,
            "description": r.description, "stage": r.stage,
        } for r in rows])
    finally:
        session.close()


@st.cache_data(ttl=300)
def load_financials():
    session = SessionLocal()
    try:
        rows = session.query(Financial).order_by(Financial.period).all()
        return pd.DataFrame([{
            "bu_id": r.bu_id, "period": r.period,
            "revenue": r.revenue, "ebitda": r.ebitda, "ebit": r.ebit,
            "capex": r.capex, "operating_cf": r.operating_cf,
            "gross_profit": r.gross_profit, "opex": r.opex,
            "plan_revenue": r.plan_revenue, "plan_ebitda": r.plan_ebitda,
        } for r in rows])
    finally:
        session.close()


@st.cache_data(ttl=300)
def load_kpi_values():
    session = SessionLocal()
    try:
        inv_kpis = [
            "INV_PERF", "PORTFOLIO_VAL", "EQUITY_INCOME", "DIV_YIELD",
            "PV_MAGIC", "PV_RENT", "PV_MINTIT", "PV_WALKER",
            "NEW_BIZ", "NB_CAPEX", "NB_IRR", "NB_PAYBACK",
            "NB_AI", "NB_MOBILITY", "NB_PLATFORM",
        ]
        rows = session.query(KPIValue).filter(KPIValue.kpi_id.in_(inv_kpis)).all()
        return pd.DataFrame([{
            "kpi_id": r.kpi_id, "bu_id": r.bu_id, "period": r.period,
            "actual": r.actual, "plan": r.plan, "gap": r.gap, "gap_pct": r.gap_pct,
        } for r in rows])
    finally:
        session.close()


port_df = load_portfolio()
proj_df = load_projects()
fin_df = load_financials()
kpi_df = load_kpi_values()

if port_df.empty:
    st.warning("포트폴리오 데이터가 없습니다. 데이터를 재생성해주세요.")
    st.stop()

port_df["period"] = pd.to_datetime(port_df["period"])
port_df["bu_name"] = port_df["bu_id"].map(BU_NAME_MAP)
fin_df["period"] = pd.to_datetime(fin_df["period"])
fin_df["bu_name"] = fin_df["bu_id"].map(BU_NAME_MAP)
kpi_df["period"] = pd.to_datetime(kpi_df["period"])

latest = port_df[port_df["period"] == port_df["period"].max()]
prev_month = port_df["period"].max() - pd.DateOffset(months=1)
prev = port_df[port_df["period"] == prev_month]


# ══════════════════════════════════════════
# AI Agent 시뮬레이션 유틸리티
# ══════════════════════════════════════════
def ai_agent_badge(agent_name, status="running"):
    """AI Agent 실행 상태 배지"""
    colors = {"running": "#4CAF50", "complete": "#2196F3", "warning": "#FF9800"}
    icons = {"running": "⚡", "complete": "✅", "warning": "⚠️"}
    return f'<span style="background:{colors[status]}; color:#fff; padding:2px 8px; border-radius:12px; font-size:0.75rem;">{icons[status]} {agent_name}</span>'


def deterministic_score(seed_str, low, high):
    """문자열 기반 결정적 난수 (세션 간 일관성)"""
    h = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    return low + (h % 1000) / 1000 * (high - low)


# ══════════════════════════════════════════
# Flow Diagram (AI 적용 업무 흐름)
# ══════════════════════════════════════════
st.markdown("""
<div style="padding: 1rem; border-radius: 10px; border: 1px solid rgba(128,128,128,0.3); margin-bottom: 1rem;">
<h4 style="margin-top: 0;">AI 기반 Portfolio Management — To-be Flow</h4>
<div style="display: flex; gap: 0.4rem; align-items: stretch; flex-wrap: wrap;">
  <div style="flex: 1; min-width: 140px; background: #1565C0; border-radius: 8px; padding: 0.7rem; text-align: center;">
    <b style="color: #FFFFFF; font-size: 0.9rem;">마켓 & 딜 센싱</b><br/>
    <span style="font-size: 0.72rem; color: #BBDEFB;">섹터 스캔 → Long-list<br/>→ 우선순위화</span><br/>
    <span style="background: #0D47A1; color: #90CAF9; padding: 1px 6px; border-radius: 10px; font-size: 0.65rem;">AI 센싱 Agent</span>
  </div>
  <div style="flex: 0; display: flex; align-items: center; font-size: 1.2rem; color: #888;">▸</div>
  <div style="flex: 1; min-width: 140px; background: #E65100; border-radius: 8px; padding: 0.7rem; text-align: center;">
    <b style="color: #FFFFFF; font-size: 0.9rem;">딜 스크리닝</b><br/>
    <span style="font-size: 0.72rem; color: #FFE0B2;">리서치 → 리스크 점검<br/>→ Memo 초안</span><br/>
    <span style="background: #BF360C; color: #FFCCBC; padding: 1px 6px; border-radius: 10px; font-size: 0.65rem;">AI 스크리닝 Agent</span>
  </div>
  <div style="flex: 0; display: flex; align-items: center; font-size: 1.2rem; color: #888;">▸</div>
  <div style="flex: 1; min-width: 140px; background: #6A1B9A; border-radius: 8px; padding: 0.7rem; text-align: center;">
    <b style="color: #FFFFFF; font-size: 0.9rem;">IC 지원</b><br/>
    <span style="font-size: 0.72rem; color: #E1BEE7;">Memo 검수 → Q&A<br/>→ Red/Blue Team</span><br/>
    <span style="background: #4A148C; color: #CE93D8; padding: 1px 6px; border-radius: 10px; font-size: 0.65rem;">AI IC Agent</span>
  </div>
  <div style="flex: 0; display: flex; align-items: center; font-size: 1.2rem; color: #888;">▸</div>
  <div style="flex: 1; min-width: 140px; background: #2E7D32; border-radius: 8px; padding: 0.7rem; text-align: center;">
    <b style="color: #FFFFFF; font-size: 0.9rem;">성과 모니터링</b><br/>
    <span style="font-size: 0.72rem; color: #C8E6C9;">자동 연동 → 이상감지<br/>→ Forecasting</span><br/>
    <span style="background: #1B5E20; color: #A5D6A7; padding: 1px 6px; border-radius: 10px; font-size: 0.65rem;">Smart Monitor Agent</span>
  </div>
  <div style="flex: 0; display: flex; align-items: center; font-size: 1.2rem; color: #888;">▸</div>
  <div style="flex: 1; min-width: 140px; background: #C62828; border-radius: 8px; padding: 0.7rem; text-align: center;">
    <b style="color: #FFFFFF; font-size: 0.9rem;">Exit 관리</b><br/>
    <span style="font-size: 0.72rem; color: #FFCDD2;">Valuation 도출<br/>→ 전략 수립</span><br/>
    <span style="background: #B71C1C; color: #EF9A9A; padding: 1px 6px; border-radius: 10px; font-size: 0.65rem;">AI Exit Agent</span>
  </div>
</div>
<div style="margin-top: 0.6rem; padding: 0.5rem; background: #263238; border-radius: 6px; text-align: center;">
  <span style="color: #B0BEC5; font-size: 0.78rem;">LLM 기반 통합 AI Intelligence 플랫폼</span>
  <span style="color: #78909C; font-size: 0.7rem;"> | 외부: Macro/마켓/공시 데이터 | 내부: ERP/CRM/IC메모/CDD·FDD 자료</span>
</div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════
# Tabs
# ══════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    "📊 포트폴리오 Overview",
    "🤖 AI 마켓 & 딜 센싱",
    "📝 AI 딜 스크리닝 & IC",
    "🔍 성과 모니터링 & 이상신호",
    "🎯 예측 Lever & Forecasting",
    "📈 성과 Projection",
    "🚪 Exit 관리 & Valuation",
    "🏗️ 신규투자 Pipeline",
    "⚖️ 포트폴리오 최적화",
    "🧠 포트폴리오 AI Engine",
])


# ════════════════════════════════════════════
# TAB 1: 포트폴리오 Overview
# ════════════════════════════════════════════
with tab1:
    total_fair = latest["fair_value"].sum()
    total_book = latest["book_value"].sum()
    total_eq_income = latest["equity_income"].sum()
    total_invested = latest["invested_amount"].sum()
    prev_fair = prev["fair_value"].sum() if not prev.empty else total_fair

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("포트폴리오 공정가치", f"{total_fair:,.0f} 억원",
                f"{total_fair - prev_fair:+,.0f}")
    col2.metric("장부가치 합계", f"{total_book:,.0f} 억원")
    col3.metric("누적 투자금", f"{total_invested:,.0f} 억원")
    col4.metric("지분법이익 (월)", f"{total_eq_income:,.0f} 억원")
    col5.metric("NAV Premium",
                f"{((total_fair / total_book - 1) * 100):+.1f}%")

    st.divider()

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("계열사별 포트폴리오 비중")
        pie_data = latest[["bu_name", "fair_value"]].copy()
        fig_pie = px.pie(pie_data, values="fair_value", names="bu_name",
                         color="bu_name", color_discrete_map=BU_COLOR_MAP, hole=0.4)
        fig_pie.update_traces(textposition="inside", textinfo="label+percent")
        fig_pie.update_layout(height=380, margin=dict(t=20, b=20), showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_right:
        st.subheader("사업유형별 자산배분")
        cat_data = latest.groupby("category").agg(fair_value=("fair_value", "sum")).reset_index()
        cat_data["category_name"] = cat_data["category"].map(CATEGORY_LABELS)
        cat_colors = {"핵심사업": "#2F5496", "성장사업": "#BF8F00", "신사업": "#548235"}
        fig_cat = px.bar(cat_data, x="category_name", y="fair_value", color="category_name",
                         color_discrete_map=cat_colors,
                         text=cat_data["fair_value"].apply(lambda x: f"{x:,.0f}"),
                         labels={"fair_value": "공정가치 (억원)", "category_name": ""})
        fig_cat.update_layout(height=380, margin=dict(t=20, b=20), showlegend=False)
        st.plotly_chart(fig_cat, use_container_width=True)

    st.divider()
    st.subheader("계열사별 투자 현황 상세")
    detail = latest[["bu_name", "stake_pct", "invested_amount", "book_value", "fair_value",
                      "equity_income", "roic", "irr", "category", "valuation_method"]].copy()
    detail["category"] = detail["category"].map(CATEGORY_LABELS)
    detail["premium_pct"] = ((detail["fair_value"] / detail["book_value"] - 1) * 100).round(1)
    detail = detail.rename(columns={
        "bu_name": "계열사", "stake_pct": "지분율(%)", "invested_amount": "투자금(억원)",
        "book_value": "장부가(억원)", "fair_value": "공정가치(억원)",
        "equity_income": "지분법이익(억원)", "roic": "ROIC(%)", "irr": "IRR(%)",
        "category": "분류", "valuation_method": "밸류에이션", "premium_pct": "Premium(%)"
    })
    st.dataframe(detail, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════
# TAB 2: AI 마켓 & 딜 센싱
# ════════════════════════════════════════════
with tab2:
    st.markdown(f"""
    {ai_agent_badge("마켓 센싱 Agent", "running")}
    {ai_agent_badge("섹터 Intel Agent", "running")}
    {ai_agent_badge("Long-list Agent", "complete")}
    """, unsafe_allow_html=True)
    st.markdown("AI Agent가 외부 데이터(Macro, 마켓, 공시)를 실시간 수집·분석하여 유망 섹터와 투자 타겟을 도출합니다.")

    st.divider()

    # ── 2-1: 유망 섹터 센싱 ──
    st.subheader("유망 섹터 AI 스캔")

    sectors = [
        {"섹터": "AI/반도체", "매력도": 92, "성장률": "+34.2%", "시장규모": "2,340조원",
         "AI 판단": "매우 유망 — GPU/HBM 수요 폭증, SK하이닉스 수혜",
         "관련 계열사": "SK네트웍스서비스 (ICT인프라)", "시그널": "Strong Buy"},
        {"섹터": "친환경 모빌리티", "매력도": 85, "성장률": "+28.5%", "시장규모": "580조원",
         "AI 판단": "유망 — EV 전환 가속, 충전 인프라 투자 확대",
         "관련 계열사": "SK렌터카 (EV 전환)", "시그널": "Buy"},
        {"섹터": "구독경제/렌탈", "매력도": 78, "성장률": "+12.8%", "시장규모": "42조원",
         "AI 판단": "안정 — 정수기/공기청정기 성숙기, IoT 연계 성장",
         "관련 계열사": "SK매직 (핵심)", "시그널": "Hold"},
        {"섹터": "리커머스/순환경제", "매력도": 81, "성장률": "+22.3%", "시장규모": "28조원",
         "AI 판단": "유망 — ESG 규제 강화, 중고 거래 플랫폼 성장",
         "관련 계열사": "민팃 (핵심)", "시그널": "Buy"},
        {"섹터": "호텔/레저", "매력도": 65, "성장률": "+8.2%", "시장규모": "35조원",
         "AI 판단": "보통 — 경기 민감, 프리미엄 세그먼트 차별화 필요",
         "관련 계열사": "워커힐 (핵심)", "시그널": "Neutral"},
        {"섹터": "데이터센터/클라우드", "매력도": 88, "성장률": "+31.0%", "시장규모": "120조원",
         "AI 판단": "매우 유망 — AI 인프라 수요 급증, 부지 확보 경쟁",
         "관련 계열사": "신규 진출 검토", "시그널": "Strong Buy"},
    ]
    sector_df = pd.DataFrame(sectors)

    col_left, col_right = st.columns([2, 1])
    with col_left:
        fig_sector = px.bar(sector_df, x="섹터", y="매력도", color="매력도",
                            color_continuous_scale=["#FFCDD2", "#EF5350", "#C62828"],
                            text="시그널")
        fig_sector.update_traces(textposition="outside")
        fig_sector.add_hline(y=80, line_dash="dash", line_color="#4CAF50",
                             annotation_text="투자 적격 기준 (80)")
        fig_sector.update_layout(height=400, margin=dict(t=20, b=20), coloraxis_showscale=False)
        st.plotly_chart(fig_sector, use_container_width=True)

    with col_right:
        st.markdown("**AI 마켓 시그널 요약**")
        for s in sectors:
            signal_color = {"Strong Buy": "🟢", "Buy": "🟢", "Hold": "🟡", "Neutral": "🟡"}.get(s["시그널"], "⚪")
            st.markdown(f"{signal_color} **{s['섹터']}** ({s['시그널']})<br/>"
                       f"<span style='font-size:0.8rem; opacity:0.8'>{s['AI 판단']}</span>",
                       unsafe_allow_html=True)

    st.divider()

    # ── 2-2: 딜 Long-list ──
    st.subheader("AI 생성 — 투자 타겟 Long-list")
    st.markdown(f"{ai_agent_badge('Long-list 도출 Agent', 'complete')} 네트워크 기반 유망 타겟 자동 도출",
                unsafe_allow_html=True)

    targets = pd.DataFrame([
        {"순위": 1, "타겟": "A사 (AI로봇 스타트업)", "섹터": "AI/반도체", "예상 밸류": "3,000억원",
         "매력도": 88, "리스크": "중", "추천사유": "자율주행 물류 로봇 핵심 기술 보유, 시리즈C 예정"},
        {"순위": 2, "타겟": "B사 (EV충전 플랫폼)", "섹터": "친환경 모빌리티", "예상 밸류": "1,500억원",
         "매력도": 84, "리스크": "중", "추천사유": "전국 충전소 네트워크 3위, SK렌터카 시너지"},
        {"순위": 3, "타겟": "C사 (스마트홈 IoT)", "섹터": "구독경제/렌탈", "예상 밸류": "800억원",
         "매력도": 79, "리스크": "낮", "추천사유": "SK매직 렌탈 IoT 연계, ARR 고성장"},
        {"순위": 4, "타겟": "D사 (데이터센터 부지)", "섹터": "데이터센터/클라우드", "예상 밸류": "5,000억원",
         "매력도": 82, "리스크": "높", "추천사유": "수도권 대형 부지 확보, GPU 클러스터 가능"},
        {"순위": 5, "타겟": "E사 (중고 가전 리퍼비시)", "섹터": "리커머스/순환경제", "예상 밸류": "500억원",
         "매력도": 76, "리스크": "낮", "추천사유": "민팃 사업 확장 시너지, ESG 가치"},
    ])
    targets["리스크"] = targets["리스크"].map({"낮": "🟢 낮", "중": "🟡 중", "높": "🔴 높"})
    st.dataframe(targets, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════
# TAB 3: AI 딜 스크리닝 & IC 지원
# ════════════════════════════════════════════
with tab3:
    st.markdown(f"""
    {ai_agent_badge("딜 스크리닝 Agent", "running")}
    {ai_agent_badge("리스크 판단 Agent", "running")}
    {ai_agent_badge("IC Memo Agent", "complete")}
    {ai_agent_badge("Red/Blue Team Agent", "warning")}
    """, unsafe_allow_html=True)

    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["📋 딜 스크리닝", "📄 IC Memo 생성", "⚔️ Red/Blue Team"])

    # ── 3-1: 딜 스크리닝 ──
    with sub_tab1:
        st.subheader("AI 딜 스크리닝 — 타겟 심층 분석")

        target_sel = st.selectbox("분석할 타겟 선택", [
            "A사 (AI로봇 스타트업)", "B사 (EV충전 플랫폼)", "C사 (스마트홈 IoT)",
            "D사 (데이터센터 부지)", "E사 (중고 가전 리퍼비시)"
        ])

        if st.button("AI 스크리닝 실행", key="screening_btn"):
            with st.spinner("AI Agent가 타겟 정보를 수집·분석 중..."):
                import time
                time.sleep(1)

            st.success(f"**{target_sel}** 스크리닝 완료")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**AI 분석 — 투자 매력도 평가**")
                criteria = pd.DataFrame({
                    "평가항목": ["시장성", "기술력/경쟁력", "재무건전성", "시너지",
                              "경영진", "ESG", "Exit 가능성"],
                    "점수": [deterministic_score(target_sel + "mkt", 60, 95),
                            deterministic_score(target_sel + "tech", 55, 92),
                            deterministic_score(target_sel + "fin", 50, 88),
                            deterministic_score(target_sel + "syn", 60, 95),
                            deterministic_score(target_sel + "mgmt", 55, 90),
                            deterministic_score(target_sel + "esg", 50, 85),
                            deterministic_score(target_sel + "exit", 50, 90)],
                })
                criteria["점수"] = criteria["점수"].round(0).astype(int)
                fig_radar = go.Figure(go.Scatterpolar(
                    r=criteria["점수"].tolist() + [criteria["점수"].iloc[0]],
                    theta=criteria["평가항목"].tolist() + [criteria["평가항목"].iloc[0]],
                    fill="toself", fillcolor="rgba(30,136,229,0.2)",
                    line=dict(color="#1E88E5"),
                ))
                fig_radar.update_layout(height=350, margin=dict(t=30, b=30),
                                        polar=dict(radialaxis=dict(range=[0, 100])))
                st.plotly_chart(fig_radar, use_container_width=True)

            with col2:
                st.markdown("**AI 분석 — 리스크 점검**")
                avg_score = criteria["점수"].mean()
                risks = [
                    {"리스크 항목": "밸류에이션 과열", "심각도": "🟡 중",
                     "AI 소견": "동종업 대비 EV/Revenue 멀티플 20% 이상 프리미엄, 협상 여지 필요"},
                    {"리스크 항목": "기술 대체 리스크", "심각도": "🟡 중",
                     "AI 소견": "핵심 기술 특허 보유하나, 대기업 진입 가능성 모니터링 필요"},
                    {"리스크 항목": "규제 리스크", "심각도": "🟢 낮",
                     "AI 소견": "현행 규제 프레임워크 내 사업 영위, 단기 리스크 제한적"},
                    {"리스크 항목": "Key-man 리스크", "심각도": "🟡 중",
                     "AI 소견": "창업자 의존도 높음, Lock-up 및 경영참여 조건 협의 권고"},
                ]
                st.dataframe(pd.DataFrame(risks), use_container_width=True, hide_index=True)

                st.markdown(f"""
                **종합 매력도: {avg_score:.0f}점/100점** {'✅ 투자 검토 추천' if avg_score >= 70 else '⚠️ 추가 검토 필요'}
                """)

    # ── 3-2: IC Memo 자동 생성 ──
    with sub_tab2:
        st.subheader("AI IC Memo 자동 생성")
        st.markdown(f"{ai_agent_badge('IC Memo Agent', 'complete')} Agent가 분석 결과를 바탕으로 IC Memo 초안을 자동 작성합니다.",
                    unsafe_allow_html=True)

        if st.button("IC Memo 초안 생성", key="memo_btn"):
            st.markdown("""
            ---
            ### Investment Committee Memo (AI Draft)

            **타겟:** A사 (AI로봇 스타트업) | **일자:** 2026-03-16 | **심사역:** AI Agent (Draft)

            #### 1. 투자 개요
            | 항목 | 내용 |
            |------|------|
            | 투자 규모 | 300억원 (시리즈C 공동 리드) |
            | 지분율 | 15.2% (전환우선주) |
            | Pre-money | 2,700억원 |
            | 섹터 | AI/로봇 (자율주행 물류) |

            #### 2. 투자 논점
            - **시장 기회**: 물류 자동화 시장 CAGR 34%, 2028년 580조원 규모 전망
            - **경쟁 우위**: 자체 LiDAR+AI 내비게이션 특허 12건, 실내 자율주행 정확도 99.2%
            - **시너지**: SK네트웍스서비스 ICT 유지보수 역량 + A사 로봇 기술 → B2B 물류 로봇 서비스

            #### 3. Valuation
            - **EV/Revenue**: 15.2x (Peer 평균 12.8x 대비 +19%)
            - **DCF 기반**: 2,450억원 (WACC 12%, Terminal Growth 3%)
            - **AI 판단**: 프리미엄 정당화 가능하나, 2,500억원 이하 협상 권고

            #### 4. 핵심 리스크 & 경감 방안
            | 리스크 | 경감 방안 |
            |--------|----------|
            | 기술 대체 | 핵심 기술자 Lock-up 3년 + 경업금지 |
            | 매출 집중 | 신규 고객 파이프라인 확보 조건부 투자 |
            | 자금 소진 | 마일스톤 기반 단계적 투자 집행 |

            #### 5. 권고
            **투자 진행 권고** (조건부) — 밸류에이션 2,500억원 이하로 협상 + 마일스톤 투자 구조
            ---
            """)
            st.info("이 Memo는 AI Agent 초안입니다. 심사역 검토 후 IC 제출 바랍니다.")

    # ── 3-3: Red/Blue Team ──
    with sub_tab3:
        st.subheader("Red/Blue Team AI 토론")
        st.markdown(f"{ai_agent_badge('Red Team Agent', 'warning')} {ai_agent_badge('Blue Team Agent', 'running')} "
                    "AI Agent 간 토론으로 투자 의사결정의 편향성을 방지합니다.",
                    unsafe_allow_html=True)

        if st.button("Red/Blue Team 토론 실행", key="redblue_btn"):
            debates = [
                {"라운드": "R1", "주제": "밸류에이션 적정성",
                 "Blue (찬성)": "물류 로봇 시장 초기 — 퍼스트무버 프리미엄 정당. Peer(로보티즈, 뉴로메카) 대비 기술력 우위 감안 시 EV/Rev 15x 합리적.",
                 "Red (반대)": "Pre-money 2,700억 기준 EV/Revenue 15.2x는 상장 SaaS 기업 수준. 아직 BEP 미달성 기업에 과도. 2,000억 이하 재협상 필요.",
                 "판정": "🟡 조건부 — 2,500억 캡으로 타협안 제시"},
                {"라운드": "R2", "주제": "시너지 실현 가능성",
                 "Blue (찬성)": "SK네트웍스서비스의 전국 ICT 인프라 + A사 로봇 = 즉시 B2B 서비스 론칭 가능. 1+1>2 시너지 명확.",
                 "Red (반대)": "로봇 도입 의사결정은 고객사 CTO 레벨. SKN서비스 영업채널과 불일치. 시너지 구체화에 2년 이상 소요 예상.",
                 "판정": "🟡 부분 타당 — 시너지 로드맵 사전 수립 필요"},
                {"라운드": "R3", "주제": "Exit 전략",
                 "Blue (찬성)": "3년 내 IPO 가능. 물류 로봇 테마 시장 관심 높음. 전략적 매각 대안도 다수 (네이버, 쿠팡 등).",
                 "Red (반대)": "국내 로봇 IPO 사례 부족. 글로벌 시장 침체 시 Exit 지연 리스크. Fund Life 고려 시 불확실성 높음.",
                 "판정": "🟢 Blue 우위 — IPO/M&A 복수 Exit 경로 확보 조건"},
            ]
            st.dataframe(pd.DataFrame(debates), use_container_width=True, hide_index=True)

            st.markdown("""
            **AI 종합 판정:** 투자 진행 권고 (3건 중 Blue 1승, 조건부 2건)
            - 밸류에이션 2,500억 캡 협상
            - 시너지 로드맵 사전 합의
            - Exit 경로 복수 확보 (IPO + 전략적 매각 Put Option)
            """)


# ════════════════════════════════════════════
# TAB 4: 성과 모니터링 & 이상신호 식별
# ════════════════════════════════════════════
with tab4:
    st.markdown(f"""
    {ai_agent_badge("Smart Monitor Agent", "running")}
    {ai_agent_badge("이상징후 식별 Agent", "running")}
    > 데이터 자동 연동 → 실시간 대시보드 → 이상 신호 식별 → 심사역 알림
    """, unsafe_allow_html=True)

    st.subheader("포트폴리오 실적 Trend")
    col_left, col_right = st.columns(2)
    with col_left:
        monthly_val = port_df.groupby(["period", "bu_name"])["fair_value"].sum().reset_index()
        fig_val = px.area(monthly_val, x="period", y="fair_value", color="bu_name",
                          color_discrete_map=BU_COLOR_MAP,
                          labels={"fair_value": "공정가치 (억원)", "period": "", "bu_name": "계열사"})
        fig_val.update_layout(height=350, margin=dict(t=20, b=20))
        st.plotly_chart(fig_val, use_container_width=True)

    with col_right:
        monthly_roic = port_df.groupby(["period", "bu_name"])["roic"].mean().reset_index()
        fig_roic = px.line(monthly_roic, x="period", y="roic", color="bu_name",
                           color_discrete_map=BU_COLOR_MAP,
                           labels={"roic": "ROIC (%)", "period": "", "bu_name": "계열사"})
        fig_roic.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig_roic.update_layout(height=350, margin=dict(t=20, b=20))
        st.plotly_chart(fig_roic, use_container_width=True)

    st.divider()

    st.subheader("AI 이상 신호 식별 — 포트폴리오 실적 이탈 감지")
    anomalies = []
    for bu_id in port_df["bu_id"].unique():
        bu_data = port_df[port_df["bu_id"] == bu_id].sort_values("period").copy()
        bu_name = BU_NAME_MAP[bu_id]
        for col_name, label, fmt_val, fmt_ma in [
            ("fair_value", "공정가치", lambda v: f"{v:,.0f}억원", lambda v: f"{v:,.0f}억원"),
            ("roic", "ROIC", lambda v: f"{v:.1f}%", lambda v: f"{v:.1f}%"),
            ("equity_income", "지분법이익", lambda v: f"{v:.1f}억원", lambda v: f"{v:.1f}억원"),
        ]:
            bu_data[f"{col_name}_ma"] = bu_data[col_name].rolling(6, min_periods=3).mean()
            bu_data[f"{col_name}_std"] = bu_data[col_name].rolling(6, min_periods=3).std()
            bu_data[f"{col_name}_z"] = (bu_data[col_name] - bu_data[f"{col_name}_ma"]) / bu_data[f"{col_name}_std"].replace(0, np.nan)
            for _, row in bu_data.tail(3).iterrows():
                z = row[f"{col_name}_z"]
                if pd.notna(z) and abs(z) > 1.5:
                    anomalies.append({
                        "severity": "🔴" if abs(z) > 2 else "🟡",
                        "계열사": bu_name, "지표": label,
                        "이상유형": ("급등" if z > 0 else "급락") if col_name == "fair_value" else ("개선" if z > 0 else "악화"),
                        "기간": row["period"].strftime("%Y-%m"),
                        "현재값": fmt_val(row[col_name]),
                        "이동평균": fmt_ma(row[f"{col_name}_ma"]),
                        "Z-Score": round(z, 2),
                    })

    if anomalies:
        anomaly_df = pd.DataFrame(anomalies).sort_values("Z-Score", key=abs, ascending=False)
        st.dataframe(anomaly_df, use_container_width=True, hide_index=True)
    else:
        st.success("최근 3개월 내 탐지된 이상 신호가 없습니다.")

    st.divider()
    st.subheader("투자 KPI — 계획 대비 Gap 모니터링")
    if not kpi_df.empty:
        kpi_latest = kpi_df[kpi_df["period"] == kpi_df["period"].max()]
        kpi_gap = kpi_latest.groupby("kpi_id").agg(avg_gap_pct=("gap_pct", "mean")).reset_index().sort_values("avg_gap_pct")
        kpi_labels = {"INV_PERF": "투자성과종합", "PORTFOLIO_VAL": "포트폴리오가치",
                      "EQUITY_INCOME": "지분법이익", "DIV_YIELD": "배당수익률",
                      "PV_MAGIC": "SK매직 지분가치", "PV_RENT": "SK렌터카 지분가치",
                      "PV_MINTIT": "민팃 지분가치", "PV_WALKER": "워커힐 지분가치",
                      "NEW_BIZ": "신사업투자", "NB_CAPEX": "신사업CAPEX",
                      "NB_IRR": "신사업IRR", "NB_PAYBACK": "투자회수기간",
                      "NB_AI": "AI/DT투자", "NB_MOBILITY": "모빌리티투자", "NB_PLATFORM": "플랫폼투자"}
        kpi_gap["kpi_name"] = kpi_gap["kpi_id"].map(kpi_labels)
        kpi_gap["gap_pct_display"] = (kpi_gap["avg_gap_pct"] * 100).round(1)
        kpi_gap["color"] = kpi_gap["gap_pct_display"].apply(lambda x: "#F44336" if x < -5 else ("#FF9800" if x < 0 else "#4CAF50"))
        fig_gap = go.Figure(go.Bar(x=kpi_gap["gap_pct_display"], y=kpi_gap["kpi_name"], orientation="h",
                                   marker_color=kpi_gap["color"],
                                   text=kpi_gap["gap_pct_display"].apply(lambda x: f"{x:+.1f}%"), textposition="outside"))
        fig_gap.add_vline(x=0, line_color="gray", line_dash="dash")
        fig_gap.update_layout(height=450, margin=dict(t=20, b=20, l=120), xaxis_title="계획 대비 Gap (%)", yaxis_title="")
        st.plotly_chart(fig_gap, use_container_width=True)


# ════════════════════════════════════════════
# TAB 5: 예측 Lever & Forecasting
# ════════════════════════════════════════════
with tab5:
    st.markdown(f"""
    {ai_agent_badge("예측 Lever Agent", "complete")}
    {ai_agent_badge("성과 정보 수집 Agent", "running")}
    > AI가 공정가치에 영향을 미치는 핵심 Driver를 자동 분석하고 내부/외부 데이터를 수집합니다.
    """, unsafe_allow_html=True)

    st.subheader("AI 핵심 성과 Driver(Lever) 분석")
    merged_analysis = port_df.merge(
        fin_df[["bu_id", "period", "revenue", "ebitda", "capex", "operating_cf"]],
        on=["bu_id", "period"], how="inner")

    if not merged_analysis.empty:
        corr_cols = ["fair_value", "revenue", "ebitda", "capex", "operating_cf", "roic", "equity_income"]
        available_cols = [c for c in corr_cols if c in merged_analysis.columns]
        corr_matrix = merged_analysis[available_cols].corr()
        lever_labels = {"revenue": "매출액", "ebitda": "EBITDA", "capex": "CAPEX",
                        "operating_cf": "영업CF", "roic": "ROIC", "equity_income": "지분법이익"}

        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown("**공정가치 상관 Lever (전체)**")
            fv_corr = corr_matrix["fair_value"].drop("fair_value").sort_values(ascending=False)
            lever_df = pd.DataFrame({"Lever": fv_corr.index, "상관계수": fv_corr.values})
            lever_df["Lever"] = lever_df["Lever"].map(lever_labels).fillna(lever_df["Lever"])
            lever_df["방향"] = lever_df["상관계수"].apply(lambda x: "양(+)" if x > 0 else "음(-)")
            fig_lever = px.bar(lever_df, x="Lever", y="상관계수", color="방향",
                               color_discrete_map={"양(+)": "#4CAF50", "음(-)": "#F44336"},
                               text=lever_df["상관계수"].apply(lambda x: f"{x:.3f}"))
            fig_lever.update_layout(height=350, margin=dict(t=20, b=20))
            st.plotly_chart(fig_lever, use_container_width=True)

        with col_right:
            st.markdown("**계열사별 핵심 Lever**")
            bu_levers = []
            for bu_id in merged_analysis["bu_id"].unique():
                bu_sub = merged_analysis[merged_analysis["bu_id"] == bu_id]
                if len(bu_sub) >= 6:
                    for col in ["revenue", "ebitda", "operating_cf", "roic"]:
                        if col in bu_sub.columns:
                            corr_val = bu_sub["fair_value"].corr(bu_sub[col])
                            if pd.notna(corr_val):
                                bu_levers.append({"계열사": BU_NAME_MAP[bu_id], "Lever": lever_labels.get(col, col), "상관계수": round(corr_val, 3)})
            if bu_levers:
                bu_lever_df = pd.DataFrame(bu_levers)
                top_levers = bu_lever_df.loc[bu_lever_df.groupby("계열사")["상관계수"].apply(lambda x: x.abs().idxmax())]
                fig_bl = px.bar(top_levers, x="계열사", y="상관계수", color="Lever",
                                text=top_levers["상관계수"].apply(lambda x: f"{x:.3f}"),
                                labels={"상관계수": "공정가치 상관계수"})
                fig_bl.update_layout(height=350, margin=dict(t=20, b=20))
                st.plotly_chart(fig_bl, use_container_width=True)

    st.divider()
    st.subheader("데이터 수집 현황 — AI Agent 자동 연동")
    data_source_matrix = pd.DataFrame({
        "지표": ["재무실적(P&L)", "공정가치평가", "구독자/계약 데이터", "시장/경쟁사 MI",
                 "거시경제(금리/환율)", "ESG 스코어", "Peer Valuation Multiple"],
        "내부 데이터": ["ERP/연결회계", "자산평가팀", "CRM/계약DB", "경영전략실", "재무팀", "ESG팀", "-"],
        "외부 데이터": ["-", "외부감정평가", "-", "리서치/뉴스", "한국은행/KOSIS", "KCGS/MSCI", "Bloomberg/DART"],
        "수집주기": ["월간", "분기", "실시간", "주간", "일간", "반기", "분기"],
        "AI 연동": ["🟢 자동", "🟡 반자동", "🟢 자동", "🟢 AI 크롤링", "🟢 API", "🟡 반자동", "🟢 API"],
    })
    st.dataframe(data_source_matrix, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════
# TAB 6: 성과 Projection
# ════════════════════════════════════════════
with tab6:
    st.markdown(f"""
    {ai_agent_badge("성과 예측 Agent", "running")}
    > AI Agent가 내부/외부 데이터 기반으로 향후 성과를 Projection 합니다.
    """, unsafe_allow_html=True)

    selected_bu = st.selectbox("계열사 선택", options=list(BUSINESS_UNITS.keys()),
                               format_func=lambda x: BUSINESS_UNITS[x]["name"])
    bu_port = port_df[port_df["bu_id"] == selected_bu].sort_values("period").copy()
    bu_fin = fin_df[fin_df["bu_id"] == selected_bu].sort_values("period").copy()

    if not bu_port.empty and not bu_fin.empty:
        forecast_months = 6
        last_12 = bu_port.tail(12)
        x = np.arange(len(last_12))
        fv_coeff = np.polyfit(x, last_12["fair_value"].values, 1)
        future_x = np.arange(len(last_12), len(last_12) + forecast_months)
        fv_forecast = np.polyval(fv_coeff, future_x)
        future_dates = pd.date_range(start=last_12["period"].max() + pd.DateOffset(months=1), periods=forecast_months, freq="MS")
        roic_coeff = np.polyfit(x, last_12["roic"].values, 1)
        roic_forecast = np.polyval(roic_coeff, future_x)
        eq_coeff = np.polyfit(x, last_12["equity_income"].values, 1)
        eq_forecast = np.polyval(eq_coeff, future_x)

        st.subheader(f"{BU_NAME_MAP[selected_bu]} — AI 향후 6개월 성과 Projection")
        col1, col2, col3 = st.columns(3)
        col1.metric("공정가치 예측", f"{fv_forecast[-1]:,.0f} 억원",
                     f"{fv_forecast[-1] - last_12['fair_value'].iloc[-1]:+,.0f}")
        col2.metric("ROIC 예측", f"{roic_forecast[-1]:.1f}%",
                     f"{roic_forecast[-1] - last_12['roic'].iloc[-1]:+.1f}%p")
        col3.metric("지분법이익 예측", f"{eq_forecast[-1]:.1f} 억원",
                     f"{eq_forecast[-1] - last_12['equity_income'].iloc[-1]:+.1f}")

        st.divider()
        col_left, col_right = st.columns(2)
        fv_std = last_12["fair_value"].std()
        roic_std = last_12["roic"].std()

        with col_left:
            st.markdown("**공정가치 Projection**")
            fig_proj = go.Figure()
            fig_proj.add_trace(go.Scatter(x=bu_port["period"], y=bu_port["fair_value"],
                                          mode="lines", name="실적", line=dict(color=BU_COLOR_MAP_ID[selected_bu], width=2)))
            fig_proj.add_trace(go.Scatter(x=future_dates, y=fv_forecast,
                                          mode="lines+markers", name="AI Projection",
                                          line=dict(color=BU_COLOR_MAP_ID[selected_bu], width=2, dash="dash"), marker=dict(size=6)))
            fig_proj.add_trace(go.Scatter(
                x=pd.concat([pd.Series(future_dates), pd.Series(future_dates[::-1])]),
                y=np.concatenate([fv_forecast + fv_std, (fv_forecast - fv_std)[::-1]]),
                fill="toself", fillcolor="rgba(100,100,100,0.1)", line=dict(color="rgba(0,0,0,0)"), name="신뢰구간"))
            fig_proj.update_layout(height=380, margin=dict(t=20, b=20), yaxis_title="공정가치 (억원)")
            st.plotly_chart(fig_proj, use_container_width=True)

        with col_right:
            st.markdown("**ROIC Projection**")
            fig_roic_p = go.Figure()
            fig_roic_p.add_trace(go.Scatter(x=bu_port["period"], y=bu_port["roic"],
                                            mode="lines", name="실적", line=dict(color=BU_COLOR_MAP_ID[selected_bu], width=2)))
            fig_roic_p.add_trace(go.Scatter(x=future_dates, y=roic_forecast,
                                            mode="lines+markers", name="AI Projection",
                                            line=dict(color=BU_COLOR_MAP_ID[selected_bu], width=2, dash="dash")))
            fig_roic_p.add_trace(go.Scatter(
                x=pd.concat([pd.Series(future_dates), pd.Series(future_dates[::-1])]),
                y=np.concatenate([roic_forecast + roic_std, (roic_forecast - roic_std)[::-1]]),
                fill="toself", fillcolor="rgba(100,100,100,0.1)", line=dict(color="rgba(0,0,0,0)"), name="신뢰구간"))
            fig_roic_p.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
            fig_roic_p.update_layout(height=380, margin=dict(t=20, b=20), yaxis_title="ROIC (%)")
            st.plotly_chart(fig_roic_p, use_container_width=True)

        st.divider()
        st.subheader("시나리오별 Projection 요약")
        base_fv, base_roic = fv_forecast[-1], roic_forecast[-1]
        scenarios = pd.DataFrame({
            "시나리오": ["Upside (+1σ)", "Base Case", "Downside (-1σ)", "Stress (-2σ)"],
            "공정가치 (억원)": [f"{base_fv + fv_std:,.0f}", f"{base_fv:,.0f}", f"{base_fv - fv_std:,.0f}", f"{base_fv - 2*fv_std:,.0f}"],
            "ROIC (%)": [f"{base_roic + roic_std:.1f}", f"{base_roic:.1f}", f"{base_roic - roic_std:.1f}", f"{base_roic - 2*roic_std:.1f}"],
            "확률": ["16%", "50%", "16%", "2.5%"],
        })
        st.dataframe(scenarios, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════
# TAB 7: Exit 관리 & Valuation
# ════════════════════════════════════════════
with tab7:
    st.markdown(f"""
    {ai_agent_badge("Valuation Agent", "running")}
    {ai_agent_badge("Exit 보조 Agent", "complete")}
    > AI Agent가 Peer 멀티플 + DCF 기반 예상 Valuation을 도출하고 Exit 전략을 수립합니다.
    """, unsafe_allow_html=True)

    st.subheader("AI Valuation — 멀티플 기반 평가")
    fin_12m = fin_df[fin_df["period"] >= fin_df["period"].max() - pd.DateOffset(months=11)]
    fin_annual = fin_12m.groupby("bu_id").agg(annual_rev=("revenue", "sum"), annual_ebitda=("ebitda", "sum"), annual_ebit=("ebit", "sum")).reset_index()
    val_data = latest.merge(fin_annual, on="bu_id", how="left")
    peer_multiples = {
        "SK_Magic": {"ev_ebitda": 12.5, "per": 18.0, "sector": "가전/렌탈"},
        "SK_Rentacar": {"ev_ebitda": 8.0, "per": 12.0, "sector": "모빌리티/렌탈"},
        "Mintit": {"ev_ebitda": 25.0, "per": 40.0, "sector": "리커머스/플랫폼"},
        "Walkerhill": {"ev_ebitda": 10.0, "per": 15.0, "sector": "호텔/레저"},
        "SKN_Service": {"ev_ebitda": 6.0, "per": 10.0, "sector": "ICT서비스"},
    }
    val_rows = []
    for _, row in val_data.iterrows():
        bu_id = row["bu_id"]
        peer = peer_multiples.get(bu_id, {})
        ev_ebitda_mult, per_mult, sector = peer.get("ev_ebitda", 10), peer.get("per", 15), peer.get("sector", "-")
        ev_val = row["annual_ebitda"] * ev_ebitda_mult * (row["stake_pct"] / 100) if row["annual_ebitda"] > 0 else 0
        per_val = row["annual_ebit"] * 0.75 * per_mult * (row["stake_pct"] / 100) if row["annual_ebit"] > 0 else 0
        avg_val = (ev_val + per_val) / 2 if per_val > 0 else ev_val
        upside = ((avg_val / row["fair_value"] - 1) * 100) if row["fair_value"] > 0 else 0
        val_rows.append({"계열사": BU_NAME_MAP[bu_id], "섹터": sector, "연간EBITDA": f"{row['annual_ebitda']:,.0f}",
                         "Peer EV/EBITDA": f"{ev_ebitda_mult:.1f}x", "EV/EBITDA 가치": f"{ev_val:,.0f}",
                         "Peer PER": f"{per_mult:.1f}x", "PER 가치": f"{per_val:,.0f}",
                         "AI Valuation": f"{avg_val:,.0f}", "현재 공정가치": f"{row['fair_value']:,.0f}",
                         "Upside/Downside": f"{upside:+.1f}%"})
    st.dataframe(pd.DataFrame(val_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("AI Exit Readiness 평가")
    exit_criteria = []
    for _, row in latest.iterrows():
        bu_id, bu_name = row["bu_id"], BU_NAME_MAP[row["bu_id"]]
        premium = (row["fair_value"] / row["book_value"] - 1) * 100
        score = 50
        if premium > 80: score += 20
        elif premium > 30: score += 10
        elif premium < 0: score -= 15
        if row["roic"] > 12: score += 15
        elif row["roic"] > 8: score += 8
        elif row["roic"] < 0: score -= 20
        if row["irr"] > 15: score += 15
        elif row["irr"] > 10: score += 8
        score = max(0, min(100, score))
        readiness = "Hold" if score < 40 else ("Review" if score < 65 else ("Monitor" if score < 80 else "Exit Ready"))
        color = {"Hold": "#F44336", "Review": "#FF9800", "Monitor": "#2196F3", "Exit Ready": "#4CAF50"}[readiness]
        exit_criteria.append({"bu_name": bu_name, "score": score, "readiness": readiness, "premium": premium, "roic": row["roic"], "irr": row["irr"], "color": color})
    exit_df = pd.DataFrame(exit_criteria)

    col_left, col_right = st.columns(2)
    with col_left:
        fig_exit = go.Figure(go.Bar(x=exit_df["bu_name"], y=exit_df["score"], marker_color=exit_df["color"],
                                    text=exit_df.apply(lambda r: f"{r['score']}점<br>{r['readiness']}", axis=1), textposition="outside"))
        fig_exit.add_hline(y=65, line_dash="dash", line_color="orange", annotation_text="Review 기준")
        fig_exit.add_hline(y=80, line_dash="dash", line_color="green", annotation_text="Exit Ready")
        fig_exit.update_layout(height=400, margin=dict(t=20, b=20), yaxis_title="Exit Readiness Score", yaxis_range=[0, 110])
        st.plotly_chart(fig_exit, use_container_width=True)

    with col_right:
        st.markdown("**AI Exit 전략 권고**")
        for _, r in exit_df.iterrows():
            icon = {"Hold": "🔴", "Review": "🟡", "Monitor": "🔵", "Exit Ready": "🟢"}[r["readiness"]]
            if r["readiness"] == "Exit Ready":
                strategy = "IPO 또는 전략적 매각 검토 — buy-side 미팅 준비"
            elif r["readiness"] == "Monitor":
                strategy = "시장 타이밍 모니터링 — Exit Window 대기"
            elif r["readiness"] == "Review":
                strategy = "가치 제고 전략 수립 — O/I 과제 강화"
            else:
                strategy = "장기 보유 — 구조조정 또는 추가 투자 검토"
            st.markdown(f"{icon} **{r['bu_name']}** ({r['readiness']}, {r['score']}점): {strategy}")

        st.markdown("""
        | 구간 | 상태 | 의미 |
        |------|------|------|
        | 80+ | Exit Ready | Exit 조건 충족, 매각/IPO 검토 |
        | 65-79 | Monitor | 양호, 시장 타이밍 모니터링 |
        | 40-64 | Review | 가치 제고 전략 검토 필요 |
        | 0-39 | Hold | 장기 보유/구조조정 |
        """)


# ════════════════════════════════════════════
# TAB 8: 신규투자 Pipeline
# ════════════════════════════════════════════
with tab8:
    if proj_df.empty:
        st.warning("투자 프로젝트 데이터가 없습니다.")
    else:
        proj_df["bu_name"] = proj_df["bu_id"].map(BU_NAME_MAP).fillna("본사(지주)")
        proj_df["progress"] = (proj_df["spent_amount"] / proj_df["total_budget"] * 100).round(1)
        total_budget = proj_df["total_budget"].sum()
        total_spent = proj_df["spent_amount"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 투자 Pipeline", f"{total_budget:,.0f} 억원")
        c2.metric("집행률", f"{total_spent / total_budget * 100:.1f}%", f"{total_spent:,.0f} 억원 집행")
        c3.metric("진행중 프로젝트", f"{(proj_df['status'] == 'in_progress').sum()}건")
        c4.metric("평균 기대 IRR", f"{proj_df['expected_irr'].mean():.1f}%")

        st.divider()
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("투자 Pipeline 현황")
            cat_labels = {"organic": "자체투자", "MA": "M&A", "JV": "합작투자", "strategic": "전략투자"}
            proj_cat = proj_df.copy()
            proj_cat["cat_name"] = proj_cat["category"].map(cat_labels)
            fig_pipe = px.bar(proj_cat, x="name", y="total_budget", color="cat_name", text="progress",
                              labels={"total_budget": "투자규모 (억원)", "name": "", "cat_name": "유형"})
            fig_pipe.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
            fig_pipe.update_layout(height=400, margin=dict(t=20, b=80), xaxis_tickangle=-30)
            st.plotly_chart(fig_pipe, use_container_width=True)

        with col_right:
            st.subheader("IRR vs 투자규모")
            risk_colors = {"low": "#4CAF50", "medium": "#FF9800", "high": "#F44336"}
            fig_bubble = px.scatter(proj_df, x="total_budget", y="expected_irr", size="total_budget",
                                   color="risk_level", color_discrete_map=risk_colors,
                                   text="name", hover_data=["bu_name", "expected_payback"],
                                   labels={"total_budget": "투자규모 (억원)", "expected_irr": "기대 IRR (%)", "risk_level": "리스크"}, size_max=40)
            fig_bubble.update_traces(textposition="top center", textfont_size=9)
            fig_bubble.update_layout(height=400, margin=dict(t=20, b=20))
            st.plotly_chart(fig_bubble, use_container_width=True)

        st.divider()
        st.subheader("투자 Stage 현황")
        stage_order = ["ideation", "feasibility", "execution", "monitoring"]
        stage_data = proj_df.groupby("stage").agg(count=("id", "count"), budget=("total_budget", "sum")).reindex(stage_order).fillna(0).reset_index()
        stage_data["stage_name"] = stage_data["stage"].map(STAGE_LABELS)
        fig_funnel = go.Figure(go.Funnel(y=stage_data["stage_name"], x=stage_data["budget"], textinfo="value+text",
                                         text=stage_data["count"].astype(int).astype(str) + "건",
                                         marker=dict(color=["#E3F2FD", "#90CAF9", "#42A5F5", "#1565C0"])))
        fig_funnel.update_layout(height=300, margin=dict(t=20, b=20))
        st.plotly_chart(fig_funnel, use_container_width=True)

        st.subheader("투자 프로젝트 상세")
        proj_display = proj_df[["id", "name", "bu_name", "category", "total_budget", "spent_amount",
                                "progress", "expected_irr", "expected_payback", "status", "risk_level", "stage"]].copy()
        proj_display["status"] = proj_display["status"].map(STATUS_LABELS)
        proj_display["stage"] = proj_display["stage"].map(STAGE_LABELS)
        proj_display["risk_level"] = proj_display["risk_level"].map({"low": "🟢 낮음", "medium": "🟡 중간", "high": "🔴 높음"})
        proj_display = proj_display.rename(columns={
            "id": "ID", "name": "프로젝트명", "bu_name": "관련 계열사", "category": "유형", "total_budget": "예산(억원)",
            "spent_amount": "집행액(억원)", "progress": "집행률(%)", "expected_irr": "기대IRR(%)",
            "expected_payback": "회수기간(년)", "status": "상태", "risk_level": "리스크", "stage": "단계"})
        st.dataframe(proj_display, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════
# TAB 9: 포트폴리오 최적화
# ════════════════════════════════════════════
with tab9:
    st.subheader("포트폴리오 밸런스 분석")
    latest_opt = latest.copy()
    fin_latest = fin_df[fin_df["period"] == fin_df["period"].max()]
    rev_by_bu = fin_latest.groupby("bu_id")["revenue"].sum().reset_index()
    merged = latest_opt.merge(rev_by_bu, on="bu_id", how="left")
    merged["rev_share"] = (merged["revenue"] / merged["revenue"].sum() * 100).round(1)
    merged["value_share"] = (merged["fair_value"] / merged["fair_value"].sum() * 100).round(1)

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("**매출 기여도 vs 가치 비중 비교**")
        compare_df = merged[["bu_name", "rev_share", "value_share"]].melt(id_vars="bu_name", var_name="metric", value_name="pct")
        compare_df["metric"] = compare_df["metric"].map({"rev_share": "매출 비중", "value_share": "가치 비중"})
        fig_compare = px.bar(compare_df, x="bu_name", y="pct", color="metric", barmode="group", text="pct",
                             labels={"pct": "비중 (%)", "bu_name": "", "metric": ""},
                             color_discrete_map={"매출 비중": "#2F5496", "가치 비중": "#BF8F00"})
        fig_compare.update_layout(height=380, margin=dict(t=20, b=20))
        st.plotly_chart(fig_compare, use_container_width=True)

    with col_right:
        st.markdown("**장부가 vs 공정가치 비교**")
        bv_fv = latest_opt[["bu_name", "book_value", "fair_value"]].melt(id_vars="bu_name", var_name="metric", value_name="value")
        bv_fv["metric"] = bv_fv["metric"].map({"book_value": "장부가", "fair_value": "공정가치"})
        fig_bvfv = px.bar(bv_fv, x="bu_name", y="value", color="metric", barmode="group",
                          text=bv_fv["value"].apply(lambda x: f"{x:,.0f}"),
                          labels={"value": "가치 (억원)", "bu_name": "", "metric": ""},
                          color_discrete_map={"장부가": "#90CAF9", "공정가치": "#1565C0"})
        fig_bvfv.update_layout(height=380, margin=dict(t=20, b=20))
        st.plotly_chart(fig_bvfv, use_container_width=True)

    st.divider()
    st.subheader("Risk-Return 매트릭스")
    latest_rr = latest.copy()
    latest_rr["volatility"] = port_df.groupby("bu_id")["roic"].std().reindex(latest_rr["bu_id"].values).values
    fig_rr = px.scatter(latest_rr, x="volatility", y="irr", size="fair_value", color="bu_name",
                        color_discrete_map=BU_COLOR_MAP, text="bu_name",
                        labels={"volatility": "ROIC 변동성 (Risk)", "irr": "IRR (Return %)", "bu_name": "계열사"}, size_max=50)
    fig_rr.update_traces(textposition="top center")
    fig_rr.add_hline(y=latest_rr["irr"].mean(), line_dash="dash", line_color="gray", annotation_text=f"평균 IRR {latest_rr['irr'].mean():.1f}%")
    fig_rr.add_vline(x=latest_rr["volatility"].mean(), line_dash="dash", line_color="gray", annotation_text="평균 변동성")
    fig_rr.update_layout(height=450, margin=dict(t=30, b=20))
    st.plotly_chart(fig_rr, use_container_width=True)

    st.divider()
    st.subheader("CAPEX 효율성 분석")
    fin_12m = fin_df[fin_df["period"] >= fin_df["period"].max() - pd.DateOffset(months=11)]
    capex_by_bu = fin_12m.groupby("bu_id").agg(total_capex=("capex", "sum"), total_ebitda=("ebitda", "sum"), total_rev=("revenue", "sum")).reset_index()
    capex_by_bu["bu_name"] = capex_by_bu["bu_id"].map(BU_NAME_MAP)
    capex_by_bu["capex_to_rev"] = (capex_by_bu["total_capex"] / capex_by_bu["total_rev"] * 100).round(1)
    capex_by_bu["capex_to_ebitda"] = (capex_by_bu["total_capex"] / capex_by_bu["total_ebitda"] * 100).round(1)

    col1, col2 = st.columns(2)
    with col1:
        fig_capex = px.bar(capex_by_bu, x="bu_name", y="capex_to_rev", color="bu_name",
                           color_discrete_map=BU_COLOR_MAP, text="capex_to_rev", labels={"capex_to_rev": "CAPEX/매출 (%)", "bu_name": ""})
        fig_capex.update_layout(height=350, margin=dict(t=30, b=20), showlegend=False, title_text="CAPEX / 매출 비율 (12개월)")
        st.plotly_chart(fig_capex, use_container_width=True)
    with col2:
        fig_capex2 = px.bar(capex_by_bu, x="bu_name", y="capex_to_ebitda", color="bu_name",
                            color_discrete_map=BU_COLOR_MAP, text="capex_to_ebitda", labels={"capex_to_ebitda": "CAPEX/EBITDA (%)", "bu_name": ""})
        fig_capex2.update_layout(height=350, margin=dict(t=30, b=20), showlegend=False, title_text="CAPEX / EBITDA 비율 (12개월)")
        st.plotly_chart(fig_capex2, use_container_width=True)

    st.divider()
    st.subheader("포트폴리오 인사이트")
    insights = []
    for _, row in latest_opt.iterrows():
        premium = (row["fair_value"] / row["book_value"] - 1) * 100
        if premium > 50:
            insights.append(f"🟢 **{row['bu_name']}**: 공정가치 프리미엄 {premium:.0f}% — 시장에서 높은 가치 인정")
        elif premium < 0:
            insights.append(f"🔴 **{row['bu_name']}**: 공정가치 디스카운트 {premium:.0f}% — 가치 제고 방안 검토 필요")
        if row["roic"] < 0:
            insights.append(f"🟡 **{row['bu_name']}**: ROIC {row['roic']:.1f}% — 수익성 개선 또는 성장투자 단계 확인 필요")
    if not proj_df.empty:
        high_risk = proj_df[proj_df["risk_level"] == "high"]
        if len(high_risk) > 0:
            insights.append(f"🔴 고위험 투자 프로젝트 {len(high_risk)}건 — 모니터링 강화 필요")
        insights.append(f"📊 신규투자 Pipeline 총 {proj_df['total_budget'].sum():,.0f}억원 ({len(proj_df)}건)")
    for insight in insights:
        st.markdown(f"- {insight}")


# ════════════════════════════════════════════
# TAB 10: 포트폴리오 AI Engine
# ════════════════════════════════════════════
with tab10:
    st.subheader("포트폴리오 AI Engine — 통합 운영 현황")
    st.markdown("LLM 기반 통합 AI Intelligence 플랫폼의 Agent 운영 상태를 모니터링합니다.")

    st.divider()

    # Agent 운영 현황
    st.markdown("#### AI Agent 운영 현황")

    agents = [
        {"Agent": "마켓 센싱 Agent", "유형": "Orchestration", "상태": "🟢 Active",
         "기능": "유망 섹터 스캔, 네트워크 기반 딜소싱, Long-list 생성",
         "데이터": "Bloomberg, CapIQ, 공시(DART), 뉴스/리서치", "주기": "실시간"},
        {"Agent": "섹터 Intel Agent", "유형": "Task", "상태": "🟢 Active",
         "기능": "섹터 매력도 분석, 경쟁 구조 파악, 트렌드 추적",
         "데이터": "산업 보고서, 경쟁사 IR, 특허 DB", "주기": "주간"},
        {"Agent": "딜 스크리닝 Agent", "유형": "Orchestration", "상태": "🟢 Active",
         "기능": "타겟 리서치, 리스크 점검, 투자 매력도 평가",
         "데이터": "재무제표, CDD/LDD/FDD 자료, 전문가 인터뷰", "주기": "요청시"},
        {"Agent": "IC Memo Agent", "유형": "Task", "상태": "🟢 Active",
         "기능": "IC Memo 초안 작성, 논점 정리, 편향 탈색",
         "데이터": "과거 IC Memo, 투자 심의 결과, 내부 가이드", "주기": "요청시"},
        {"Agent": "Red/Blue Team Agent", "유형": "Task", "상태": "🟡 Standby",
         "기능": "투자 찬반 토론, 편향성 방지, 반론 생성",
         "데이터": "스크리닝 결과, IC Memo, 시장 데이터", "주기": "IC 전"},
        {"Agent": "Smart Monitor Agent", "유형": "Orchestration", "상태": "🟢 Active",
         "기능": "실적 자동 모니터링, 이상징후 감지, 심사역 알림",
         "데이터": "ERP, CRM, 재무실적, 외부 시장 MI", "주기": "실시간"},
        {"Agent": "성과 예측 Agent", "유형": "Task", "상태": "🟢 Active",
         "기능": "포트폴리오 성과 Projection, 시나리오 분석",
         "데이터": "과거 실적, 거시/산업 지표, O/I 계획", "주기": "월간"},
        {"Agent": "Valuation Agent", "유형": "Task", "상태": "🟢 Active",
         "기능": "Peer 멀티플 기반 Valuation, DCF 모델링",
         "데이터": "Peer 그룹 MI, 재무 실적, History M&A 자료", "주기": "분기"},
        {"Agent": "Exit 보조 Agent", "유형": "Task", "상태": "🟡 Standby",
         "기능": "Exit Readiness 평가, buy-side 미팅 준비, 전략 수립",
         "데이터": "Valuation 결과, 시장 센싱, 내부 의사결정", "주기": "요청시"},
        {"Agent": "정보 취합 Agent", "유형": "Orchestration", "상태": "🟢 Active",
         "기능": "다중 Agent 결과 통합, 의사결정 요약 리포트 생성",
         "데이터": "전체 Agent Output 집계", "주기": "실시간"},
    ]
    st.dataframe(pd.DataFrame(agents), use_container_width=True, hide_index=True)

    st.divider()

    # 데이터 파이프라인
    st.markdown("#### 데이터 파이프라인")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        **외부 데이터**
        - Macro (Bloomberg 등)
        - 마켓 데이터 (CapIQ 등)
        - 공시 데이터 (10K, IR, DART)
        - 뉴스/리서치 피드
        """)
    with col2:
        st.markdown("""
        **내부 데이터**
        - 과거 CDD, LDD, FDD 자료
        - IC 메모/노트
        - 전문가 인터뷰 복기록
        - 투자 심의 이력
        """)
    with col3:
        st.markdown("""
        **회사 데이터**
        - ERP (연결재무)
        - CRM (고객/계약)
        - 포트폴리오 관리 DB
        - Excel/CSV 실적 자료
        """)

    st.divider()

    # AI Engine 활용 통계
    st.markdown("#### AI Engine 활용 통계 (최근 30일)")
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    stat_col1.metric("Agent 실행 횟수", "1,247회", "+18%")
    stat_col2.metric("자동 생성 리포트", "34건", "+5건")
    stat_col3.metric("이상신호 탐지", "12건", "조치완료 8건")
    stat_col4.metric("업무 시간 절감", "약 320시간", "심사역 기준")

    st.markdown("""
    ---
    **AI Engine 아키텍처:**
    Orchestration Agent가 전체 워크플로우를 조율하며, 각 Task Agent가 전문 영역을 담당합니다.
    모든 Agent는 LLM 기반 통합 플랫폼 위에서 동작하며, 내부/외부 데이터 파이프라인과 실시간으로 연동됩니다.
    """)
