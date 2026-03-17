"""
SK네트웍스 Decision Intelligence - 디지털 트윈 메인
지주사 관점 - 계열사 관리 대시보드
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import MODULES, DECISION_AREAS, BUSINESS_UNITS

st.set_page_config(
    page_title="SK Networks Decision Intelligence",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #4A90D9; margin-bottom: 0.5rem; }
    .sub-header { font-size: 1.1rem; color: #A0A0A0; margin-bottom: 2rem; }
    .module-card { border-radius: 10px; padding: 1.5rem;
                   border-left: 4px solid; margin-bottom: 1rem;
                   border: 1px solid rgba(128,128,128,0.3);
                   border-left-width: 4px; }
    .module-card h5, .module-card p { color: inherit; }
    .decision-area { border-radius: 8px; padding: 1rem;
                     border: 1px solid rgba(128,128,128,0.3); }
    .decision-area h4 { color: inherit; }
    .subsidiary-card { border-radius: 8px; padding: 0.8rem;
                       border: 1px solid rgba(128,128,128,0.3);
                       text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">SK네트웍스 Decision Intelligence</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">지주사 계열사 관리 - Data Driven 의사결정 지원 시스템 - Digital Twin Environment</div>', unsafe_allow_html=True)

st.divider()

# 계열사 구조
st.subheader("계열사 포트폴리오")
bu_icons = {"SK_Magic": "💧", "SK_Rentacar": "🚗", "Mintit": "📱", "Walkerhill": "🏨", "SKN_Service": "🔧"}
bu_types = {"subscription": "구독형", "asset": "자산운영형", "platform": "플랫폼형", "service": "서비스형"}
cols = st.columns(5)
for col, (bu_id, info) in zip(cols, BUSINESS_UNITS.items()):
    with col:
        icon = bu_icons.get(bu_id, "🏢")
        btype = bu_types.get(info["type"], info["type"])
        st.markdown(f"""
        <div class="subsidiary-card" style="border-top: 3px solid {info['color']};">
            <h4>{icon} {info['name']}</h4>
            <p style="font-size: 0.8rem; opacity: 0.7;">{btype}</p>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# 4대 관리영역
st.subheader("4대 의사결정 관리 영역")
cols = st.columns(4)
area_icons = {"performance": "📊", "operation": "⚙️", "investment": "💰", "risk": "🛡️"}
area_colors = {"performance": "#2F5496", "operation": "#548235", "investment": "#BF8F00", "risk": "#C00000"}

for col, (key, name) in zip(cols, DECISION_AREAS.items()):
    with col:
        st.markdown(f"""
        <div class="decision-area" style="border-top: 3px solid {area_colors[key]};">
            <h4>{area_icons[key]} {name}</h4>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# 6대 모듈
st.subheader("시스템 6대 모듈")
module_colors = ["#2F5496", "#548235", "#BF8F00", "#7030A0", "#C00000", "#D4760A"]
module_icons = ["📊", "🌳", "💬", "🔮", "🚨", "💼"]

cols = st.columns(6)
for col, (key, name), color, icon in zip(cols, MODULES.items(), module_colors, module_icons):
    with col:
        st.markdown(f"""
        <div class="module-card" style="border-left-color: {color};">
            <h5>{icon} {key}</h5>
            <p style="font-size: 0.85rem;">{name}</p>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# 디지털 트윈 상태
st.subheader("Digital Twin 환경 상태")

# DB 자동 초기화
SEED_VERSION = 1
try:
    from db.models import SessionLocal, engine
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    table_count = len(insp.get_table_names())

    need_reseed = False
    if table_count == 0:
        need_reseed = True
    else:
        session = SessionLocal()
        total_rows = sum(
            session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            for t in insp.get_table_names()
        )
        if total_rows == 0:
            need_reseed = True
        else:
            # SK네트웍스 버전 체크 (계열사 수로 판별)
            bu_count = session.execute(text("SELECT COUNT(*) FROM business_units")).scalar()
            if bu_count != 5:  # SK네트웍스 5개 계열사
                need_reseed = True
        session.close()

    if need_reseed:
        from data.seed_data import seed_all
        seed_all()
        insp = inspect(engine)
        table_count = len(insp.get_table_names())
        session = SessionLocal()
        total_rows = sum(
            session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            for t in insp.get_table_names()
        )
        session.close()

    db_active = True
except Exception:
    table_count, total_rows, db_active = 0, 0, False

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Database", "SQLite" if db_active else "Disconnected", "Active" if db_active else "Error")
with col2:
    st.metric("Tables", f"{table_count}개", f"{total_rows:,} rows")
with col3:
    st.metric("Data Mode", "Virtual Seed", "Demo")
with col4:
    st.metric("계열사", f"{len(BUSINESS_UNITS)}개사", "5 Subsidiaries")

st.info("**사이드바**에서 각 모듈 페이지로 이동할 수 있습니다. **Data Connection Map** 페이지에서 소스 시스템 연결 현황을 확인하세요.")
