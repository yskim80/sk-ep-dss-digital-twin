"""M3. Biz Question Q&A - Claude API 연동 비즈니스 질의응답"""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.models import SessionLocal, BizQuestion, Financial, KPIValue, KPIDefinition, RiskItem
from config.settings import DECISION_AREAS, BUSINESS_UNITS

st.set_page_config(page_title="M3. Biz Q&A", page_icon="<C2><AC>", layout="wide")
st.title("M3. Biz Question Q&A")
st.caption("Claude API 기반 - 경영진 비즈니스 질문에 데이터 기반 답변 제공")


# ── Session state init ──
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
def _check_llm():
    try:
        from llm_engine import client
        return client is not None
    except Exception:
        return False

# Sidebar: API 키 설정
with st.sidebar:
    st.subheader("Claude API 설정")
    api_key_input = st.text_input(
        "API Key", type="password", key="api_key_input",
        placeholder="sk-ant-api03-...",
        help="ANTHROPIC_API_KEY를 입력하세요"
    )
    if api_key_input:
        import os
        os.environ["ANTHROPIC_API_KEY"] = api_key_input
        st.session_state.pop("llm_available", None)

    if st.button("연결 테스트", key="test_api"):
        try:
            from llm_engine import _get_client
            test_client = _get_client()
            if test_client:
                resp = test_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "hi"}]
                )
                st.success("Claude API 연결 성공!")
                st.session_state.llm_available = True
            else:
                st.error("API Key가 설정되지 않았습니다.")
                st.session_state.llm_available = False
        except Exception as e:
            st.error(f"연결 실패: {e}")
            st.session_state.llm_available = False

if "llm_available" not in st.session_state:
    try:
        from llm_engine import _get_client
        st.session_state.llm_available = (_get_client() is not None)
        if not st.session_state.llm_available:
            st.session_state.llm_error = "ANTHROPIC_API_KEY 미설정 (왼쪽 사이드바에서 입력하세요)"
    except Exception as e:
        st.session_state.llm_available = False
        st.session_state.llm_error = str(e)


# ── Data loaders ──
@st.cache_data(ttl=300)
def load_biz_questions():
    session = SessionLocal()
    try:
        qs = session.query(BizQuestion).order_by(BizQuestion.priority).all()
        return [{
            "id": q.id, "area": q.decision_area, "question": q.question,
            "trigger": q.trigger_condition, "answer_type": q.answer_type,
            "kpis": q.required_kpis, "priority": q.priority
        } for q in qs]
    finally:
        session.close()

@st.cache_data(ttl=300)
def load_latest_financials():
    session = SessionLocal()
    try:
        fins = session.query(Financial).order_by(Financial.period.desc()).all()
        df = pd.DataFrame([{
            "bu_id": r.bu_id, "period": r.period,
            "revenue": r.revenue, "ebitda": r.ebitda, "ebit": r.ebit,
            "cogs": r.cogs, "opex": r.opex, "capex": r.capex,
            "backlog": r.backlog, "operating_cf": r.operating_cf,
            "plan_revenue": r.plan_revenue, "plan_ebitda": r.plan_ebitda,
        } for r in fins])
        return df
    finally:
        session.close()

@st.cache_data(ttl=300)
def load_latest_kpis():
    session = SessionLocal()
    try:
        latest_period = session.query(Financial.period).order_by(Financial.period.desc()).first()
        if not latest_period:
            return pd.DataFrame()
        vals = (
            session.query(KPIValue, KPIDefinition)
            .join(KPIDefinition, KPIValue.kpi_id == KPIDefinition.id)
            .filter(KPIValue.period == latest_period[0])
            .all()
        )
        return pd.DataFrame([{
            "kpi_id": d.id, "kpi_name": d.name, "category": d.category,
            "unit": d.unit, "bu_id": v.bu_id,
            "bu_name": BUSINESS_UNITS.get(v.bu_id, {}).get("name", v.bu_id),
            "actual": v.actual, "plan": v.plan,
            "gap_pct": round(v.gap_pct * 100, 1) if v.gap_pct else 0,
        } for v, d in vals])
    finally:
        session.close()

@st.cache_data(ttl=300)
def load_risks():
    session = SessionLocal()
    try:
        risks = session.query(RiskItem).filter(RiskItem.status == "active").all()
        return pd.DataFrame([{
            "bu_id": r.bu_id,
            "bu_name": BUSINESS_UNITS.get(r.bu_id, {}).get("name", r.bu_id),
            "category": r.category, "description": r.description,
            "risk_score": round(r.risk_score, 2),
        } for r in risks])
    finally:
        session.close()


questions = load_biz_questions()
fin_df = load_latest_financials()
kpi_df = load_latest_kpis()
risk_df = load_risks()

# ══════════════════════════════════════════════════
# TAB 구조: 자연어 Q&A / Biz Q Pool / 데이터 탐색
# ══════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["AI Q&A (Claude)", "Biz Question Pool", "Data Explorer"])

# ══════════════════════════════════════════════════
# TAB 1: AI Q&A (Claude API 연동)
# ══════════════════════════════════════════════════
with tab1:
    st.subheader("AI 기반 경영 Q&A")

    if not st.session_state.llm_available:
        st.warning(
            f"Claude API 연결 불가: {st.session_state.get('llm_error', 'Unknown')}\n\n"
            "ANTHROPIC_API_KEY 환경변수를 설정하세요."
        )

    # 빠른 질문 버튼
    st.markdown("**빠른 질문:**")
    quick_cols = st.columns(4)
    quick_questions = [
        ("EBITDA Gap 분석", "이번 달 EBITDA 목표 대비 편차는 어느 사업부에서 발생했으며 주요 원인은?"),
        ("수주잔고 전망", "수주잔고 추이와 향후 매출 전환 전망은?"),
        ("리스크 현황", "현재 가장 위험도가 높은 리스크 항목은 무엇이며 대응 방안은?"),
        ("투자 ROI 현황", "투자 집행률과 NPV/IRR이 기준 이하인 프로젝트는?"),
    ]

    selected_quick = None
    for i, (label, question) in enumerate(quick_questions):
        with quick_cols[i]:
            if st.button(label, use_container_width=True, key=f"quick_{i}"):
                selected_quick = question

    st.divider()

    # 채팅 히스토리 표시
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 질문 입력
    user_input = st.chat_input("경영진 질문을 입력하세요 (예: 이번 분기 매출 목표 달성이 어려운 사업부는?)")

    # 빠른 질문 선택 시 처리
    if selected_quick:
        user_input = selected_quick

    if user_input:
        # 사용자 메시지 표시
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # AI 답변 생성
        with st.chat_message("assistant"):
            if st.session_state.llm_available:
                from llm_engine import ask_question, get_matched_biz_question

                # 매칭된 Biz Q 표시
                matched = get_matched_biz_question(user_input)
                if matched:
                    st.info(f"관련 Biz Question: **[{matched['ID']}]** {matched['질문'][:80]}...")

                # Claude API 스트리밍 호출
                try:
                    with ask_question(user_input, stream=True) as stream:
                        response_text = st.write_stream(
                            (text for text in stream.text_stream)
                        )
                    st.session_state.chat_history.append({"role": "assistant", "content": response_text})
                except Exception as e:
                    error_msg = f"API 호출 오류: {str(e)}"
                    st.error(error_msg)
                    st.session_state.chat_history.append({"role": "assistant", "content": error_msg})
            else:
                # Fallback: 데이터 기반 간단 답변
                answer = _generate_fallback_answer(user_input, fin_df, kpi_df, risk_df)
                st.markdown(answer)
                st.session_state.chat_history.append({"role": "assistant", "content": answer})

    # 채팅 초기화
    if st.session_state.chat_history:
        if st.button("대화 초기화", type="secondary"):
            st.session_state.chat_history = []
            st.rerun()

# ══════════════════════════════════════════════════
# TAB 2: Biz Question Pool
# ══════════════════════════════════════════════════
with tab2:
    if not questions:
        st.warning("Biz Question이 정의되지 않았습니다.")
    else:
        area_filter = st.selectbox(
            "의사결정 영역", ["전체"] + list(DECISION_AREAS.values()),
        )
        area_key_map = {v: k for k, v in DECISION_AREAS.items()}
        if area_filter != "전체":
            filtered_qs = [q for q in questions if q["area"] == area_key_map[area_filter]]
        else:
            filtered_qs = questions

        st.subheader(f"Biz Question Pool ({len(filtered_qs)}개)")

        for q in filtered_qs:
            area_label = DECISION_AREAS.get(q["area"], q["area"])
            area_colors = {"performance": "red", "operation": "blue", "investment": "green", "risk": "orange"}
            area_color = area_colors.get(q["area"], "gray")

            with st.expander(f':{area_color}[P{q["priority"]}] [{q["id"]}] {q["question"][:80]}...'):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**의사결정 영역:** {area_label}")
                    st.markdown(f"**트리거 조건:** {q['trigger']}")
                    st.markdown(f"**Answer 유형:** `{q['answer_type']}`")
                with col2:
                    st.markdown(f"**필요 KPI:** `{q['kpis']}`")
                    st.markdown(f"**우선순위:** P{q['priority']}")

                # AI Answer 생성 버튼
                if st.button(f"AI Answer 생성", key=f"bq_ans_{q['id']}"):
                    if st.session_state.llm_available:
                        from llm_engine import ask_question
                        with st.spinner("Claude API 분석 중..."):
                            try:
                                answer = ask_question(q["question"], stream=False)
                                st.markdown("---")
                                st.markdown("**AI Answer:**")
                                st.markdown(answer)
                            except Exception as e:
                                st.error(f"API 오류: {e}")
                    else:
                        st.markdown("---")
                        answer = _generate_fallback_answer(q["question"], fin_df, kpi_df, risk_df)
                        st.markdown(answer)


# ══════════════════════════════════════════════════
# TAB 3: Data Explorer
# ══════════════════════════════════════════════════
with tab3:
    st.subheader("데이터 탐색 (AI 답변의 근거 데이터)")

    data_tab1, data_tab2, data_tab3 = st.tabs(["재무 데이터", "KPI 현황", "리스크"])

    with data_tab1:
        if not fin_df.empty:
            fin_display = fin_df.copy()
            fin_display["period"] = pd.to_datetime(fin_display["period"])
            fin_display["bu_name"] = fin_display["bu_id"].map(
                {k: v["name"] for k, v in BUSINESS_UNITS.items()}
            )
            latest_period = fin_display["period"].max()
            latest_fin = fin_display[fin_display["period"] == latest_period]

            st.markdown(f"**최신 기간: {latest_period.strftime('%Y-%m')}**")

            cols = st.columns(4)
            for i, (_, row) in enumerate(latest_fin.iterrows()):
                with cols[i % 4]:
                    rev_gap = (row["revenue"] / row["plan_revenue"] - 1) * 100 if row["plan_revenue"] else 0
                    ebitda_gap = (row["ebitda"] / row["plan_ebitda"] - 1) * 100 if row["plan_ebitda"] else 0
                    st.metric(f"{row['bu_name']} 매출", f"{row['revenue']:,.0f}억", f"{rev_gap:+.1f}%")
                    st.metric(f"{row['bu_name']} EBITDA", f"{row['ebitda']:,.0f}억", f"{ebitda_gap:+.1f}%")

            st.dataframe(
                latest_fin[["bu_name", "revenue", "plan_revenue", "ebitda", "plan_ebitda",
                            "ebit", "capex", "backlog"]].rename(columns={
                    "bu_name": "사업부", "revenue": "매출(실적)", "plan_revenue": "매출(계획)",
                    "ebitda": "EBITDA(실적)", "plan_ebitda": "EBITDA(계획)",
                    "ebit": "영업이익", "capex": "CAPEX", "backlog": "수주잔고"
                }),
                use_container_width=True, hide_index=True
            )

    with data_tab2:
        if not kpi_df.empty:
            cat_filter = st.selectbox("KPI 영역", ["전체", "performance", "operation", "investment", "risk"], key="kpi_cat")
            display_kpi = kpi_df if cat_filter == "전체" else kpi_df[kpi_df["category"] == cat_filter]

            # Gap 이상 항목 하이라이트
            alert_kpis = display_kpi[display_kpi["gap_pct"].abs() > 5]
            if not alert_kpis.empty:
                st.warning(f"Gap > 5% 이상 KPI: {len(alert_kpis)}건")

            st.dataframe(
                display_kpi[["kpi_id", "kpi_name", "bu_name", "actual", "plan", "unit", "gap_pct"]].rename(columns={
                    "kpi_id": "KPI ID", "kpi_name": "KPI명", "bu_name": "사업부",
                    "actual": "실적", "plan": "계획", "unit": "단위", "gap_pct": "Gap(%)"
                }),
                use_container_width=True, hide_index=True
            )

    with data_tab3:
        if not risk_df.empty:
            st.dataframe(
                risk_df[["bu_name", "category", "description", "risk_score"]].rename(columns={
                    "bu_name": "사업부", "category": "카테고리",
                    "description": "설명", "risk_score": "Risk Score"
                }).sort_values("Risk Score", ascending=False),
                use_container_width=True, hide_index=True
            )


# ══════════════════════════════════════════════════
# Fallback Answer (API 불가 시)
# ══════════════════════════════════════════════════
def _generate_fallback_answer(question: str, fin_df, kpi_df, risk_df) -> str:
    """Claude API 없이 데이터 기반 간단 답변 생성"""
    parts = ["**[Data-based Answer]** (Claude API 미연결 - 데이터 요약 모드)\n"]

    if fin_df.empty:
        return parts[0] + "재무 데이터가 없습니다."

    fin_df_copy = fin_df.copy()
    fin_df_copy["period"] = pd.to_datetime(fin_df_copy["period"])
    latest_period = fin_df_copy["period"].max()
    latest = fin_df_copy[fin_df_copy["period"] == latest_period]
    latest["bu_name"] = latest["bu_id"].map({k: v["name"] for k, v in BUSINESS_UNITS.items()})

    q_lower = question.lower()

    # EBITDA/매출/실적 관련
    if any(kw in q_lower for kw in ["ebitda", "매출", "실적", "목표", "편차", "gap"]):
        parts.append("### 사업부별 실적 vs 계획\n")
        for _, row in latest.iterrows():
            rev_gap = (row["revenue"] / row["plan_revenue"] - 1) * 100 if row["plan_revenue"] else 0
            ebitda_gap = (row["ebitda"] / row["plan_ebitda"] - 1) * 100 if row["plan_ebitda"] else 0
            status = "미달" if ebitda_gap < -3 else "달성" if ebitda_gap >= 0 else "근접"
            parts.append(
                f"- **{row['bu_name']}**: 매출 {row['revenue']:,.0f}억 ({rev_gap:+.1f}%), "
                f"EBITDA {row['ebitda']:,.0f}억 ({ebitda_gap:+.1f}%) -> **{status}**"
            )
        worst = latest.loc[((latest["ebitda"] / latest["plan_ebitda"]) - 1).idxmin()]
        parts.append(f"\n> 가장 큰 Gap: **{worst['bu_name']}** 사업부")

    # 리스크 관련
    elif any(kw in q_lower for kw in ["리스크", "위험", "risk", "환율", "안전"]):
        if not risk_df.empty:
            parts.append("### 활성 리스크 항목 (Score 순)\n")
            for _, r in risk_df.sort_values("risk_score", ascending=False).iterrows():
                parts.append(f"- [{r['bu_name']}] {r['category']}: {r['description']} (Score: {r['risk_score']})")

    # KPI 관련
    elif any(kw in q_lower for kw in ["kpi", "가동", "cpi", "spi"]):
        if not kpi_df.empty:
            alert = kpi_df[kpi_df["gap_pct"].abs() > 5]
            parts.append(f"### Gap > 5% KPI 항목 ({len(alert)}건)\n")
            for _, k in alert.iterrows():
                parts.append(f"- {k['kpi_name']} [{k['bu_name']}]: 실적 {k['actual']:.1f} / 계획 {k['plan']:.1f} (Gap: {k['gap_pct']:+.1f}%)")

    # 수주/잔고 관련
    elif any(kw in q_lower for kw in ["수주", "잔고", "backlog"]):
        parts.append("### 사업부별 수주잔고\n")
        for _, row in latest.iterrows():
            parts.append(f"- **{row['bu_name']}**: 수주잔고 {row['backlog']:,.0f}억")

    # 투자 관련
    elif any(kw in q_lower for kw in ["투자", "capex", "npv", "irr"]):
        parts.append("### 사업부별 CAPEX\n")
        for _, row in latest.iterrows():
            parts.append(f"- **{row['bu_name']}**: CAPEX {row['capex']:,.0f}억")
        if not kpi_df.empty:
            irr_kpis = kpi_df[kpi_df["kpi_id"] == "IRR"]
            if not irr_kpis.empty:
                parts.append("\n### IRR 현황")
                for _, k in irr_kpis.iterrows():
                    parts.append(f"- {k['bu_name']}: IRR {k['actual']:.1f}% (계획 {k['plan']:.1f}%)")

    else:
        parts.append("### 전사 최신 실적 요약\n")
        total_rev = latest["revenue"].sum()
        total_ebitda = latest["ebitda"].sum()
        parts.append(f"- 전사 매출: {total_rev:,.0f}억원")
        parts.append(f"- 전사 EBITDA: {total_ebitda:,.0f}억원")
        parts.append(f"- 전사 수주잔고: {latest['backlog'].sum():,.0f}억원")

    parts.append("\n---\n*Claude API 연결 시 심층 원인 분석 및 Action 제안이 포함됩니다.*")
    return "\n".join(parts)
