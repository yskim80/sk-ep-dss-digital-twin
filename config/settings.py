"""
SK에코플랜트 Decision Intelligence - 디지털 트윈 설정
"""
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_DIR = BASE_DIR / "db"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_DIR / 'ecoplant_dss.db'}")

# Business Structure - SK에코플랜트 사업구조 반영
BUSINESS_UNITS = {
    "EPC_Hitech": {"name": "Hi-tech EPC", "type": "project", "color": "#2F5496"},
    "GreenEnergy": {"name": "Green Energy", "type": "asset", "color": "#548235"},
    "Recycling": {"name": "Recycling", "type": "asset", "color": "#BF8F00"},
    "Solution": {"name": "Solution", "type": "service", "color": "#7030A0"},
}

# 4대 의사결정 관리 영역
DECISION_AREAS = {
    "performance": "성과 관리 (Performance)",
    "operation": "운영 관리 (Operation)",
    "investment": "투자 관리 (Investment)",
    "risk": "리스크 관리 (Risk)",
}

# 5대 모듈
MODULES = {
    "M1": "Executive Dashboard",
    "M2": "Value Driver & Drill-down",
    "M3": "Biz Question Q&A",
    "M4": "Scenario / What-if Simulation",
    "M5": "Early Warning Center",
}

# Demo data config
DEMO_MONTHS = 24  # 2년치 월별 데이터
DEMO_SEED = 42
