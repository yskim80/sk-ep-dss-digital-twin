"""
SK네트웍스 Decision Intelligence - 디지털 트윈 설정
지주사(Holding Company) 관점 - 계열사 관리 목적
"""
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_DIR = BASE_DIR / "db"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_DIR / 'skn_dss.db'}")

# Business Structure - SK네트웍스 계열사 구조
BUSINESS_UNITS = {
    "SK_Magic": {"name": "SK매직", "type": "subscription", "color": "#2F5496"},
    "SK_Rentacar": {"name": "SK렌터카", "type": "asset", "color": "#548235"},
    "Mintit": {"name": "민팃", "type": "platform", "color": "#BF8F00"},
    "Walkerhill": {"name": "워커힐", "type": "service", "color": "#7030A0"},
    "SKN_Service": {"name": "SK네트웍스서비스", "type": "service", "color": "#C00000"},
}

# 4대 의사결정 관리 영역 (지주사 관점)
DECISION_AREAS = {
    "performance": "성과 관리 (Performance)",
    "operation": "운영 관리 (Operation)",
    "investment": "투자 관리 (Investment)",
    "risk": "리스크 관리 (Risk)",
}

# 6대 모듈
MODULES = {
    "M1": "Executive Dashboard",
    "M2": "Value Driver & Drill-down",
    "M3": "Biz Question Q&A",
    "M4": "Scenario / What-if Simulation",
    "M5": "Early Warning Center",
    "M6": "Portfolio Management",
}

# Demo data config
DEMO_MONTHS = 24  # 2년치 월별 데이터
DEMO_SEED = 42
