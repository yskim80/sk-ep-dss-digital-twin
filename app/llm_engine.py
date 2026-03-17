"""
LLM Q&A Engine - Claude API 연동 비즈니스 질의응답
SK네트웍스 Decision Intelligence 디지털 트윈 (지주사 관점)
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

# Claude client
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

MODEL = "claude-sonnet-4-20250514"


def _get_client() -> Optional[Anthropic]:
    """매 호출 시 최신 API 키로 클라이언트 생성"""
    key = _get_api_key()
    if key:
        return Anthropic(api_key=key)
    return None


client = _get_client()

SYSTEM_PROMPT = """당신은 SK네트웍스 경영진을 위한 Decision Intelligence 분석가입니다.
SK네트웍스는 지주사(Holding Company)로서 5개 핵심 계열사를 관리합니다.
아래 데이터를 기반으로 경영진의 비즈니스 질문에 전문적으로 답변합니다.

## 역할
- 지주사 경영진 관점의 계열사 포트폴리오 분석
- 데이터에 근거한 정확한 답변 (숫자, 비율, 추세 포함)
- 근본 원인 분석 (Why) 및 실행 가능한 제안 (Action)
- 간결하고 구조적인 답변 (bullet point, 표 활용)

## SK네트웍스 계열사 구조
- **SK매직** (SK_Magic): 정수기/공기청정기/비데 렌탈 (구독형, B2C)
- **SK렌터카** (SK_Rentacar): 자동차 렌탈/리스/FMS (자산운영형, B2B/B2C)
- **민팃** (Mintit): 중고 전자기기 거래 플랫폼/ATM 키오스크 (플랫폼형)
- **워커힐** (Walkerhill): 호텔/리조트/F&B (서비스형, B2C)
- **SK네트웍스서비스** (SKN_Service): ICT 인프라 유지보수 (서비스형, B2B)

## 4대 관리영역
- 성과(Performance): 연결 EBITDA, ROE, FCF, 계열사별 이익기여
- 운영(Operation): 구독자수/이탈률(Churn), 자산가동률(차량/객실/키오스크), CCC
- 투자(Investment): 포트폴리오 가치, 지분법이익, 신사업투자(AI/모빌리티/플랫폼)
- 리스크(Risk): 재무건전성, 시장리스크, ESG, 규제리스크(렌탈/개인정보/공정거래)

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
        fins = session.query(Financial).order_by(Financial.period.desc()).limit(30).all()
        fin_records = []
        for f in fins:
            fin_records.append({
                "계열사": BUSINESS_UNITS.get(f.bu_id, {}).get("name", f.bu_id),
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
                "계약잔고": round(f.backlog),
                "계획매출": round(f.plan_revenue),
                "계획EBITDA": round(f.plan_ebitda),
            })

        # 2. 최신 KPI 값
        latest_period = session.query(Financial.period).order_by(Financial.period.desc()).first()
        kpi_records = []
        if latest_period:
            kpi_vals = (
                session.query(KPIValue)
                .filter(KPIValue.period == latest_period[0])
                .all()
            )
            kpi_def_map = {d.id: d for d in session.query(KPIDefinition).all()}

            for val in kpi_vals:
                defn = kpi_def_map.get(val.kpi_id)
                if defn:
                    name, cat, unit = defn.name, defn.category, defn.unit
                else:
                    name, cat, unit = val.kpi_id, "unknown", ""

                kpi_records.append({
                    "KPI_ID": val.kpi_id,
                    "KPI명": name,
                    "영역": cat,
                    "단위": unit,
                    "계열사": BUSINESS_UNITS.get(val.bu_id, {}).get("name", val.bu_id),
                    "실적": round(val.actual, 2) if val.actual else None,
                    "계획": round(val.plan, 2) if val.plan else None,
                    "Gap%": round(val.gap_pct * 100, 1) if val.gap_pct else None,
                })

        # 3. KPI 정의 (Driver Tree)
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
                "계열사": BUSINESS_UNITS.get(r.bu_id, {}).get("name", r.bu_id),
                "카테고리": r.category,
                "설명": r.description,
                "발생확률": r.probability,
                "영향도": r.impact,
                "Risk_Score": round(r.risk_score, 2),
            })

        # 5. Biz Question Pool
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

    if data["financial"]:
        df = pd.DataFrame(data["financial"])
        latest = df[df["기간"] == df["기간"].max()]
        parts.append("## 최신 월 재무 실적 (계열사별)")
        for _, row in latest.iterrows():
            gap_rev = (row["매출"] / row["계획매출"] - 1) * 100 if row["계획매출"] else 0
            gap_ebitda = (row["EBITDA"] / row["계획EBITDA"] - 1) * 100 if row["계획EBITDA"] else 0
            parts.append(
                f"- **{row['계열사']}** ({row['기간']}): "
                f"매출 {row['매출']:,}억 (계획대비 {gap_rev:+.1f}%), "
                f"EBITDA {row['EBITDA']:,}억 (계획대비 {gap_ebitda:+.1f}%), "
                f"영업이익 {row['영업이익']:,}억, CAPEX {row['CAPEX']:,}억, "
                f"계약잔고 {row['계약잔고']:,}억"
            )

        total = latest[["매출", "매출원가", "매출총이익", "판관비", "EBITDA", "영업이익", "CAPEX", "계약잔고", "계획매출", "계획EBITDA"]].sum()
        gap_rev_t = (total["매출"] / total["계획매출"] - 1) * 100 if total["계획매출"] else 0
        gap_ebitda_t = (total["EBITDA"] / total["계획EBITDA"] - 1) * 100 if total["계획EBITDA"] else 0
        parts.append(
            f"- **연결 합계**: 매출 {total['매출']:,.0f}억 (계획대비 {gap_rev_t:+.1f}%), "
            f"EBITDA {total['EBITDA']:,.0f}억 (계획대비 {gap_ebitda_t:+.1f}%), "
            f"영업이익 {total['영업이익']:,.0f}억, CAPEX {total['CAPEX']:,.0f}억"
        )

        parts.append("\n## 최근 3개월 추이 (계열사별)")
        recent_3m = df.sort_values(["계열사", "기간"]).groupby("계열사").tail(3)
        for bu in recent_3m["계열사"].unique():
            bu_data = recent_3m[recent_3m["계열사"] == bu]
            trend = ", ".join([f"{r['기간'][-5:]}: 매출{r['매출']:,}/EBITDA{r['EBITDA']:,}" for _, r in bu_data.iterrows()])
            parts.append(f"- **{bu}**: {trend}")

    if data["kpi_values"]:
        parts.append("\n## 최신 KPI 실적")
        for kpi in data["kpi_values"]:
            gap_str = f"(Gap: {kpi['Gap%']:+.1f}%)" if kpi['Gap%'] is not None else ""
            parts.append(
                f"- {kpi['KPI_ID']} {kpi['KPI명']} [{kpi['계열사']}]: "
                f"실적 {kpi['실적']} / 계획 {kpi['계획']} {kpi['단위']} {gap_str}"
            )

    if data["kpi_tree"]:
        parts.append("\n## KPI Driver Tree 구조")
        for k in data["kpi_tree"]:
            indent = "  " * k["레벨"]
            parent_str = f" <- {k['상위KPI']}" if k["상위KPI"] else ""
            parts.append(f"{indent}- L{k['레벨']} {k['ID']} {k['이름']} ({k['단위']}){parent_str}")

    if data["risks"]:
        parts.append("\n## 활성 리스크 항목")
        for r in data["risks"]:
            parts.append(f"- [{r['계열사']}] {r['카테고리']}: {r['설명']} (Score: {r['Risk_Score']})")

    return "\n".join(parts)


def _find_matching_biz_question(user_question: str, bq_records: list) -> Optional[dict]:
    """사용자 질문과 가장 관련 있는 Biz Question 매칭"""
    keywords_map = {
        "ebitda": ["BQ001"], "매출": ["BQ001", "BQ002"], "실적": ["BQ001"],
        "성장": ["BQ002"], "달성": ["BQ002"],
        "구독": ["BQ003", "BQ010"], "이탈": ["BQ003"], "churn": ["BQ003"], "해지": ["BQ003"],
        "가동": ["BQ004"], "차량": ["BQ004"], "객실": ["BQ004"], "키오스크": ["BQ004"],
        "포트폴리오": ["BQ005"], "지분": ["BQ005"], "배당": ["BQ005"],
        "투자": ["BQ006"], "ai": ["BQ006"], "모빌리티": ["BQ006"], "신사업": ["BQ006"],
        "부채": ["BQ007"], "재무": ["BQ007"], "유동": ["BQ007"],
        "esg": ["BQ008"], "환경": ["BQ008"],
        "규제": ["BQ009"], "렌탈": ["BQ009"],
        "계정": ["BQ010"], "가입": ["BQ010"], "arpu": ["BQ010"],
        "리스크": ["BQ007"], "위험": ["BQ007"],
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
    """사용자 질문에 대해 DB 데이터 기반 Claude API 답변 생성"""
    data = _fetch_context_data()
    matched_bq = _find_matching_biz_question(user_question, data["biz_questions"])
    data_context = _build_data_context(data)

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
        f"다음은 SK네트웍스의 최신 경영 데이터입니다:\n\n"
        f"{data_context}"
        f"{bq_context}\n\n"
        f"---\n\n"
        f"## 경영진 질문\n{user_question}\n\n"
        f"위 데이터를 기반으로 지주사 경영진 관점에서 정확하고 구조적인 답변을 제공하세요."
    )

    active_client = _get_client()
    if active_client is None:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 미설정. 환경변수, .env 파일, 또는 Streamlit secrets에 설정하세요."
        )

    if stream:
        return active_client.messages.stream(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    else:
        response = active_client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text


def get_matched_biz_question(user_question: str) -> Optional[dict]:
    """사용자 질문에 매칭되는 Biz Question 반환"""
    data = _fetch_context_data()
    return _find_matching_biz_question(user_question, data["biz_questions"])
