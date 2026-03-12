"""
LLM Q&A Engine - Claude API 연동 비즈니스 질의응답
SK에코플랜트 Decision Intelligence 디지털 트윈
"""
import os
import json
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from anthropic import Anthropic

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.models import (
    SessionLocal, Financial, KPIDefinition, KPIValue,
    BizQuestion, RiskItem, BusinessUnit
)
from config.settings import BUSINESS_UNITS, DECISION_AREAS

# Claude client - API 키 설정 방법:
# 1. 환경변수: ANTHROPIC_API_KEY
# 2. Streamlit secrets: st.secrets["ANTHROPIC_API_KEY"]
# 3. .env 파일 (02_DigitalTwin/.env)
def _get_api_key():
    """여러 소스에서 API 키 탐색"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

_api_key = _get_api_key()
client = Anthropic(api_key=_api_key) if _api_key else None
MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """당신은 SK에코플랜트 경영진을 위한 Decision Intelligence 분석가입니다.
아래 데이터를 기반으로 경영진의 비즈니스 질문에 전문적으로 답변합니다.

## 역할
- 데이터에 근거한 정확한 답변 (숫자, 비율, 추세 포함)
- 근본 원인 분석 (Why) 및 실행 가능한 제안 (Action)
- 간결하고 구조적인 답변 (bullet point, 표 활용)

## SK에코플랜트 사업구조
- **Hi-tech EPC** (EPC_Hitech): 반도체 FAB, 플랜트 건설 (프로젝트형)
- **Green Energy** (GreenEnergy): 태양광, 풍력, WtE 발전 (자산운영형)
- **Recycling**: 폐기물 처리, 재활용, 소재 회수 (자산운영형)
- **Solution**: 환경 컨설팅, O&M 서비스 (서비스형)

## 4대 관리영역
- 성과(Performance): EBITDA, ROIC, EVA, FCF
- 운영(Operation): CPI/SPI, 가동률, CCC, 수주잔고
- 투자(Investment): CAPEX, NPV/IRR, ROIC-WACC Spread
- 리스크(Risk): Risk Score, ESG, 환율, 안전

## 답변 형식
1. **핵심 요약** (1-2문장)
2. **상세 분석** (데이터 기반, 표/비교 활용)
3. **원인 분석** (Driver 관점)
4. **Action 제안** (구체적 실행 방안)

금액 단위는 억원, 비율은 %로 표시합니다. 데이터에 없는 내용은 추정하지 마세요."""


def _fetch_context_data() -> dict:
    """DB에서 최신 컨텍스트 데이터를 수집"""
    session = SessionLocal()
    try:
        # 1. 최근 6개월 재무 데이터
        fins = session.query(Financial).order_by(Financial.period.desc()).limit(24).all()
        fin_records = []
        for f in fins:
            fin_records.append({
                "사업부": BUSINESS_UNITS.get(f.bu_id, {}).get("name", f.bu_id),
                "bu_id": f.bu_id,
                "기간": str(f.period),
                "매출": round(f.revenue),
                "매출원가": round(f.cogs),
                "매출총이익": round(f.gross_profit),
                "판관비": round(f.opex),
                "EBITDA": round(f.ebitda),
                "영업이익": round(f.ebit),
                "CAPEX": round(f.capex),
                "영업현금흐름": round(f.operating_cf),
                "수주잔고": round(f.backlog),
                "계획매출": round(f.plan_revenue),
                "계획EBITDA": round(f.plan_ebitda),
            })

        # 2. 최신 KPI 값 (최근 1개월)
        latest_period = session.query(Financial.period).order_by(Financial.period.desc()).first()
        kpi_records = []
        if latest_period:
            # KPIValue.kpi_id와 KPIDefinition.id가 다른 체계일 수 있으므로
            # 각각 독립적으로 조회 후 결합
            kpi_vals = (
                session.query(KPIValue)
                .filter(KPIValue.period == latest_period[0])
                .all()
            )
            # kpi_id 매핑 테이블 (약칭 -> 정규 ID)
            kpi_alias_map = {
                "UTIL": "O-011", "CCC": "O-021", "FX_RISK": "R-002",
                "ESG_SCORE": "R-004", "SAFETY": "R-006", "IRR": "I-003",
            }
            kpi_def_map = {d.id: d for d in session.query(KPIDefinition).all()}

            # 약칭 KPI 명칭
            kpi_name_fallback = {
                "UTIL": ("설비 가동률", "operation", "%"),
                "CCC": ("현금전환주기(CCC)", "operation", "일"),
                "FX_RISK": ("환율 리스크", "risk", "점"),
                "ESG_SCORE": ("ESG Score", "risk", "점"),
                "SAFETY": ("안전사고율(LTIR)", "risk", "건/백만h"),
                "IRR": ("IRR", "investment", "%"),
            }

            for val in kpi_vals:
                mapped_id = kpi_alias_map.get(val.kpi_id, val.kpi_id)
                defn = kpi_def_map.get(mapped_id)
                if defn:
                    name, cat, unit = defn.name, defn.category, defn.unit
                else:
                    fb = kpi_name_fallback.get(val.kpi_id, (val.kpi_id, "unknown", ""))
                    name, cat, unit = fb

                kpi_records.append({
                    "KPI_ID": mapped_id,
                    "KPI명": name,
                    "영역": cat,
                    "단위": unit,
                    "사업부": BUSINESS_UNITS.get(val.bu_id, {}).get("name", val.bu_id),
                    "실적": round(val.actual, 2) if val.actual else None,
                    "계획": round(val.plan, 2) if val.plan else None,
                    "Gap%": round(val.gap_pct * 100, 1) if val.gap_pct else None,
                })

        # 3. KPI 정의 (Driver Tree 구조)
        kpi_defs = session.query(KPIDefinition).order_by(KPIDefinition.id).all()
        tree_records = []
        for k in kpi_defs:
            tree_records.append({
                "ID": k.id, "이름": k.name, "영역": k.category,
                "단위": k.unit, "레벨": k.level,
                "상위KPI": k.parent_kpi_id, "산식": k.formula,
            })

        # 4. 리스크 항목
        risks = session.query(RiskItem).filter(RiskItem.status == "active").all()
        risk_records = []
        for r in risks:
            risk_records.append({
                "사업부": BUSINESS_UNITS.get(r.bu_id, {}).get("name", r.bu_id),
                "카테고리": r.category,
                "설명": r.description,
                "발생확률": r.probability,
                "영향도": r.impact,
                "Risk_Score": round(r.risk_score, 2),
            })

        # 5. Biz Question Pool (매칭용)
        bqs = session.query(BizQuestion).all()
        bq_records = []
        for q in bqs:
            bq_records.append({
                "ID": q.id, "영역": q.decision_area,
                "질문": q.question, "트리거": q.trigger_condition,
                "Answer유형": q.answer_type, "필요KPI": q.required_kpis,
            })

        return {
            "financial": fin_records,
            "kpi_values": kpi_records,
            "kpi_tree": tree_records,
            "risks": risk_records,
            "biz_questions": bq_records,
        }
    finally:
        session.close()


def _build_data_context(data: dict) -> str:
    """데이터를 LLM 컨텍스트 문자열로 변환"""
    parts = []

    # 재무 데이터 (최근 6개월)
    if data["financial"]:
        df = pd.DataFrame(data["financial"])
        # 최신 월
        latest = df[df["기간"] == df["기간"].max()]
        parts.append("## 최신 월 재무 실적 (사업부별)")
        for _, row in latest.iterrows():
            gap_rev = (row["매출"] / row["계획매출"] - 1) * 100 if row["계획매출"] else 0
            gap_ebitda = (row["EBITDA"] / row["계획EBITDA"] - 1) * 100 if row["계획EBITDA"] else 0
            parts.append(
                f"- **{row['사업부']}** ({row['기간']}): "
                f"매출 {row['매출']:,}억 (계획대비 {gap_rev:+.1f}%), "
                f"EBITDA {row['EBITDA']:,}억 (계획대비 {gap_ebitda:+.1f}%), "
                f"영업이익 {row['영업이익']:,}억, CAPEX {row['CAPEX']:,}억, "
                f"수주잔고 {row['수주잔고']:,}억"
            )

        # 전사 합계
        total = latest[["매출", "매출원가", "매출총이익", "판관비", "EBITDA", "영업이익", "CAPEX", "수주잔고", "계획매출", "계획EBITDA"]].sum()
        gap_rev_t = (total["매출"] / total["계획매출"] - 1) * 100 if total["계획매출"] else 0
        gap_ebitda_t = (total["EBITDA"] / total["계획EBITDA"] - 1) * 100 if total["계획EBITDA"] else 0
        parts.append(
            f"- **전사 합계**: 매출 {total['매출']:,.0f}억 (계획대비 {gap_rev_t:+.1f}%), "
            f"EBITDA {total['EBITDA']:,.0f}억 (계획대비 {gap_ebitda_t:+.1f}%), "
            f"영업이익 {total['영업이익']:,.0f}억, CAPEX {total['CAPEX']:,.0f}억"
        )

        # 3개월 추이
        parts.append("\n## 최근 3개월 추이 (사업부별)")
        recent_3m = df.sort_values(["사업부", "기간"]).groupby("사업부").tail(3)
        for bu in recent_3m["사업부"].unique():
            bu_data = recent_3m[recent_3m["사업부"] == bu]
            trend = ", ".join([f"{r['기간'][-5:]}: 매출{r['매출']:,}/EBITDA{r['EBITDA']:,}" for _, r in bu_data.iterrows()])
            parts.append(f"- **{bu}**: {trend}")

    # KPI 값
    if data["kpi_values"]:
        parts.append("\n## 최신 KPI 실적")
        for kpi in data["kpi_values"]:
            gap_str = f"(Gap: {kpi['Gap%']:+.1f}%)" if kpi['Gap%'] is not None else ""
            parts.append(
                f"- {kpi['KPI_ID']} {kpi['KPI명']} [{kpi['사업부']}]: "
                f"실적 {kpi['실적']} / 계획 {kpi['계획']} {kpi['단위']} {gap_str}"
            )

    # Driver Tree 구조
    if data["kpi_tree"]:
        parts.append("\n## KPI Driver Tree 구조")
        for k in data["kpi_tree"]:
            indent = "  " * k["레벨"]
            parent_str = f" <- {k['상위KPI']}" if k["상위KPI"] else ""
            parts.append(f"{indent}- L{k['레벨']} {k['ID']} {k['이름']} ({k['단위']}){parent_str}: {k['산식'] or ''}")

    # 리스크
    if data["risks"]:
        parts.append("\n## 활성 리스크 항목")
        for r in data["risks"]:
            parts.append(f"- [{r['사업부']}] {r['카테고리']}: {r['설명']} (Score: {r['Risk_Score']})")

    return "\n".join(parts)


def _find_matching_biz_question(user_question: str, bq_records: list) -> Optional[dict]:
    """사용자 질문과 가장 관련 있는 Biz Question 매칭 (키워드 기반)"""
    keywords_map = {
        "ebitda": ["BQ-P01"],
        "eva": ["BQ-P02"], "roic": ["BQ-P02", "BQ-I03"],
        "수주": ["BQ-P03"], "잔고": ["BQ-P03"],
        "반도체": ["BQ-P04"], "fab": ["BQ-P04"],
        "cpi": ["BQ-O01"], "spi": ["BQ-O01"], "공정": ["BQ-O01"], "지연": ["BQ-O01"],
        "가동": ["BQ-O02"], "다운타임": ["BQ-O02"], "설비": ["BQ-O02"],
        "opex": ["BQ-O03"], "처리비용": ["BQ-O03"], "톤당": ["BQ-O03"],
        "ccc": ["BQ-O04"], "현금": ["BQ-O04"], "매출채권": ["BQ-O04"], "미청구": ["BQ-O04"],
        "투자": ["BQ-I01"], "npv": ["BQ-I01"], "irr": ["BQ-I01", "BQ-I02"],
        "lcoe": ["BQ-I02"], "에너지 투자": ["BQ-I02"],
        "자본": ["BQ-I03"], "배분": ["BQ-I03"], "포트폴리오": ["BQ-I03"],
        "환율": ["BQ-R01"], "원자재": ["BQ-R01"],
        "esg": ["BQ-R02"], "탄소": ["BQ-R02"],
        "안전": ["BQ-R03"], "사고": ["BQ-R03"], "near": ["BQ-R03"],
        "부채": ["BQ-R04"], "ipo": ["BQ-R04"], "차입": ["BQ-R04"],
        "매출": ["BQ-P01"], "실적": ["BQ-P01"], "목표": ["BQ-P01"],
        "리스크": ["BQ-R01"], "위험": ["BQ-R01"],
    }

    q_lower = user_question.lower()
    matched_ids = set()
    for keyword, bq_ids in keywords_map.items():
        if keyword in q_lower:
            matched_ids.update(bq_ids)

    if matched_ids:
        bq_map = {q["ID"]: q for q in bq_records}
        for mid in matched_ids:
            if mid in bq_map:
                return bq_map[mid]
    return None


def ask_question(user_question: str, stream: bool = False):
    """
    사용자 질문에 대해 DB 데이터 기반 Claude API 답변 생성

    Args:
        user_question: 경영진 자연어 질문
        stream: True면 스트리밍 응답 반환

    Returns:
        stream=False: 전체 답변 문자열
        stream=True: 스트리밍 이벤트 제너레이터
    """
    # 1. DB에서 컨텍스트 데이터 수집
    data = _fetch_context_data()

    # 2. 관련 Biz Question 매칭
    matched_bq = _find_matching_biz_question(user_question, data["biz_questions"])

    # 3. 데이터 컨텍스트 구성
    data_context = _build_data_context(data)

    # 4. 매칭된 Biz Q 정보 추가
    bq_context = ""
    if matched_bq:
        bq_context = (
            f"\n\n## 관련 Biz Question\n"
            f"- ID: {matched_bq['ID']}\n"
            f"- 질문: {matched_bq['질문']}\n"
            f"- 트리거: {matched_bq['트리거']}\n"
            f"- Answer 유형: {matched_bq['Answer유형']}\n"
            f"- 필요 KPI: {matched_bq['필요KPI']}\n"
        )

    user_message = (
        f"다음은 SK에코플랜트의 최신 경영 데이터입니다:\n\n"
        f"{data_context}"
        f"{bq_context}\n\n"
        f"---\n\n"
        f"## 경영진 질문\n{user_question}\n\n"
        f"위 데이터를 기반으로 정확하고 구조적인 답변을 제공하세요."
    )

    if client is None:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 미설정. 환경변수, .env 파일, 또는 Streamlit secrets에 설정하세요."
        )

    if stream:
        return client.messages.stream(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    else:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text


def get_matched_biz_question(user_question: str) -> Optional[dict]:
    """사용자 질문에 매칭되는 Biz Question 반환 (UI 표시용)"""
    data = _fetch_context_data()
    return _find_matching_biz_question(user_question, data["biz_questions"])
