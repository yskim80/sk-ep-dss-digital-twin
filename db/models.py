"""
SK에코플랜트 DSS - 데이터베이스 모델 (SQLAlchemy ORM)
실제 전환 시 스키마를 그대로 활용할 수 있도록 설계
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
    """사업부/계열사"""
    __tablename__ = "business_units"

    id = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=False)
    biz_type = Column(String(20))  # project, asset, service
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
    period = Column(Date, nullable=False)  # 월초 날짜
    revenue = Column(Float)           # 매출 (억원)
    cogs = Column(Float)              # 매출원가
    gross_profit = Column(Float)      # 매출총이익
    opex = Column(Float)              # 판관비
    ebitda = Column(Float)            # EBITDA
    ebit = Column(Float)              # 영업이익
    capex = Column(Float)             # 투자지출
    operating_cf = Column(Float)      # 영업현금흐름
    backlog = Column(Float)           # 수주잔고
    plan_revenue = Column(Float)      # 계획 매출
    plan_ebitda = Column(Float)       # 계획 EBITDA

    business_unit = relationship("BusinessUnit", back_populates="financials")


class KPIDefinition(Base):
    """KPI 정의 (Driver Tree 구조)"""
    __tablename__ = "kpi_definitions"

    id = Column(String(30), primary_key=True)
    name = Column(String(100), nullable=False)
    category = Column(String(30))     # performance, operation, investment, risk
    unit = Column(String(20))         # 억원, %, 일, 건
    formula = Column(Text)            # 산식
    parent_kpi_id = Column(String(30), ForeignKey("kpi_definitions.id"), nullable=True)
    level = Column(Integer, default=0)  # Driver Tree 깊이
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
    gap = Column(Float)      # actual - plan
    gap_pct = Column(Float)  # gap / plan

    kpi_def = relationship("KPIDefinition", back_populates="values")
    business_unit = relationship("BusinessUnit", back_populates="kpis")


class BizQuestion(Base):
    """Biz Question 정의"""
    __tablename__ = "biz_questions"

    id = Column(String(20), primary_key=True)
    decision_area = Column(String(20))  # performance, operation, investment, risk
    question = Column(Text, nullable=False)
    trigger_condition = Column(Text)
    answer_type = Column(String(30))  # snapshot, driver_tree, early_warning, what_if
    required_kpis = Column(Text)      # comma-separated KPI IDs
    priority = Column(Integer, default=3)  # 1=highest
    status = Column(String(20), default="defined")


class RiskItem(Base):
    """리스크 항목"""
    __tablename__ = "risk_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bu_id = Column(String(20), ForeignKey("business_units.id"), nullable=False)
    category = Column(String(30))     # market, operational, regulatory, financial
    description = Column(Text)
    probability = Column(Float)       # 0-1
    impact = Column(Float)            # 0-1
    risk_score = Column(Float)        # probability * impact
    status = Column(String(20), default="active")
    detected_at = Column(DateTime, default=datetime.now)
    threshold_kpi_id = Column(String(30), ForeignKey("kpi_definitions.id"), nullable=True)

    business_unit = relationship("BusinessUnit", back_populates="risks")


class Project(Base):
    """EPC 프로젝트 마스터"""
    __tablename__ = "projects"

    id = Column(String(20), primary_key=True)
    name = Column(String(200), nullable=False)
    bu_id = Column(String(20), ForeignKey("business_units.id"), nullable=False)
    project_type = Column(String(30))      # semiconductor, battery, display, pharma, energy
    client = Column(String(100))
    contract_value = Column(Float)         # 계약금액 (억원)
    start_date = Column(Date)
    end_date = Column(Date)                # 계획 준공일
    duration_months = Column(Integer)      # 총 공기 (개월)
    status = Column(String(20), default="active")  # active, completed, delayed, at_risk
    bac = Column(Float)                    # Budget At Completion (억원)

    business_unit = relationship("BusinessUnit")
    evm_data = relationship("EVMMonthly", back_populates="project")


class EVMMonthly(Base):
    """EVM 월별 시계열 데이터"""
    __tablename__ = "evm_monthly"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(20), ForeignKey("projects.id"), nullable=False)
    period = Column(Date, nullable=False)           # 측정 월
    month_seq = Column(Integer)                     # 프로젝트 시작 후 경과 월

    # Core EVM metrics
    pv = Column(Float)              # Planned Value (BCWS) - 계획 공정률 기반 누적
    ev = Column(Float)              # Earned Value (BCWP) - 실적 공정률 기반 누적
    ac = Column(Float)              # Actual Cost (ACWP) - 실제 투입 원가 누적

    # Schedule metrics
    pv_rate = Column(Float)         # 계획 공정률 (%)
    ev_rate = Column(Float)         # 실적 공정률 (%)

    # Derived (computed from PV/EV/AC)
    sv = Column(Float)              # Schedule Variance = EV - PV
    cv = Column(Float)              # Cost Variance = EV - AC
    spi = Column(Float)             # Schedule Performance Index = EV / PV
    cpi = Column(Float)             # Cost Performance Index = EV / AC

    # Earned Schedule
    es = Column(Float)              # Earned Schedule (개월) - EV가 PV와 만나는 시점
    ed = Column(Float)              # Earned Duration (개월) - 실제 경과 기간
    es_spi_t = Column(Float)        # SPI(t) = ES / AT (시간 기반 SPI)

    # Forecasting
    eac = Column(Float)             # Estimate At Completion = BAC / CPI
    etc = Column(Float)             # Estimate To Complete = EAC - AC
    vac = Column(Float)             # Variance At Completion = BAC - EAC
    ieac_t = Column(Float)          # Independent EAC(t) = PD / SPI(t) (일정 기반)
    tcpi = Column(Float)            # To-Complete Performance Index = (BAC-EV)/(BAC-AC)

    project = relationship("Project", back_populates="evm_data")


class ScenarioRun(Base):
    """What-if 시뮬레이션 실행 이력"""
    __tablename__ = "scenario_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200))
    description = Column(Text)
    parameters = Column(Text)         # JSON string
    results = Column(Text)            # JSON string
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(50))


def init_db():
    """데이터베이스 초기화 (테이블 생성)"""
    Base.metadata.create_all(engine)
    print(f"Database initialized: {DATABASE_URL}")


if __name__ == "__main__":
    init_db()
