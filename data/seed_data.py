"""
SK네트웍스 DSS - 가상 데이터 생성기 (Seed Data)
지주사 관점: 계열사별 성과/운영/투자/리스크 관리
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
    KPIDefinition, KPIValue, BizQuestion, RiskItem,
    PortfolioHolding, InvestmentProject,
)


def generate_financials(session, rng):
    """월별 재무 데이터 생성 - 계열사별 특성 반영"""
    today = pd.Timestamp(datetime.now().date())
    months = pd.date_range(end=today.replace(day=1), periods=DEMO_MONTHS, freq="MS")

    bu_params = {
        "SK_Magic": {"base_rev": 450, "trend": 0.012, "cogs_range": (0.35, 0.45), "capex_range": (0.08, 0.15)},
        "SK_Rentacar": {"base_rev": 380, "trend": 0.008, "cogs_range": (0.55, 0.65), "capex_range": (0.15, 0.25)},
        "Mintit": {"base_rev": 120, "trend": 0.025, "cogs_range": (0.50, 0.60), "capex_range": (0.05, 0.10)},
        "Walkerhill": {"base_rev": 200, "trend": 0.010, "cogs_range": (0.45, 0.55), "capex_range": (0.04, 0.08)},
        "SKN_Service": {"base_rev": 300, "trend": 0.006, "cogs_range": (0.60, 0.70), "capex_range": (0.03, 0.06)},
    }

    for bu_id, params in bu_params.items():
        base = params["base_rev"]
        trend = params["trend"]
        season_amp = rng.uniform(0.03, 0.08)

        for i, m in enumerate(months):
            # 워커힐: 계절성 강화 (여름/겨울 성수기)
            if bu_id == "Walkerhill":
                seasonality = 1 + 0.15 * np.sin(2 * np.pi * ((m.month - 1) / 12))
            else:
                seasonality = 1 + season_amp * np.sin(2 * np.pi * (m.month / 12))

            revenue = base * ((1 + trend) ** i) * seasonality + rng.normal(0, base * 0.04)
            revenue = max(50, revenue)

            cogs_ratio = rng.uniform(*params["cogs_range"])
            opex_ratio = rng.uniform(0.10, 0.18)
            cogs = revenue * cogs_ratio
            opex = revenue * opex_ratio
            gross_profit = revenue - cogs
            ebit = gross_profit - opex
            ebitda = ebit + revenue * rng.uniform(0.03, 0.07)  # D&A (렌탈/자산 사업은 D&A 비중 높음)
            capex = revenue * rng.uniform(*params["capex_range"])
            operating_cf = ebit - 0.4 * capex + rng.normal(0, revenue * 0.02)
            # 구독/렌탈 사업은 수주잔고 대신 계약잔고 개념
            backlog = revenue * rng.uniform(8.0, 15.0) if params["cogs_range"][0] < 0.50 else revenue * rng.uniform(3.0, 6.0)

            plan_rev = base * ((1 + trend * 1.1) ** i) * seasonality
            plan_ebitda = plan_rev * (1 - (params["cogs_range"][0] + params["cogs_range"][1]) / 2 - 0.14) + plan_rev * 0.05

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
    """KPI 정의 및 Driver Tree 구조 - 지주사 관점"""
    kpis = [
        # ══════════════════════════════════════════════
        # Performance 영역 - 연결 실적 중심
        # ══════════════════════════════════════════════

        # ── Level 0 - Top KPIs ──
        ("EBITDA", "연결 EBITDA", "performance", "억원", None, 0, "연결기준 이자/세금/감가상각 전 영업이익"),
        ("ROE", "ROE", "performance", "%", None, 0, "자기자본이익률"),
        ("FCF", "Free Cash Flow", "performance", "억원", None, 0, "잉여현금흐름"),

        # ── Level 1 - EBITDA Drivers (계열사별) ──
        ("REV", "연결 매출액", "performance", "억원", "EBITDA", 1, "연결기준 총 매출"),
        ("COGS", "연결 매출원가", "performance", "억원", "EBITDA", 1, "연결기준 매출원가"),
        ("OPEX", "연결 판관비", "performance", "억원", "EBITDA", 1, "연결기준 판매관리비"),
        ("DA", "감가상각비", "performance", "억원", "EBITDA", 1, "유무형자산 감가상각 (렌탈자산 포함)"),

        # ── Level 2 - Revenue Drivers (계열사별 매출) ──
        ("REV_MAGIC", "SK매직 매출", "performance", "억원", "REV", 2, "정수기/공기청정기/비데 렌탈 매출"),
        ("REV_RENT", "SK렌터카 매출", "performance", "억원", "REV", 2, "자동차 렌탈/리스/FMS 매출"),
        ("REV_MINTIT", "민팃 매출", "performance", "억원", "REV", 2, "중고폰 거래 플랫폼 매출"),
        ("REV_WALKER", "워커힐 매출", "performance", "억원", "REV", 2, "호텔/리조트/F&B 매출"),
        ("REV_SVC", "SK네트웍스서비스 매출", "performance", "억원", "REV", 2, "ICT 인프라 유지보수 매출"),

        # ── Level 2 - OPEX 분해 ──
        ("OPEX_PERSONNEL", "인건비", "performance", "억원", "OPEX", 2, "급여/복리후생/퇴직급여"),
        ("OPEX_MARKETING", "마케팅비", "performance", "억원", "OPEX", 2, "광고/프로모션/고객획득비"),
        ("OPEX_LOGISTICS", "물류/배송비", "performance", "억원", "OPEX", 2, "배송/설치/회수 비용"),
        ("OPEX_IT", "IT운영비", "performance", "억원", "OPEX", 2, "시스템/플랫폼 운영 비용"),
        ("OPEX_GENERAL", "일반관리비", "performance", "억원", "OPEX", 2, "임차/통신/보험/기타"),

        # ── Level 1 - ROE Decomposition ──
        ("ROE_NI", "당기순이익", "performance", "억원", "ROE", 1, "연결기준 당기순이익"),
        ("ROE_EQUITY", "자기자본", "performance", "억원", "ROE", 1, "연결기준 자기자본"),
        # Level 2 - ROE 계열사 기여도
        ("ROE_MAGIC", "SK매직 이익기여", "performance", "%p", "ROE", 2, "SK매직 순이익 기여도"),
        ("ROE_RENT", "SK렌터카 이익기여", "performance", "%p", "ROE", 2, "SK렌터카 순이익 기여도"),
        ("ROE_MINTIT", "민팃 이익기여", "performance", "%p", "ROE", 2, "민팃 순이익 기여도"),
        ("ROE_WALKER", "워커힐 이익기여", "performance", "%p", "ROE", 2, "워커힐 순이익 기여도"),
        ("ROE_SVC", "SKN서비스 이익기여", "performance", "%p", "ROE", 2, "SK네트웍스서비스 순이익 기여도"),

        # ══════════════════════════════════════════════
        # Operation 영역 - 구독/렌탈/플랫폼 운영 KPI
        # ══════════════════════════════════════════════

        # ── 구독경제 지표 ──
        ("SUBSCRIPTION", "구독경제 종합", "operation", "점", None, 0, "구독/렌탈 사업 종합 지표"),
        # Level 1
        ("SUB_BASE", "총 구독자(계정)수", "operation", "만건", "SUBSCRIPTION", 1, "전체 계열사 렌탈/구독 계정 수"),
        ("SUB_ARPU", "ARPU", "operation", "만원", "SUBSCRIPTION", 1, "가입자당 월 평균 매출"),
        ("SUB_CHURN", "이탈률(Churn)", "operation", "%", "SUBSCRIPTION", 1, "월간 계약 해지율"),
        # Level 2 - 구독자 Driver
        ("SUB_MAGIC_ACC", "SK매직 계정수", "operation", "만건", "SUB_BASE", 2, "정수기/공기청정기 렌탈 계정"),
        ("SUB_RENT_ACC", "SK렌터카 계정수", "operation", "만건", "SUB_BASE", 2, "자동차 렌탈/리스 계약 건"),
        ("SUB_NEW", "신규가입수", "operation", "건/월", "SUB_BASE", 2, "월간 신규 가입 건수"),
        ("SUB_RENEW", "재가입률", "operation", "%", "SUB_BASE", 2, "만기 후 재가입/연장 비율"),
        # Level 2 - 이탈률 Driver
        ("CHURN_MAGIC", "SK매직 이탈률", "operation", "%", "SUB_CHURN", 2, "정수기/공기청정기 월간 이탈률"),
        ("CHURN_RENT", "SK렌터카 이탈률", "operation", "%", "SUB_CHURN", 2, "차량 렌탈 조기반납률"),
        ("CHURN_REASON", "불만해지 비율", "operation", "%", "SUB_CHURN", 2, "서비스 불만 사유 해지 비율"),

        # ── 자산 효율 ──
        ("ASSET_UTIL", "자산가동률 종합", "operation", "%", None, 0, "핵심 자산 가동률 종합"),
        # Level 1
        ("UTIL_VEHICLE", "차량가동률", "operation", "%", "ASSET_UTIL", 1, "전체 보유 차량 가동 비율"),
        ("UTIL_HOTEL", "객실점유율(OCC)", "operation", "%", "ASSET_UTIL", 1, "워커힐 객실 점유율"),
        ("UTIL_KIOSK", "키오스크 가동률", "operation", "%", "ASSET_UTIL", 1, "민팃 ATM/키오스크 가동률"),
        # Level 2 - 차량가동률 Driver
        ("VH_TOTAL", "보유차량 대수", "operation", "대", "UTIL_VEHICLE", 2, "전체 렌탈 차량 보유 대수"),
        ("VH_ACTIVE", "운용중 차량", "operation", "대", "UTIL_VEHICLE", 2, "현재 렌탈 중인 차량 수"),
        ("VH_MAINT", "정비중 차량", "operation", "대", "UTIL_VEHICLE", 2, "정비/수리 중 비가동 차량"),
        # Level 2 - 객실점유율 Driver
        ("HOTEL_ADR", "ADR(평균객단가)", "operation", "만원", "UTIL_HOTEL", 2, "Average Daily Rate"),
        ("HOTEL_REVPAR", "RevPAR", "operation", "만원", "UTIL_HOTEL", 2, "Revenue Per Available Room"),

        # ── CCC (현금전환주기) ──
        ("CCC", "현금전환주기", "operation", "일", None, 0, "Cash Conversion Cycle"),
        ("CCC_AR", "매출채권회전일", "operation", "일", "CCC", 1, "매출채권 평균 회수 기간"),
        ("CCC_INV", "재고회전일", "operation", "일", "CCC", 1, "재고 평균 보유 기간"),
        ("CCC_AP", "매입채무회전일", "operation", "일", "CCC", 1, "매입채무 평균 지급 기간"),

        # ══════════════════════════════════════════════
        # Investment 영역 - 포트폴리오/신사업 투자
        # ══════════════════════════════════════════════

        ("INV_PERF", "투자성과 종합", "investment", "점", None, 0, "포트폴리오 투자 성과 종합"),
        # Level 1
        ("PORTFOLIO_VAL", "포트폴리오 가치", "investment", "억원", "INV_PERF", 1, "계열사 지분가치 합계"),
        ("EQUITY_INCOME", "지분법이익", "investment", "억원", "INV_PERF", 1, "비연결 투자 지분법이익"),
        ("DIV_YIELD", "배당수익률", "investment", "%", "INV_PERF", 1, "계열사 배당 수익률"),
        # Level 2 - 포트폴리오 분해
        ("PV_MAGIC", "SK매직 지분가치", "investment", "억원", "PORTFOLIO_VAL", 2, "SK매직 지분 평가 가치"),
        ("PV_RENT", "SK렌터카 지분가치", "investment", "억원", "PORTFOLIO_VAL", 2, "SK렌터카 지분 평가 가치"),
        ("PV_MINTIT", "민팃 지분가치", "investment", "억원", "PORTFOLIO_VAL", 2, "민팃 지분 평가 가치"),
        ("PV_WALKER", "워커힐 지분가치", "investment", "억원", "PORTFOLIO_VAL", 2, "워커힐 지분 평가 가치"),

        # ── 신사업 투자 ──
        ("NEW_BIZ", "신사업 투자", "investment", "점", None, 0, "신사업/M&A 투자 성과"),
        ("NB_CAPEX", "신사업 CAPEX", "investment", "억원", "NEW_BIZ", 1, "신사업 자본적 지출"),
        ("NB_IRR", "신사업 IRR", "investment", "%", "NEW_BIZ", 1, "신사업 투자 내부수익률"),
        ("NB_PAYBACK", "투자 회수기간", "investment", "년", "NEW_BIZ", 1, "투자금 회수 예상 기간"),
        # Level 2 - 신사업 분야별
        ("NB_AI", "AI/DT 투자", "investment", "억원", "NB_CAPEX", 2, "AI/디지털전환 투자"),
        ("NB_MOBILITY", "모빌리티 투자", "investment", "억원", "NB_CAPEX", 2, "EV/모빌리티 신규 투자"),
        ("NB_PLATFORM", "플랫폼 투자", "investment", "억원", "NB_CAPEX", 2, "민팃 등 플랫폼 확장 투자"),

        # ══════════════════════════════════════════════
        # Risk 영역 - 지주사 리스크 관리
        # ══════════════════════════════════════════════

        ("RISK_MGMT", "리스크 관리 종합", "risk", "점", None, 0, "지주사 리스크 관리 종합 스코어"),
        # Level 1
        ("FIN_RISK", "재무리스크", "risk", "점", "RISK_MGMT", 1, "연결기준 재무 건전성"),
        ("MKT_RISK", "시장리스크", "risk", "점", "RISK_MGMT", 1, "경기변동/경쟁 리스크"),
        ("ESG_SCORE", "ESG 스코어", "risk", "점", "RISK_MGMT", 1, "ESG 종합 스코어"),
        ("REG_RISK", "규제리스크", "risk", "점", "RISK_MGMT", 1, "규제환경 변화 리스크"),
        # Level 2 - 재무리스크 Driver
        ("FIN_DEBT_RATIO", "부채비율", "risk", "%", "FIN_RISK", 2, "연결기준 총부채/자기자본"),
        ("FIN_LIQUIDITY", "유동비율", "risk", "%", "FIN_RISK", 2, "연결기준 유동자산/유동부채"),
        ("FIN_INTEREST", "이자보상배율", "risk", "배", "FIN_RISK", 2, "영업이익/이자비용"),
        ("FIN_NET_DEBT", "순차입금/EBITDA", "risk", "배", "FIN_RISK", 2, "순차입금 대비 EBITDA 배수"),
        # Level 2 - 시장리스크 Driver
        ("MKT_COMPETE", "경쟁강도 지수", "risk", "점", "MKT_RISK", 2, "주요 사업 경쟁 환경 평가"),
        ("MKT_DEMAND", "수요변동성", "risk", "%", "MKT_RISK", 2, "주요 사업 수요 변동 폭"),
        ("MKT_TECH", "기술변화 리스크", "risk", "점", "MKT_RISK", 2, "기술 대체/변화 리스크"),
        # Level 2 - ESG Driver
        ("ESG_ENV", "환경(E) 스코어", "risk", "점", "ESG_SCORE", 2, "탄소배출, 자원순환, 에너지효율"),
        ("ESG_SOCIAL", "사회(S) 스코어", "risk", "점", "ESG_SCORE", 2, "고용, 안전, 고객보호"),
        ("ESG_GOV", "지배구조(G) 스코어", "risk", "점", "ESG_SCORE", 2, "이사회, 윤리경영, 정보공개"),
        # Level 2 - 규제리스크 Driver
        ("REG_RENTAL", "렌탈업 규제", "risk", "점", "REG_RISK", 2, "할부/렌탈 관련 규제 변화"),
        ("REG_PRIVACY", "개인정보 규제", "risk", "점", "REG_RISK", 2, "개인정보보호법 강화 영향"),
        ("REG_FAIR_TRADE", "공정거래 규제", "risk", "점", "REG_RISK", 2, "공정거래/하도급 규제 리스크"),
    ]
    for kpi_id, name, cat, unit, parent, level, desc in kpis:
        session.add(KPIDefinition(
            id=kpi_id, name=name, category=cat, unit=unit,
            parent_kpi_id=parent, level=level, description=desc
        ))


def generate_kpi_values(session, rng):
    """KPI 실적/계획 값 생성 - 계열사별 특성 반영"""
    today = pd.Timestamp(datetime.now().date())
    months = pd.date_range(end=today.replace(day=1), periods=DEMO_MONTHS, freq="MS")

    simple_kpis = {
        # ── Operation KPIs ──
        "SUBSCRIPTION": (78, 6),
        "SUB_BASE": (350, 20),
        "SUB_ARPU": (3.2, 0.3),
        "SUB_CHURN": (2.5, 0.6),
        "SUB_MAGIC_ACC": (220, 12),
        "SUB_RENT_ACC": (85, 5),
        "SUB_NEW": (15000, 2000),
        "SUB_RENEW": (72, 5),
        "CHURN_MAGIC": (2.0, 0.4),
        "CHURN_RENT": (1.8, 0.3),
        "CHURN_REASON": (35, 8),
        "ASSET_UTIL": (82, 5),
        "UTIL_VEHICLE": (88, 4),
        "UTIL_HOTEL": (72, 10),
        "UTIL_KIOSK": (78, 8),
        "VH_TOTAL": (45000, 2000),
        "VH_ACTIVE": (39600, 2500),
        "VH_MAINT": (2500, 600),
        "HOTEL_ADR": (28, 5),
        "HOTEL_REVPAR": (20, 6),
        "CCC": (35, 6),
        "CCC_AR": (42, 8),
        "CCC_INV": (25, 5),
        "CCC_AP": (32, 6),
        # ── Performance KPIs ──
        "OPEX_PERSONNEL": (120, 10),
        "OPEX_MARKETING": (65, 12),
        "OPEX_LOGISTICS": (45, 8),
        "OPEX_IT": (30, 5),
        "OPEX_GENERAL": (25, 4),
        "ROE_NI": (280, 40),
        "ROE_EQUITY": (5200, 300),
        # ── Investment KPIs ──
        "INV_PERF": (72, 8),
        "PORTFOLIO_VAL": (18000, 1500),
        "EQUITY_INCOME": (150, 30),
        "DIV_YIELD": (3.5, 0.8),
        "PV_MAGIC": (8500, 800),
        "PV_RENT": (4500, 400),
        "PV_MINTIT": (2500, 500),
        "PV_WALKER": (2500, 300),
        "NEW_BIZ": (65, 10),
        "NB_CAPEX": (200, 40),
        "NB_IRR": (10, 3),
        "NB_PAYBACK": (5.5, 1.2),
        "NB_AI": (80, 15),
        "NB_MOBILITY": (70, 20),
        "NB_PLATFORM": (50, 12),
        # ── Risk KPIs ──
        "RISK_MGMT": (68, 8),
        "FIN_RISK": (62, 10),
        "MKT_RISK": (55, 12),
        "ESG_SCORE": (74, 5),
        "REG_RISK": (60, 10),
        "FIN_DEBT_RATIO": (95, 15),
        "FIN_LIQUIDITY": (145, 12),
        "FIN_INTEREST": (5.2, 1.0),
        "FIN_NET_DEBT": (2.8, 0.5),
        "MKT_COMPETE": (58, 10),
        "MKT_DEMAND": (12, 5),
        "MKT_TECH": (45, 12),
        "ESG_ENV": (72, 6),
        "ESG_SOCIAL": (76, 5),
        "ESG_GOV": (74, 6),
        "REG_RENTAL": (55, 12),
        "REG_PRIVACY": (62, 10),
        "REG_FAIR_TRADE": (58, 11),
    }

    # 계열사별 특성 반영 가중치
    bu_weights = {
        "SK_Magic": {"SUB_BASE": 1.3, "SUB_CHURN": 0.9, "CHURN_MAGIC": 1.0, "OPEX_LOGISTICS": 1.3},
        "SK_Rentacar": {"UTIL_VEHICLE": 1.0, "SUB_BASE": 0.8, "SUB_CHURN": 0.85, "OPEX_LOGISTICS": 0.8},
        "Mintit": {"UTIL_KIOSK": 1.0, "SUB_BASE": 0.5, "NB_PLATFORM": 1.3, "MKT_TECH": 1.2},
        "Walkerhill": {"UTIL_HOTEL": 1.0, "SUB_BASE": 0.3, "OPEX_MARKETING": 1.2, "MKT_DEMAND": 1.3},
        "SKN_Service": {"SUB_BASE": 0.6, "SUB_CHURN": 0.7, "OPEX_IT": 1.4, "MKT_COMPETE": 0.9},
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

    # ROE 계열사별 기여도 (별도 생성)
    roe_contrib = {"ROE_MAGIC": 3.8, "ROE_RENT": 2.5, "ROE_MINTIT": 1.2, "ROE_WALKER": 1.5, "ROE_SVC": 1.8}
    bu_map = {"ROE_MAGIC": "SK_Magic", "ROE_RENT": "SK_Rentacar",
              "ROE_MINTIT": "Mintit", "ROE_WALKER": "Walkerhill", "ROE_SVC": "SKN_Service"}
    for kpi_id, base_val in roe_contrib.items():
        mapped_bu = bu_map[kpi_id]
        for m in months:
            actual = max(0, rng.normal(base_val, 0.6))
            plan = base_val * rng.uniform(1.0, 1.08)
            gap = actual - plan
            session.add(KPIValue(
                kpi_id=kpi_id, bu_id=mapped_bu, period=m.date(),
                actual=round(actual, 2), plan=round(plan, 2),
                gap=round(gap, 2), gap_pct=round(gap / plan if plan else 0, 4)
            ))


def generate_biz_questions(session):
    """Biz Question Pool - 지주사 관점"""
    questions = [
        ("BQ001", "performance", "이번 분기 연결 EBITDA 목표 대비 편차는 어느 계열사에서 발생했으며 주요 원인은?",
         "EBITDA 목표-실적 편차 > 5%", "driver_tree", "EBITDA,REV,COGS,OPEX", 1),
        ("BQ002", "performance", "계열사별 매출 성장률 추세와 계획 달성률은?",
         "분기 마감 시점", "snapshot", "REV,REV_MAGIC,REV_RENT,REV_MINTIT,REV_WALKER,REV_SVC", 1),
        ("BQ003", "operation", "구독/렌탈 이탈률(Churn) 추이와 이탈 원인 분석은?",
         "월간 이탈률 > 3%", "driver_tree", "SUB_CHURN,CHURN_MAGIC,CHURN_RENT,CHURN_REASON", 1),
        ("BQ004", "operation", "핵심 자산 가동률(차량/객실/키오스크) 현황과 개선 방안은?",
         "가동률 < 목표 5%p 미달", "driver_tree", "ASSET_UTIL,UTIL_VEHICLE,UTIL_HOTEL,UTIL_KIOSK", 2),
        ("BQ005", "investment", "계열사 포트폴리오 가치 변동과 지분법이익 현황은?",
         "분기별 투자 리뷰", "snapshot", "PORTFOLIO_VAL,EQUITY_INCOME,DIV_YIELD", 1),
        ("BQ006", "investment", "신사업(AI/모빌리티/플랫폼) 투자 대비 성과는?",
         "신규 투자 검토 시", "what_if", "NB_CAPEX,NB_IRR,NB_PAYBACK", 2),
        ("BQ007", "risk", "연결기준 재무건전성 지표(부채비율/유동비율) 추이와 전망은?",
         "부채비율 > 100% 또는 유동비율 < 120%", "early_warning", "FIN_DEBT_RATIO,FIN_LIQUIDITY,FIN_INTEREST", 1),
        ("BQ008", "risk", "ESG 스코어 변동 원인과 개선 과제는?",
         "ESG Score 하락 시", "driver_tree", "ESG_SCORE,ESG_ENV,ESG_SOCIAL,ESG_GOV", 2),
        ("BQ009", "risk", "렌탈/구독업 규제 변화가 실적에 미치는 영향은?",
         "규제 변경 발생 시", "what_if", "REG_RENTAL,REG_PRIVACY,REV", 2),
        ("BQ010", "performance", "구독자(계정) 수 추이와 향후 12개월 매출 전환 예측은?",
         "월별 정기 리뷰", "snapshot", "SUB_BASE,SUB_ARPU,REV", 2),
    ]
    for q_id, area, question, trigger, answer_type, kpis, priority in questions:
        session.add(BizQuestion(
            id=q_id, decision_area=area, question=question,
            trigger_condition=trigger, answer_type=answer_type,
            required_kpis=kpis, priority=priority
        ))


def generate_risk_items(session, rng):
    """리스크 항목 생성 - 계열사별"""
    risks = [
        ("SK_Magic", "market", "정수기 시장 성숙화에 따른 성장 둔화 및 경쟁 심화 (코웨이/LG)"),
        ("SK_Magic", "operational", "렌탈 자산 노후화에 따른 서비스 품질 저하 및 이탈률 상승"),
        ("SK_Rentacar", "market", "EV 전환에 따른 차량 잔존가치 변동 리스크"),
        ("SK_Rentacar", "regulatory", "렌탈/리스 회계기준 변경(IFRS16) 영향"),
        ("Mintit", "market", "중고폰 시장 가격 변동성 및 거래량 감소 리스크"),
        ("Mintit", "operational", "키오스크 네트워크 확장 시 운영비 증가"),
        ("Walkerhill", "market", "경기 침체에 따른 여행/레저 수요 감소"),
        ("Walkerhill", "operational", "인건비 상승에 따른 서비스 원가 압박"),
        ("SKN_Service", "market", "ICT 유지보수 시장 가격 경쟁 심화"),
        ("SKN_Service", "financial", "대형 고객 계약 만료에 따른 매출 감소 가능성"),
    ]
    for bu_id, category, desc in risks:
        prob = rng.uniform(0.1, 0.8)
        impact = rng.uniform(0.2, 0.9)
        session.add(RiskItem(
            bu_id=bu_id, category=category, description=desc,
            probability=round(prob, 2), impact=round(impact, 2),
            risk_score=round(prob * impact, 3)
        ))


def generate_portfolio_holdings(session, rng):
    """포트폴리오 보유 현황 생성 - 계열사별 지분투자"""
    today = pd.Timestamp(datetime.now().date())
    months = pd.date_range(end=today.replace(day=1), periods=DEMO_MONTHS, freq="MS")

    holdings_params = {
        "SK_Magic": {
            "stake_pct": 39.3, "base_book": 4200, "base_fair": 8500,
            "invested": 3800, "category": "core",
            "valuation_method": "EV_EBITDA", "eq_income_base": 65, "div_base": 40,
            "roic_base": 12.5, "irr_base": 15.2, "trend": 0.008,
        },
        "SK_Rentacar": {
            "stake_pct": 100.0, "base_book": 3500, "base_fair": 4500,
            "invested": 3200, "category": "core",
            "valuation_method": "DCF", "eq_income_base": 45, "div_base": 30,
            "roic_base": 9.8, "irr_base": 11.5, "trend": 0.006,
        },
        "Mintit": {
            "stake_pct": 100.0, "base_book": 1200, "base_fair": 2500,
            "invested": 1500, "category": "growth",
            "valuation_method": "PER", "eq_income_base": -8, "div_base": 0,
            "roic_base": -3.2, "irr_base": 18.0, "trend": 0.025,
        },
        "Walkerhill": {
            "stake_pct": 100.0, "base_book": 2800, "base_fair": 2500,
            "invested": 2600, "category": "core",
            "valuation_method": "EV_EBITDA", "eq_income_base": 25, "div_base": 15,
            "roic_base": 6.5, "irr_base": 8.3, "trend": 0.005,
        },
        "SKN_Service": {
            "stake_pct": 100.0, "base_book": 800, "base_fair": 900,
            "invested": 700, "category": "core",
            "valuation_method": "PER", "eq_income_base": 18, "div_base": 12,
            "roic_base": 10.2, "irr_base": 12.0, "trend": 0.004,
        },
    }

    for bu_id, p in holdings_params.items():
        for i, m in enumerate(months):
            growth = (1 + p["trend"]) ** i
            season = 1 + 0.03 * np.sin(2 * np.pi * (m.month / 12))
            noise = rng.normal(1.0, 0.03)

            fair_value = p["base_fair"] * growth * season * noise
            book_value = p["base_book"] * (1 + p["trend"] * 0.5) ** i
            eq_income = max(-50, p["eq_income_base"] * growth * rng.normal(1.0, 0.15))
            div_received = max(0, p["div_base"] * rng.normal(1.0, 0.1)) if m.month in [3, 6, 9, 12] else 0

            session.add(PortfolioHolding(
                bu_id=bu_id, period=m.date(),
                stake_pct=p["stake_pct"],
                book_value=round(book_value, 1),
                fair_value=round(fair_value, 1),
                invested_amount=round(p["invested"] * (1 + p["trend"] * 0.3) ** i, 1),
                equity_income=round(eq_income, 1),
                dividend_received=round(div_received, 1),
                roic=round(p["roic_base"] + rng.normal(0, 1.5), 1),
                irr=round(p["irr_base"] + rng.normal(0, 1.0), 1),
                category=p["category"],
                valuation_method=p["valuation_method"],
            ))


def generate_investment_projects(session, rng):
    """신규 투자 프로젝트 생성"""
    projects = [
        ("INV001", "AI/DT 통합 플랫폼 구축", "SKN_Service", "organic", 350, 0.72,
         18.5, 3.5, "2025-03-01", "2026-12-31", "in_progress", "medium",
         "그룹 AI/디지털전환 역량 내재화 - 계열사 공용 플랫폼", "execution"),
        ("INV002", "민팃 동남아 진출", "Mintit", "organic", 200, 0.35,
         22.0, 4.0, "2025-06-01", "2027-06-30", "in_progress", "high",
         "민팃 ATM 동남아(베트남, 인도네시아) 진출 프로젝트", "execution"),
        ("INV003", "EV 충전 인프라 투자", "SK_Rentacar", "JV", 500, 0.15,
         14.0, 5.5, "2025-09-01", "2028-03-31", "in_progress", "medium",
         "SK렌터카 EV 전환 대비 충전 인프라 JV 투자", "feasibility"),
        ("INV004", "워커힐 리노베이션", "Walkerhill", "organic", 280, 0.88,
         12.0, 6.0, "2024-06-01", "2026-06-30", "in_progress", "low",
         "워커힐 객실 전면 리노베이션 및 F&B 업그레이드", "execution"),
        ("INV005", "스마트홈 구독 서비스", "SK_Magic", "organic", 150, 0.45,
         20.0, 3.0, "2025-10-01", "2027-03-31", "in_progress", "medium",
         "SK매직 스마트홈 IoT 연계 구독 서비스 론칭", "execution"),
        ("INV006", "물류 자동화 솔루션 M&A", None, "MA", 800, 0.05,
         16.0, 4.5, "2026-01-01", "2026-12-31", "planning", "high",
         "물류 자동화 스타트업 인수를 통한 신사업 진출", "feasibility"),
        ("INV007", "그린모빌리티 펀드 출자", "SK_Rentacar", "strategic", 120, 0.50,
         10.0, 7.0, "2025-04-01", "2030-03-31", "in_progress", "low",
         "친환경 모빌리티 벤처펀드 LP 출자", "monitoring"),
        ("INV008", "데이터센터 부지 확보", None, "strategic", 450, 0.10,
         13.0, 8.0, "2026-02-01", "2029-12-31", "planning", "high",
         "AI 인프라 수요 대응 데이터센터 부지 투자 검토", "ideation"),
    ]
    for row in projects:
        p_id, name, bu_id, cat, budget, spent_pct, irr, payback, start, end, status, risk, desc, stage = row
        session.add(InvestmentProject(
            id=p_id, name=name, bu_id=bu_id, category=cat,
            total_budget=budget, spent_amount=round(budget * spent_pct, 1),
            expected_irr=irr, expected_payback=payback,
            start_date=pd.Timestamp(start).date(),
            target_completion=pd.Timestamp(end).date(),
            status=status, risk_level=risk, description=desc, stage=stage,
        ))


def seed_all():
    """전체 가상 데이터 생성"""
    rng = np.random.default_rng(DEMO_SEED)
    init_db()
    session = SessionLocal()

    try:
        # 기존 데이터 삭제
        for table in [InvestmentProject, PortfolioHolding,
                      RiskItem, KPIValue, Financial,
                      BizQuestion, KPIDefinition, BusinessUnit]:
            session.query(table).delete()
        session.commit()

        # 계열사 생성
        for bu_id, info in BUSINESS_UNITS.items():
            session.add(BusinessUnit(id=bu_id, name=info["name"], biz_type=info["type"]))
        session.commit()

        generate_kpi_definitions(session)
        session.commit()

        generate_financials(session, rng)
        generate_kpi_values(session, rng)
        generate_biz_questions(session)
        generate_risk_items(session, rng)
        generate_portfolio_holdings(session, rng)
        generate_investment_projects(session, rng)
        session.commit()

        # Summary
        print("=== SK Networks Seed Data Generated ===")
        print(f"Business Units (계열사): {session.query(BusinessUnit).count()}")
        print(f"Financial Records: {session.query(Financial).count()}")
        print(f"KPI Definitions: {session.query(KPIDefinition).count()}")
        print(f"KPI Values: {session.query(KPIValue).count()}")
        print(f"Biz Questions: {session.query(BizQuestion).count()}")
        print(f"Risk Items: {session.query(RiskItem).count()}")
        print(f"Portfolio Holdings: {session.query(PortfolioHolding).count()}")
        print(f"Investment Projects: {session.query(InvestmentProject).count()}")

    finally:
        session.close()


if __name__ == "__main__":
    seed_all()
