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
