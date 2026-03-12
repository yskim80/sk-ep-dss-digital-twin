"""KPI Pool 정교화 데이터를 디지털 트윈 DB에 반영"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db.models import SessionLocal, KPIDefinition, BizQuestion, init_db

init_db()
session = SessionLocal()

# 기존 KPI 정의 삭제 후 정교화된 버전으로 교체
session.query(KPIDefinition).delete()
session.query(BizQuestion).delete()
session.commit()

# === 정교화된 KPI 정의 (49개) ===
kpis = [
    # 성과 L0
    ("P-001", "EBITDA", "performance", "억원", None, 0, "이자/세금/감가상각 전 영업이익"),
    ("P-002", "ROIC", "performance", "%", None, 0, "투하자본수익률 = NOPAT/IC"),
    ("P-003", "EVA", "performance", "억원", None, 0, "경제적부가가치 = NOPAT-(IC×WACC)"),
    ("P-004", "FCF", "performance", "억원", None, 0, "잉여현금흐름 = 영업CF-CAPEX"),
    # 성과 L1
    ("P-011", "매출액", "performance", "억원", "P-001", 1, "총 매출 (사업부/계열사별)"),
    ("P-012", "매출원가", "performance", "억원", "P-001", 1, "COGS (재료비+노무비+경비)"),
    ("P-013", "매출총이익률", "performance", "%", "P-001", 1, "(매출-매출원가)/매출×100"),
    ("P-014", "판관비율", "performance", "%", "P-001", 1, "판매관리비/매출×100"),
    ("P-015", "감가상각비", "performance", "억원", "P-001", 1, "유무형자산 감가상각"),
    # 성과 L2
    ("P-021", "EPC/반도체 매출", "performance", "억원", "P-011", 2, "Hi-tech EPC+반도체 인프라"),
    ("P-022", "Green Energy 매출", "performance", "억원", "P-011", 2, "녹색에너지 사업 매출"),
    ("P-023", "Recycling 매출", "performance", "억원", "P-011", 2, "리사이클링 사업 매출"),
    ("P-024", "Solution 매출", "performance", "억원", "P-011", 2, "솔루션 서비스 매출"),
    ("P-025", "계획 대비 달성률", "performance", "%", "P-011", 2, "실적매출/계획매출×100"),
    # 운영 - EPC
    ("O-001", "CPI", "operation", "배수", None, 0, "Cost Performance Index = EV/AC"),
    ("O-002", "SPI", "operation", "배수", None, 0, "Schedule Performance Index = EV/PV"),
    ("O-003", "EAC", "operation", "억원", None, 0, "총예상원가 = AC+(BAC-EV)/CPI"),
    ("O-004", "공정 진척률", "operation", "%", "O-002", 1, "실제진척/계획진척×100"),
    ("O-005", "변경계약(VO) 비율", "operation", "%", "O-001", 1, "변경계약/원도급×100"),
    # 운영 - 설비/자산
    ("O-011", "설비 가동률", "operation", "%", None, 0, "실가동시간/계획가동시간×100"),
    ("O-012", "다운타임", "operation", "시간", "O-011", 1, "비계획 정지 시간"),
    ("O-013", "처리량/수율", "operation", "%", "O-011", 1, "실처리량/설계용량×100"),
    ("O-014", "Diversion Rate", "operation", "%", "O-013", 2, "매립회피/총폐기물×100"),
    ("O-015", "WtE 효율", "operation", "%", "O-013", 2, "에너지회수/투입열량×100"),
    # 운영 - 현금
    ("O-021", "CCC", "operation", "일", None, 0, "현금전환주기=재고+매출채권-매입채무"),
    ("O-022", "매출채권 회전일", "operation", "일", "O-021", 1, "(매출채권/매출)×365"),
    ("O-023", "수주잔고", "operation", "억원", None, 0, "미실행 수주 금액"),
    ("O-024", "미청구공사", "operation", "억원", "O-023", 1, "진행기성-청구기성"),
    ("O-025", "톤당 처리비용", "operation", "만원/톤", "O-013", 2, "총운영비/처리톤수"),
    ("O-026", "Recyclables Revenue/Ton", "operation", "만원/톤", "O-013", 2, "재활용매출/처리톤수"),
    # 투자
    ("I-001", "CAPEX 집행률", "investment", "%", None, 0, "실집행/계획CAPEX×100"),
    ("I-002", "NPV", "investment", "억원", None, 0, "투자 순현재가치"),
    ("I-003", "IRR", "investment", "%", None, 0, "투자 내부수익률"),
    ("I-004", "ROIC-WACC Spread", "investment", "%p", "P-002", 1, "ROIC-WACC (양수=가치창출)"),
    ("I-005", "포트폴리오 비중", "investment", "%", "I-001", 1, "사업부별 투자 비중"),
    ("I-006", "Payback Period", "investment", "년", "I-002", 1, "투자금 회수 기간"),
    ("I-007", "LCOE", "investment", "원/kWh", "I-003", 2, "균등화발전비용"),
    ("I-008", "반도체 FAB 투자 ROI", "investment", "%", "I-003", 2, "FAB EPC 투자수익률"),
    # 리스크
    ("R-001", "Risk Score", "risk", "점(0-1)", None, 0, "발생확률×영향도 종합"),
    ("R-002", "환율 리스크", "risk", "억원/%", "R-001", 1, "환율변동 손익영향도"),
    ("R-003", "원자재 가격 리스크", "risk", "억원/%", "R-001", 1, "원자재가격 변동영향도"),
    ("R-004", "ESG Score", "risk", "점(0-100)", None, 0, "ESG 종합평가 점수"),
    ("R-005", "탄소 배출량", "risk", "tCO2e", "R-004", 1, "Scope1+2 배출량"),
    ("R-006", "안전사고율 (LTIR)", "risk", "건/백만h", None, 0, "재해건수/백만근로시간"),
    ("R-007", "Near-miss 발생률", "risk", "건/월", "R-006", 1, "아차사고 보고건수"),
    ("R-008", "규제 준수율", "risk", "%", "R-004", 1, "점검통과/총점검×100"),
    ("R-009", "부채비율", "risk", "%", None, 0, "총부채/자기자본×100"),
    ("R-010", "차입금의존도", "risk", "%", "R-009", 1, "차입금/총자산×100"),
    ("R-011", "REC/탄소크레딧 가격", "risk", "원", "R-001", 2, "REC/탄소배출권 가격변동"),
]

for kpi_id, name, cat, unit, parent, level, desc in kpis:
    session.add(KPIDefinition(
        id=kpi_id, name=name, category=cat, unit=unit,
        parent_kpi_id=parent, level=level, description=desc
    ))
session.commit()

# === 정교화된 Biz Question (15개) ===
questions = [
    ("BQ-P01", "performance", "이번 분기 EBITDA 목표 대비 편차는 어느 사업부에서 발생했으며 주요 원인(Driver)은?",
     "EBITDA Gap > 5%", "driver_tree", "P-001,P-011,P-012,P-014,P-025", 1),
    ("BQ-P02", "performance", "계열사별 EVA가 양수/음수인 곳은? ROIC-WACC Spread 기준 가치 창출/파괴 사업부는?",
     "ROIC < WACC 발생 시", "snapshot", "P-002,P-003,I-004", 1),
    ("BQ-P03", "performance", "수주잔고 추이와 향후 12개월 매출 전환 예측은?",
     "월별 정기 리뷰", "snapshot", "O-023,P-021,P-022,P-023,P-024", 1),
    ("BQ-P04", "performance", "반도체 EPC 매출 비중과 수익성은? 하이닉스 연관 매출 집중도 리스크는?",
     "분기별 리뷰", "snapshot", "P-021,I-008", 1),
    ("BQ-O01", "operation", "CPI/SPI 기준 원가초과/일정지연 프로젝트는? 근본원인과 대응방안은?",
     "CPI<0.95 또는 SPI<0.90", "driver_tree", "O-001,O-002,O-003,O-004,O-005", 1),
    ("BQ-O02", "operation", "리사이클링 설비 가동률 하락 원인은? 다운타임 패턴과 예방정비 효과는?",
     "가동률 < 80%", "driver_tree", "O-011,O-012,O-013", 1),
    ("BQ-O03", "operation", "OPEX 급증 항목과 톤당 처리비용 변동 원인/비용 레버는?",
     "OPEX 전월비 10% 증가", "driver_tree", "P-014,O-025,O-026", 1),
    ("BQ-O04", "operation", "CCC 악화 원인은? 매출채권 회수 지연 사업부와 개선 방안은?",
     "CCC > 60일", "driver_tree", "O-021,O-022,O-024", 2),
    ("BQ-I01", "investment", "투자 집행률과 NPV/IRR이 기준 이하인 프로젝트는?",
     "분기별 투자 리뷰", "snapshot", "I-001,I-002,I-003", 1),
    ("BQ-I02", "investment", "Green Energy 신규 투자 LCOE는? 환율/보조금 시나리오별 IRR 변화는?",
     "신규 투자 검토 시", "what_if", "I-003,I-007,R-002", 1),
    ("BQ-I03", "investment", "ROIC-WACC Spread 추이로 볼 때 자본 재배분 필요 영역은?",
     "분기별 전략 리뷰", "what_if", "I-004,I-005,P-002", 1),
    ("BQ-R01", "risk", "환율 10% 변동 시 사업부별 손익 영향은? 복합 시나리오 결과는?",
     "환율 일 2% 이상 변동", "what_if", "R-001,R-002,R-003,P-001", 1),
    ("BQ-R02", "risk", "ESG Score 하락 리스크가 있는 사업부는? 가장 큰 위험 요인은?",
     "ESG Score < 70", "early_warning", "R-004,R-005,R-006,R-008", 1),
    ("BQ-R03", "risk", "안전사고 선행지표(Near-miss) 이상 징후 사업장은?",
     "Near-miss 전월비 50% 증가", "early_warning", "R-006,R-007", 1),
    ("BQ-R04", "risk", "재무 리스크(부채비율/차입금) 추이는 IPO 기준에 부합하는가?",
     "분기별 리뷰", "snapshot", "R-009,R-010,P-004", 1),
]

for q_id, area, question, trigger, answer_type, kpis_str, priority in questions:
    session.add(BizQuestion(
        id=q_id, decision_area=area, question=question,
        trigger_condition=trigger, answer_type=answer_type,
        required_kpis=kpis_str, priority=priority
    ))
session.commit()

print("=== KPI Pool & Biz Q Updated ===")
print(f"KPI Definitions: {session.query(KPIDefinition).count()}")
print(f"Biz Questions: {session.query(BizQuestion).count()}")
session.close()
