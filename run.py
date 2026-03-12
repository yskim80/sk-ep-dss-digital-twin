"""
SK에코플랜트 DSS 디지털 트윈 - 실행 스크립트
1. DB 초기화
2. 가상 데이터 생성
3. Streamlit 앱 실행
"""
import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

print("=" * 50)
print("SK에코플랜트 Decision Intelligence - Digital Twin")
print("=" * 50)

# Step 1 & 2: DB init + seed data
print("\n[1/2] Database 초기화 & 가상 데이터 생성...")
from data.seed_data import seed_all
seed_all()

# Step 3: Launch Streamlit
print("\n[2/2] Streamlit 앱 실행...")
print("브라우저에서 http://localhost:8501 로 접속하세요.")
print("종료하려면 Ctrl+C를 누르세요.\n")

subprocess.run([
    sys.executable, "-m", "streamlit", "run",
    os.path.join("app", "Home.py"),
    "--server.port", "8501",
    "--server.headless", "true",
    "--browser.gatherUsageStats", "false",
])
