"""
SK네트웍스 DSS - 데이터베이스 모델 (SQLAlchemy ORM)
지주사 관점 계열사 관리 - EVM 테이블 제외
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime,
    ForeignKey, Text, Boolean, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import DATABASE_URL, DB_DIR

DB_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class BusinessUnit(Base):
    """계열사"""
    __tablename__ = "business_units"

    id = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=False)
    biz_type = Column(String(20))  # subscription, asset, platform, service
    parent_id = Column(String(20), ForeignKey("business_units.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    financials = relationship("Financial", back_populates="business_unit")
    kpis = relationship("KPIValue", back_populates="business_unit")
    risks = relationship("RiskItem", back_populates="business_unit")


class Financial(Base):
    """월별 재무 데이터"""
    __tablename__ = "financials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bu_id = Column(String(20), ForeignKey("business_units.id"), nullable=False)
    period = Column(Date, nullable=False)
    revenue = Column(Float)
    cogs = Column(Float)
    gross_profit = Column(Float)
    opex = Column(Float)
    ebitda = Column(Float)
    ebit = Column(Float)
    capex = Column(Float)
    operating_cf = Column(Float)
    backlog = Column(Float)           # 계약잔고 (렌탈/구독)
    plan_revenue = Column(Float)
    plan_ebitda = Column(Float)

    business_unit = relationship("BusinessUnit", back_populates="financials")


class KPIDefinition(Base):
    """KPI 정의 (Driver Tree 구조)"""
    __tablename__ = "kpi_definitions"

    id = Column(String(30), primary_key=True)
    name = Column(String(100), nullable=False)
    category = Column(String(30))
    unit = Column(String(20))
    formula = Column(Text)
    parent_kpi_id = Column(String(30), ForeignKey("kpi_definitions.id"), nullable=True)
    level = Column(Integer, default=0)
    description = Column(Text)

    values = relationship("KPIValue", back_populates="kpi_def")
    children = relationship("KPIDefinition")


class KPIValue(Base):
    """KPI 실적/계획 값"""
    __tablename__ = "kpi_values"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kpi_id = Column(String(30), ForeignKey("kpi_definitions.id"), nullable=False)
    bu_id = Column(String(20), ForeignKey("business_units.id"), nullable=False)
    period = Column(Date, nullable=False)
    actual = Column(Float)
    plan = Column(Float)
    gap = Column(Float)
    gap_pct = Column(Float)

    kpi_def = relationship("KPIDefinition", back_populates="values")
    business_unit = relationship("BusinessUnit", back_populates="kpis")


class BizQuestion(Base):
    """Biz Question 정의"""
    __tablename__ = "biz_questions"

    id = Column(String(20), primary_key=True)
    decision_area = Column(String(20))
    question = Column(Text, nullable=False)
    trigger_condition = Column(Text)
    answer_type = Column(String(30))
    required_kpis = Column(Text)
    priority = Column(Integer, default=3)
    status = Column(String(20), default="defined")


class RiskItem(Base):
    """리스크 항목"""
    __tablename__ = "risk_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bu_id = Column(String(20), ForeignKey("business_units.id"), nullable=False)
    category = Column(String(30))
    description = Column(Text)
    probability = Column(Float)
    impact = Column(Float)
    risk_score = Column(Float)
    status = Column(String(20), default="active")
    detected_at = Column(DateTime, default=datetime.now)
    threshold_kpi_id = Column(String(30), ForeignKey("kpi_definitions.id"), nullable=True)

    business_unit = relationship("BusinessUnit", back_populates="risks")


class PortfolioHolding(Base):
    """투자 포트폴리오 - 계열사별 지분/투자 현황"""
    __tablename__ = "portfolio_holdings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bu_id = Column(String(20), ForeignKey("business_units.id"), nullable=False)
    period = Column(Date, nullable=False)
    stake_pct = Column(Float)           # 지분율 (%)
    book_value = Column(Float)          # 장부가 (억원)
    fair_value = Column(Float)          # 공정가치 (억원)
    invested_amount = Column(Float)     # 누적투자금 (억원)
    equity_income = Column(Float)       # 지분법이익 (억원)
    dividend_received = Column(Float)   # 수취배당 (억원)
    roic = Column(Float)               # ROIC (%)
    irr = Column(Float)                # IRR (%)
    category = Column(String(30))       # core, growth, new_biz
    valuation_method = Column(String(30))  # DCF, EV_EBITDA, PER

    business_unit = relationship("BusinessUnit")


class InvestmentProject(Base):
    """신규 투자 프로젝트 트래커"""
    __tablename__ = "investment_projects"

    id = Column(String(20), primary_key=True)
    name = Column(String(200), nullable=False)
    bu_id = Column(String(20), ForeignKey("business_units.id"), nullable=True)
    category = Column(String(30))       # organic, MA, JV, strategic
    total_budget = Column(Float)        # 총 투자예산 (억원)
    spent_amount = Column(Float)        # 집행액 (억원)
    expected_irr = Column(Float)        # 기대 IRR (%)
    expected_payback = Column(Float)    # 기대 회수기간 (년)
    start_date = Column(Date)
    target_completion = Column(Date)
    status = Column(String(20))         # planning, in_progress, completed, on_hold
    risk_level = Column(String(10))     # low, medium, high
    description = Column(Text)
    stage = Column(String(30))          # ideation, feasibility, execution, monitoring

    business_unit = relationship("BusinessUnit")


class ScenarioRun(Base):
    """What-if 시뮬레이션 실행 이력"""
    __tablename__ = "scenario_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200))
    description = Column(Text)
    parameters = Column(Text)
    results = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(50))


def init_db():
    """데이터베이스 초기화 (테이블 생성)"""
    Base.metadata.create_all(engine)
    print(f"Database initialized: {DATABASE_URL}")


if __name__ == "__main__":
    init_db()
