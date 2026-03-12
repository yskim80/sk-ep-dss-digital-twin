"""
SK에코플랜트 Decision Intelligence - 디지털 트윈 메인
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import MODULES, DECISION_AREAS

st.set_page_config(
    page_title="EcoPlant Decision Intelligence",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #2F5496; margin-bottom: 0.5rem; }
    .sub-header { font-size: 1.1rem; color: #666; margin-bottom: 2rem; }
    .module-card { border-radius: 10px; padding: 1.5rem;
                   border-left: 4px solid; margin-bottom: 1rem;
                   border: 1px solid rgba(128,128,128,0.3);
                   border-left-width: 4px; }
    .module-card h5, .module-card p { color: inherit; }
    .decision-area { border-radius: 8px; padding: 1rem;
                     border: 1px solid rgba(128,128,128,0.3); }
    .decision-area h4 { color: inherit; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">SK에코플랜트 Decision Intelligence</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Data Driven 의사결정 지원 시스템 - Digital Twin Environment</div>', unsafe_allow_html=True)

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

# 5대 모듈
st.subheader("시스템 5대 모듈")
module_colors = ["#2F5496", "#548235", "#BF8F00", "#7030A0", "#C00000"]
module_icons = ["📊", "🌳", "💬", "🔮", "🚨"]

cols = st.columns(5)
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

# DB 실시간 통계
try:
    from db.models import SessionLocal, engine
    from sqlalchemy import inspect, text
    session = SessionLocal()
    insp = inspect(engine)
    table_count = len(insp.get_table_names())
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
    st.metric("Source Systems", "7개 정의", "0 Live / 7 Planned")

st.info("**사이드바**에서 각 모듈 페이지로 이동할 수 있습니다. **Data Connection Map** 페이지에서 소스 시스템 연결 현황을 확인하세요.")
