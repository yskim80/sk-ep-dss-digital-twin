"""
DB 자동 초기화 헬퍼 - 각 페이지 진입 시 DB가 준비되었는지 확인
Streamlit Cloud에서 Home 페이지를 거치지 않고 직접 페이지 접속 시에도 동작
"""
import streamlit as st

@st.cache_resource
def ensure_db():
    """DB가 존재하고 데이터가 있는지 확인, 없으면 seed 실행"""
    try:
        from db.models import SessionLocal, engine, init_db
        from sqlalchemy import inspect, text

        init_db()
        insp = inspect(engine)
        tables = insp.get_table_names()

        if not tables:
            from data.seed_data import seed_all
            seed_all()
            return True

        session = SessionLocal()
        try:
            total = sum(
                session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                for t in tables
            )
            if total == 0:
                session.close()
                from data.seed_data import seed_all
                seed_all()
                return True

            bu_count = session.execute(text("SELECT COUNT(*) FROM business_units")).scalar()
            if bu_count != 5:
                session.close()
                from data.seed_data import seed_all
                seed_all()
                return True
        finally:
            session.close()

        return True
    except Exception as e:
        st.error(f"DB 초기화 실패: {e}")
        return False
