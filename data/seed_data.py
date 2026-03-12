"""
SK에코플랜트 DSS - 가상 데이터 생성기 (Seed Data)
에코플랜트 사업구조를 반영한 현실적인 데이터 생성
실제 데이터로 교체만 하면 즉시 운영 가능
"""
import numpy as np
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import BUSINESS_UNITS, DEMO_MONTHS, DEMO_SEED
from db.models import (
    init_db, SessionLocal, BusinessUnit, Financial,
    KPIDefinition, KPIValue, BizQuestion, RiskItem
)


def generate_financials(session, rng):
    """월별 재무 데이터 생성 - 사업부별 특성 반영"""
    today = pd.Timestamp(datetime.now().date())
    months = pd.date_range(end=today.replace(day=1), periods=DEMO_MONTHS, freq="MS")

    bu_params = {
        "EPC_Hitech": {"base_rev": 1500, "trend": 0.008, "cogs_range": (0.72, 0.82), "capex_range": (0.03, 0.06)},
        "GreenEnergy": {"base_rev": 800, "trend": 0.015, "cogs_range": (0.58, 0.68), "capex_range": (0.06, 0.12)},
        "Recycling": {"base_rev": 600, "trend": 0.012, "cogs_range": (0.55, 0.70), "capex_range": (0.04, 0.10)},
        "Solution": {"base_rev": 400, "trend": 0.02, "cogs_range": (0.68, 0.78), "capex_range": (0.02, 0.05)},
    }

    for bu_id, params in bu_params.items():
        base = params["base_rev"]
        trend = params["trend"]
        season_amp = rng.uniform(0.03, 0.08)

        for i, m in enumerate(months):
            seasonality = 1 + season_amp * np.sin(2 * np.pi * (m.month / 12))
            revenue = base * ((1 + trend) ** i) * seasonality + rng.normal(0, base * 0.04)
            revenue = max(100, revenue)

            cogs_ratio = rng.uniform(*params["cogs_range"])
            opex_ratio = rng.uniform(0.08, 0.15)
            cogs = revenue * cogs_ratio
            opex = revenue * opex_ratio
            gross_profit = revenue - cogs
            ebit = gross_profit - opex
            ebitda = ebit + revenue * rng.uniform(0.02, 0.05)  # D&A
            capex = revenue * rng.uniform(*params["capex_range"])
            operating_cf = ebit - 0.5 * capex + rng.normal(0, revenue * 0.02)
            backlog = revenue * rng.uniform(3.5, 8.0) if params["cogs_range"][0] > 0.65 else revenue * rng.uniform(2.0, 5.0)

            plan_rev = base * ((1 + trend * 1.1) ** i) * seasonality
            plan_ebitda = plan_rev * (1 - (params["cogs_range"][0] + params["cogs_range"][1]) / 2 - 0.12) + plan_rev * 0.035

            session.add(Financial(
                bu_id=bu_id, period=m.date(),
                revenue=round(revenue, 1), cogs=round(cogs, 1),
                gross_profit=round(gross_profit, 1), opex=round(opex, 1),
                ebitda=round(ebitda, 1), ebit=round(ebit, 1),
                capex=round(capex, 1), operating_cf=round(operating_cf, 1),
                backlog=round(backlog, 1),
                plan_revenue=round(plan_rev, 1), plan_ebitda=round(plan_ebitda, 1),
            ))


def generate_kpi_definitions(session):
    """KPI 정의 및 Driver Tree 구조 (확장판)"""
    kpis = [
        # ── Level 0 - Top KPIs ──
        ("EBITDA", "EBITDA", "performance", "억원", None, 0, "이자/세금/감가상각 전 영업이익"),
        ("ROIC", "ROIC", "performance", "%", None, 0, "투하자본수익률"),
        ("FCF", "Free Cash Flow", "performance", "억원", None, 0, "잉여현금흐름"),

        # ── Level 1 - EBITDA Drivers ──
        ("REV", "매출액", "performance", "억원", "EBITDA", 1, "총 매출"),
        ("COGS", "매출원가", "performance", "억원", "EBITDA", 1, "매출원가"),
        ("OPEX", "판관비(SG&A)", "performance", "억원", "EBITDA", 1, "판매관리비"),
        ("DA", "감가상각비", "performance", "억원", "EBITDA", 1, "유무형자산 감가상각"),

        # ── Level 2 - Revenue Drivers (사업부별) ──
        ("REV_EPC", "EPC 매출", "performance", "억원", "REV", 2, "EPC/건설 사업부 매출"),
        ("REV_GREEN", "Green Energy 매출", "performance", "억원", "REV", 2, "녹색에너지 매출"),
        ("REV_RECYCLE", "Recycling 매출", "performance", "억원", "REV", 2, "리사이클링 매출"),
        ("REV_SOL", "Solution 매출", "performance", "억원", "REV", 2, "솔루션 매출"),

        # ── Level 2 - SG&A Cost Pool (판관비 분해) ──
        ("OPEX_PERSONNEL", "인건비", "performance", "억원", "OPEX", 2, "급여/복리후생/퇴직급여"),
        ("OPEX_OUTSOURCE", "외주용역비", "performance", "억원", "OPEX", 2, "외주/도급/위탁 비용"),
        ("OPEX_MARKETING", "영업마케팅비", "performance", "억원", "OPEX", 2, "광고/접대/판촉 비용"),
        ("OPEX_RND", "연구개발비", "performance", "억원", "OPEX", 2, "연구개발 투자 비용"),
        ("OPEX_GENERAL", "일반관리비", "performance", "억원", "OPEX", 2, "임차/통신/보험/기타"),

        # ── Level 1 - ROIC Decomposition ──
        ("ROIC_NOPAT", "NOPAT", "performance", "억원", "ROIC", 1, "세후영업이익 = EBIT × (1-t)"),
        ("ROIC_IC", "투하자본", "performance", "억원", "ROIC", 1, "순운전자본 + 순고정자산"),
        # Level 2 - ROIC 사업부 기여도
        ("ROIC_EPC", "EPC ROIC 기여", "performance", "%p", "ROIC", 2, "Hi-tech EPC 사업 ROIC 기여도"),
        ("ROIC_GREEN", "Green ROIC 기여", "performance", "%p", "ROIC", 2, "Green Energy 사업 ROIC 기여도"),
        ("ROIC_RECYCLE", "Recycling ROIC 기여", "performance", "%p", "ROIC", 2, "Recycling 사업 ROIC 기여도"),
        ("ROIC_SOL", "Solution ROIC 기여", "performance", "%p", "ROIC", 2, "Solution 사업 ROIC 기여도"),

        # ── Operation KPIs ──
        ("PRODUCTIVITY", "생산성", "operation", "점", None, 0, "종합 생산성 지수"),
        # Level 1 - 생산성 Driver 분해
        ("PROD_DEMAND", "수요/수주", "operation", "%", "PRODUCTIVITY", 1, "수주전환율, 수요 충족률"),
        ("PROD_UTIL", "설비가동률", "operation", "%", "PRODUCTIVITY", 1, "평균 설비 가동률"),
        ("PROD_PROCESS", "프로세스 효율", "operation", "%", "PRODUCTIVITY", 1, "공정 효율, Yield Rate"),
        # Level 2 - 수요 Driver
        ("DEMAND_ORDER_RATE", "수주전환율", "operation", "%", "PROD_DEMAND", 2, "제안 대비 수주 비율"),
        ("DEMAND_PIPELINE", "파이프라인 충실도", "operation", "억원", "PROD_DEMAND", 2, "향후 12개월 수주 파이프라인"),
        # Level 2 - 가동률 Driver
        ("UTIL_PLANNED", "계획가동시간", "operation", "시간", "PROD_UTIL", 2, "월 계획 가동 시간"),
        ("UTIL_DOWNTIME", "비계획정지시간", "operation", "시간", "PROD_UTIL", 2, "고장/정비 등 비계획 정지"),
        # Level 2 - 프로세스 Driver
        ("PROC_YIELD", "공정수율", "operation", "%", "PROD_PROCESS", 2, "투입 대비 양품 비율"),
        ("PROC_CYCLE", "공정 Cycle Time", "operation", "일", "PROD_PROCESS", 2, "단위 공정 소요 시간"),
        ("PROC_REWORK", "재작업률", "operation", "%", "PROD_PROCESS", 2, "재작업/수정 발생 비율"),

        ("CCC", "현금전환주기", "operation", "일", None, 0, "Cash Conversion Cycle"),
        ("BACKLOG", "수주잔고", "operation", "억원", None, 0, "수주잔고"),

        # ── Investment KPIs ──
        ("CAPEX", "설비투자", "investment", "억원", None, 0, "자본적 지출"),
        ("NPV", "투자NPV", "investment", "억원", None, 0, "순현재가치"),
        ("IRR", "투자IRR", "investment", "%", None, 0, "내부수익률"),
        # 투자 성과 미달 원인 분석
        ("INV_PERF", "투자성과 분석", "investment", "점", None, 0, "투자 프로젝트 성과 종합"),
        ("INV_MARKET", "시장요인", "investment", "점", "INV_PERF", 1, "시장수요 변동, 경쟁 심화, 가격 하락"),
        ("INV_EXEC", "집행요인", "investment", "점", "INV_PERF", 1, "집행률 지연, 일정 초과, 인허가 지연"),
        ("INV_COST", "원가요인", "investment", "점", "INV_PERF", 1, "원자재 상승, 인건비 초과, 설계 변경"),
        # Level 2 - 시장요인 분해
        ("INV_MKT_DEMAND", "수요 변동", "investment", "%", "INV_MARKET", 2, "예상 대비 실제 수요 괴리"),
        ("INV_MKT_PRICE", "판매단가 변동", "investment", "%", "INV_MARKET", 2, "예상 대비 실제 판매단가"),
        ("INV_MKT_COMPETE", "경쟁 환경", "investment", "점", "INV_MARKET", 2, "신규 경쟁자 진입/점유율 변화"),
        # Level 2 - 집행요인 분해
        ("INV_EXEC_RATE", "투자집행률", "investment", "%", "INV_EXEC", 2, "계획 대비 실제 집행 비율"),
        ("INV_EXEC_DELAY", "일정 지연", "investment", "개월", "INV_EXEC", 2, "계획 대비 일정 지연 기간"),
        ("INV_EXEC_PERMIT", "인허가 진척", "investment", "%", "INV_EXEC", 2, "인허가 취득 진행률"),
        # Level 2 - 원가요인 분해
        ("INV_COST_MAT", "원자재 원가", "investment", "%", "INV_COST", 2, "원자재 가격 변동률"),
        ("INV_COST_LABOR", "인건비 초과", "investment", "%", "INV_COST", 2, "계획 대비 인건비 초과율"),
        ("INV_COST_DESIGN", "설계변경 비용", "investment", "억원", "INV_COST", 2, "설계 변경으로 인한 추가 비용"),

        # ── Risk KPIs ──
        ("FX_RISK", "환율리스크", "risk", "점", None, 0, "환율 변동 리스크 스코어"),
        ("ESG_SCORE", "ESG 스코어", "risk", "점", None, 0, "ESG 종합 스코어"),
        ("SAFETY", "안전사고율", "risk", "건/백만시간", None, 0, "LTIR"),
    ]
    for kpi_id, name, cat, unit, parent, level, desc in kpis:
        session.add(KPIDefinition(
            id=kpi_id, name=name, category=cat, unit=unit,
            parent_kpi_id=parent, level=level, description=desc
        ))


def generate_kpi_values(session, rng):
    """KPI 실적/계획 값 생성 (확장판)"""
    today = pd.Timestamp(datetime.now().date())
    months = pd.date_range(end=today.replace(day=1), periods=DEMO_MONTHS, freq="MS")

    simple_kpis = {
        # 기존 KPI
        "CCC": (45, 8),
        "FX_RISK": (0.4, 0.15),
        "ESG_SCORE": (72, 5),
        "SAFETY": (0.3, 0.1),
        "IRR": (12, 3),
        # SG&A Cost Pool (억원 단위, 전사 OPEX의 비율로 생성)
        "OPEX_PERSONNEL": (180, 15),
        "OPEX_OUTSOURCE": (95, 12),
        "OPEX_MARKETING": (45, 8),
        "OPEX_RND": (60, 10),
        "OPEX_GENERAL": (35, 5),
        # 생산성 Driver
        "PRODUCTIVITY": (75, 8),
        "PROD_DEMAND": (72, 10),
        "PROD_UTIL": (85, 5),
        "PROD_PROCESS": (88, 4),
        "DEMAND_ORDER_RATE": (35, 8),
        "DEMAND_PIPELINE": (2500, 400),
        "UTIL_PLANNED": (720, 20),
        "UTIL_DOWNTIME": (45, 15),
        "PROC_YIELD": (94, 3),
        "PROC_CYCLE": (12, 3),
        "PROC_REWORK": (3.5, 1.2),
        # ROIC 사업부 기여도
        "ROIC_NOPAT": (450, 50),
        "ROIC_IC": (3800, 200),
        # 투자 성과 원인 분석
        "INV_PERF": (70, 10),
        "INV_MARKET": (65, 12),
        "INV_EXEC": (72, 10),
        "INV_COST": (68, 11),
        "INV_MKT_DEMAND": (-5, 8),
        "INV_MKT_PRICE": (-3, 6),
        "INV_MKT_COMPETE": (55, 15),
        "INV_EXEC_RATE": (78, 12),
        "INV_EXEC_DELAY": (2.5, 1.5),
        "INV_EXEC_PERMIT": (65, 18),
        "INV_COST_MAT": (8, 5),
        "INV_COST_LABOR": (5, 3),
        "INV_COST_DESIGN": (15, 8),
    }

    # 사업부별 특성 반영 가중치
    bu_weights = {
        "EPC_Hitech": {"PROD_UTIL": 0.9, "PROD_DEMAND": 1.1, "INV_EXEC_DELAY": 1.3, "INV_COST_MAT": 1.2},
        "GreenEnergy": {"PROD_UTIL": 1.1, "PROD_DEMAND": 0.9, "INV_MARKET": 0.85, "INV_COST_MAT": 1.1},
        "Recycling": {"PROD_UTIL": 0.85, "PROD_PROCESS": 0.95, "INV_EXEC_RATE": 0.9, "PROC_YIELD": 0.97},
        "Solution": {"PROD_DEMAND": 1.15, "PROD_UTIL": 1.05, "INV_MARKET": 1.1, "DEMAND_ORDER_RATE": 1.1},
    }

    for bu_id in BUSINESS_UNITS:
        for kpi_id, (mean, std) in simple_kpis.items():
            weight = bu_weights.get(bu_id, {}).get(kpi_id, 1.0)
            for m in months:
                actual = max(0, rng.normal(mean * weight, std))
                plan = mean * weight * rng.uniform(0.98, 1.05)
                gap = actual - plan
                session.add(KPIValue(
                    kpi_id=kpi_id, bu_id=bu_id, period=m.date(),
                    actual=round(actual, 2), plan=round(plan, 2),
                    gap=round(gap, 2), gap_pct=round(gap / plan if plan else 0, 4)
                ))

    # ROIC 사업부별 기여도 (별도 생성)
    roic_contrib = {"ROIC_EPC": 4.2, "ROIC_GREEN": 3.1, "ROIC_RECYCLE": 2.5, "ROIC_SOL": 1.8}
    bu_map = {"ROIC_EPC": "EPC_Hitech", "ROIC_GREEN": "GreenEnergy",
              "ROIC_RECYCLE": "Recycling", "ROIC_SOL": "Solution"}
    for kpi_id, base_val in roic_contrib.items():
        mapped_bu = bu_map[kpi_id]
        for m in months:
            actual = max(0, rng.normal(base_val, 0.8))
            plan = base_val * rng.uniform(1.0, 1.08)
            gap = actual - plan
            session.add(KPIValue(
                kpi_id=kpi_id, bu_id=mapped_bu, period=m.date(),
                actual=round(actual, 2), plan=round(plan, 2),
                gap=round(gap, 2), gap_pct=round(gap / plan if plan else 0, 4)
            ))


def generate_biz_questions(session):
    """Biz Question Pool"""
    questions = [
        ("BQ001", "performance", "이번 분기 EBITDA 목표 대비 편차는 어느 사업부에서 발생했으며 주요 원인은?",
         "EBITDA 목표-실적 편차 > 5%", "driver_tree", "EBITDA,REV,COGS,OPEX", 1),
        ("BQ002", "performance", "계열사별 매출 성장률 추세와 계획 달성률은?",
         "분기 마감 시점", "snapshot", "REV,REV_EPC,REV_GREEN,REV_RECYCLE,REV_SOL", 1),
        ("BQ003", "operation", "OPEX 급증 항목은 무엇이며 어떤 비용 레버를 조정해야 하나?",
         "OPEX 전월 대비 10% 이상 증가", "driver_tree", "OPEX,CCC", 2),
        ("BQ004", "operation", "설비 가동률 하락의 원인과 개선 방안은?",
         "가동률 < 80%", "driver_tree", "UTIL", 2),
        ("BQ005", "investment", "투자 집행률과 경제성 지표(NPV/IRR)는 목표 대비 어떤 수준인가?",
         "분기별 투자 리뷰", "snapshot", "CAPEX,NPV,IRR", 2),
        ("BQ006", "investment", "Green Energy 신규 투자의 예상 IRR은? 환율 변동 시나리오별 영향은?",
         "신규 투자 검토 시", "what_if", "IRR,FX_RISK,CAPEX", 3),
        ("BQ007", "risk", "환율 10% 변동 시 계열사별 손익 영향은?",
         "환율 급변동 (일 2% 이상)", "what_if", "FX_RISK,EBITDA", 1),
        ("BQ008", "risk", "ESG 관련 규제 강화 시 대응 방안과 비용 영향은?",
         "ESG Score < 70", "early_warning", "ESG_SCORE,OPEX", 2),
        ("BQ009", "risk", "안전사고 선행지표 이상 징후가 있는 사업장은?",
         "안전 선행지표 임계치 초과", "early_warning", "SAFETY", 1),
        ("BQ010", "performance", "수주잔고 추이와 향후 12개월 매출 전환 예측은?",
         "월별 정기 리뷰", "snapshot", "BACKLOG,REV", 2),
    ]
    for q_id, area, question, trigger, answer_type, kpis, priority in questions:
        session.add(BizQuestion(
            id=q_id, decision_area=area, question=question,
            trigger_condition=trigger, answer_type=answer_type,
            required_kpis=kpis, priority=priority
        ))


def generate_risk_items(session, rng):
    """리스크 항목 생성"""
    risks = [
        ("EPC_Hitech", "market", "원자재(철강/시멘트) 가격 급등으로 프로젝트 마진 압박"),
        ("EPC_Hitech", "operational", "해외 프로젝트 공정 지연 리스크 (인허가/날씨)"),
        ("GreenEnergy", "regulatory", "탄소배출권 가격 변동에 따른 수익성 영향"),
        ("GreenEnergy", "market", "재생에너지 REC 가격 하락 가능성"),
        ("Recycling", "operational", "폐기물 처리 설비 노후화에 따른 가동률 저하"),
        ("Recycling", "regulatory", "환경부 폐기물 관리법 강화"),
        ("Solution", "market", "경쟁 심화에 따른 수주 감소"),
        ("Solution", "financial", "프로젝트 대금 회수 지연"),
    ]
    for bu_id, category, desc in risks:
        prob = rng.uniform(0.1, 0.8)
        impact = rng.uniform(0.2, 0.9)
        session.add(RiskItem(
            bu_id=bu_id, category=category, description=desc,
            probability=round(prob, 2), impact=round(impact, 2),
            risk_score=round(prob * impact, 3)
        ))


def seed_all():
    """전체 가상 데이터 생성"""
    rng = np.random.default_rng(DEMO_SEED)
    init_db()
    session = SessionLocal()

    try:
        # 기존 데이터 삭제
        for table in [RiskItem, KPIValue, Financial, BizQuestion, KPIDefinition, BusinessUnit]:
            session.query(table).delete()
        session.commit()

        # 사업부 생성
        for bu_id, info in BUSINESS_UNITS.items():
            session.add(BusinessUnit(id=bu_id, name=info["name"], biz_type=info["type"]))
        session.commit()

        generate_kpi_definitions(session)
        session.commit()

        generate_financials(session, rng)
        generate_kpi_values(session, rng)
        generate_biz_questions(session)
        generate_risk_items(session, rng)
        session.commit()

        # Summary
        print("=== Seed Data Generated ===")
        print(f"Business Units: {session.query(BusinessUnit).count()}")
        print(f"Financial Records: {session.query(Financial).count()}")
        print(f"KPI Definitions: {session.query(KPIDefinition).count()}")
        print(f"KPI Values: {session.query(KPIValue).count()}")
        print(f"Biz Questions: {session.query(BizQuestion).count()}")
        print(f"Risk Items: {session.query(RiskItem).count()}")

    finally:
        session.close()


if __name__ == "__main__":
    seed_all()
