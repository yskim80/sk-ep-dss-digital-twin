# SK에코플랜트 DSS Digital Twin - 작업 이력 (2026-03-12)

## 1. Streamlit 앱 실행 확인

- `run.py` 실행하여 로컬 환경에서 앱 정상 동작 확인
- URL: http://localhost:8501
- DB 초기화 + 가상 데이터 생성 (4 BU, 96 Financial, 20 KPI, 576 KPI Values, 10 BizQ, 8 Risk)

---

## 2. CI/CD 및 배포 인프라 구성

### 생성된 파일

| 파일 | 용도 |
|------|------|
| `.gitignore` | `__pycache__/`, `*.db`, `.env`, `secrets.toml` 등 제외 |
| `.streamlit/config.toml` | Streamlit 서버 설정 + 다크 테마 |
| `Dockerfile` | Python 3.11 기반 컨테이너 이미지 빌드 |
| `docker-compose.yml` | 원클릭 Docker 실행 (포트 8501, DB 볼륨) |
| `.github/workflows/ci.yml` | GitHub Actions CI/CD (문법 체크 + Docker 빌드 테스트) |

### 배포 아키텍처

```
[개발자 PC] → git push → [GitHub] → 자동 감지 → [Streamlit Community Cloud]
                                  → GitHub Actions (CI 테스트)
                                        ↓
                                https://sk-ep-dss-digital-twin.streamlit.app
```

---

## 3. Git 저장소 초기화 및 GitHub 연동

- Git 저장소 초기화 (`git init`, branch: `main`)
- GitHub CLI (`gh`) 설치 (winget, v2.88.0)
- GitHub 로그인 (계정: **yskim80**)
- OAuth workflow scope 추가 인증
- GitHub 저장소 생성: **https://github.com/yskim80/sk-ep-dss-digital-twin**
- Initial commit + push 완료

### 커밋 이력

| 커밋 | 내용 |
|------|------|
| `67e5708` | Initial commit: 전체 앱 + CI/CD 인프라 |
| `3e4edf4` | Switch to dark theme for consistent dark mode UI |

---

## 4. 다크 테마 적용

### 변경 파일

**`.streamlit/config.toml`**
- `base = "dark"` 추가
- `backgroundColor`: `#FFFFFF` → `#0E1117`
- `secondaryBackgroundColor`: `#F0F2F6` → `#1A1D23`
- `textColor`: `#262730` → `#FAFAFA`
- `primaryColor`: `#2F5496` → `#4A90D9`

**`app/Home.py`**
- `.main-header` 색상: `#2F5496` → `#4A90D9`
- `.sub-header` 색상: `#666` → `#A0A0A0`

---

## 5. Streamlit Community Cloud 배포

- **URL**: https://sk-ep-dss-digital-twin.streamlit.app
- GitHub 연동 완료 (자동 배포 활성화)
- `git push` 시 자동 재배포

---

## 운영 가이드

### 코드 수정 후 배포 방법
```bash
cd D:/ConsultingVault/Projects/2026_SK_EP_DSS/02_DigitalTwin
git add .
git commit -m "변경 내용 설명"
git push
```
→ 1~2분 후 https://sk-ep-dss-digital-twin.streamlit.app 에 자동 반영

### Docker 로컬 실행 (대안)
```bash
docker-compose up --build
```

### 주요 경로
- 앱 진입점: `app/Home.py`
- 모듈 페이지: `app/pages/1_M1~6_*.py`
- DB 모델: `db/models.py`
- 시드 데이터: `data/seed_data.py`
- AI 엔진: `app/llm_engine.py`
- 설정: `config/settings.py`
