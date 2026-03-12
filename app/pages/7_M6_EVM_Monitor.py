"""M6. EVM (Earned Value Management) - EPC 프로젝트 성과 모니터링"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db.models import SessionLocal, Project, EVMMonthly

st.set_page_config(page_title="M6. EVM Monitor", page_icon="📐", layout="wide")
st.title("M6. EVM (Earned Value Management)")
st.caption("EPC 프로젝트별 S-Curve, CPI/SPI, Earned Schedule/Duration 모니터링")


# ── Data Loading ──
@st.cache_data(ttl=300)
def load_projects():
    session = SessionLocal()
    try:
        projects = session.query(Project).order_by(Project.id).all()
        return [{
            "id": p.id, "name": p.name, "type": p.project_type,
            "client": p.client, "contract": p.contract_value,
            "start": p.start_date, "end": p.end_date,
            "duration": p.duration_months, "status": p.status, "bac": p.bac,
        } for p in projects]
    finally:
        session.close()


@st.cache_data(ttl=300)
def load_evm(project_id):
    session = SessionLocal()
    try:
        records = session.query(EVMMonthly).filter(
            EVMMonthly.project_id == project_id
        ).order_by(EVMMonthly.month_seq).all()
        return pd.DataFrame([{
            "month": r.month_seq, "period": r.period,
            "pv": r.pv, "ev": r.ev, "ac": r.ac,
            "pv_rate": r.pv_rate, "ev_rate": r.ev_rate,
            "sv": r.sv, "cv": r.cv, "spi": r.spi, "cpi": r.cpi,
            "es": r.es, "ed": r.ed, "spi_t": r.es_spi_t,
            "eac": r.eac, "etc": r.etc, "vac": r.vac,
            "ieac_t": r.ieac_t, "tcpi": r.tcpi,
        } for r in records])
    finally:
        session.close()


projects = load_projects()
if not projects:
    st.warning("프로젝트 데이터가 없습니다.")
    st.stop()

proj_df = pd.DataFrame(projects)


# ════════════════════════════════════════════════
# 전사 프로젝트 포트폴리오 개요
# ════════════════════════════════════════════════
st.subheader("EPC 프로젝트 포트폴리오 현황")

# 프로젝트별 최신 EVM 지표 요약
summary_data = []
for _, proj in proj_df.iterrows():
    evm = load_evm(proj["id"])
    if evm.empty:
        continue
    latest = evm.iloc[-1]
    summary_data.append({
        "프로젝트": proj["name"],
        "발주처": proj["client"],
        "유형": proj["type"],
        "계약액(억)": f"{proj['contract']:,.0f}",
        "BAC(억)": f"{proj['bac']:,.0f}",
        "공정률(%)": f"{latest['ev_rate']:.1f}",
        "SPI": latest["spi"],
        "CPI": latest["cpi"],
        "SPI(t)": latest["spi_t"],
        "EAC(억)": f"{latest['eac']:,.0f}",
        "VAC(억)": f"{latest['vac']:+,.0f}",
        "상태": proj["status"],
    })

if summary_data:
    sum_df = pd.DataFrame(summary_data)

    # 상태 메트릭
    col1, col2, col3, col4 = st.columns(4)
    avg_spi = sum_df["SPI"].mean()
    avg_cpi = sum_df["CPI"].mean()
    avg_spi_t = sum_df["SPI(t)"].mean()
    at_risk = sum(1 for r in summary_data if r["SPI"] < 0.95 or r["CPI"] < 0.95)
    col1.metric("전사 평균 SPI", f"{avg_spi:.3f}", "정상" if avg_spi >= 0.95 else "주의")
    col2.metric("전사 평균 CPI", f"{avg_cpi:.3f}", "정상" if avg_cpi >= 0.95 else "주의")
    col3.metric("전사 평균 SPI(t)", f"{avg_spi_t:.3f}", "정상" if avg_spi_t >= 0.95 else "주의")
    col4.metric("주의 프로젝트", f"{at_risk}건 / {len(summary_data)}건")

    # 포트폴리오 CPI vs SPI 산점도
    col_scatter, col_table = st.columns([1, 1])
    with col_scatter:
        st.markdown("#### CPI vs SPI Matrix")
        fig_scatter = go.Figure()

        for row in summary_data:
            color = "#C00000" if row["SPI"] < 0.9 or row["CPI"] < 0.9 else \
                    "#F58220" if row["SPI"] < 0.95 or row["CPI"] < 0.95 else "#548235"
            fig_scatter.add_trace(go.Scatter(
                x=[row["SPI"]], y=[row["CPI"]],
                mode="markers+text", text=[row["프로젝트"][:10]],
                textposition="top center", textfont=dict(size=9),
                marker=dict(size=16, color=color, line=dict(width=1, color="white")),
                showlegend=False,
                hovertemplate=f"{row['프로젝트']}<br>SPI: {row['SPI']:.3f}<br>CPI: {row['CPI']:.3f}<extra></extra>",
            ))

        # 기준선
        fig_scatter.add_hline(y=1.0, line_dash="dash", line_color="#888", line_width=1)
        fig_scatter.add_vline(x=1.0, line_dash="dash", line_color="#888", line_width=1)
        fig_scatter.add_shape(type="rect", x0=0.0, y0=0.0, x1=0.95, y1=0.95,
                              fillcolor="rgba(192,0,0,0.05)", line=dict(width=0))
        fig_scatter.add_annotation(x=0.88, y=0.88, text="Cost+Schedule<br>Risk Zone",
                                   font=dict(color="#C00000", size=10), showarrow=False)
        fig_scatter.update_layout(
            height=380, margin=dict(t=20, b=40),
            xaxis=dict(title="SPI (Schedule)", range=[0.7, 1.2]),
            yaxis=dict(title="CPI (Cost)", range=[0.7, 1.2]),
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col_table:
        st.markdown("#### 프로젝트 요약")
        st.dataframe(
            sum_df.style.applymap(
                lambda v: "color: #C00000" if isinstance(v, float) and v < 0.95
                else "color: #548235" if isinstance(v, float) and v >= 1.0
                else "", subset=["SPI", "CPI", "SPI(t)"]
            ),
            use_container_width=True, hide_index=True, height=380,
        )


# ════════════════════════════════════════════════
# 프로젝트 상세 분석
# ════════════════════════════════════════════════
st.divider()
st.subheader("프로젝트별 EVM 상세 분석")

selected_proj = st.selectbox(
    "프로젝트 선택",
    options=proj_df["id"].tolist(),
    format_func=lambda x: f"{x}: {proj_df[proj_df['id']==x]['name'].values[0]} ({proj_df[proj_df['id']==x]['client'].values[0]})"
)

proj_info = proj_df[proj_df["id"] == selected_proj].iloc[0]
evm_df = load_evm(selected_proj)

if evm_df.empty:
    st.warning("EVM 데이터가 없습니다.")
    st.stop()

latest = evm_df.iloc[-1]

# 프로젝트 정보 카드
st.markdown(f"### {proj_info['name']}")
info_cols = st.columns(6)
info_cols[0].metric("발주처", proj_info["client"])
info_cols[1].metric("계약금액", f"{proj_info['contract']:,.0f}억")
info_cols[2].metric("BAC", f"{proj_info['bac']:,.0f}억")
info_cols[3].metric("공기", f"{proj_info['duration']}개월")
info_cols[4].metric("경과", f"{int(latest['ed'])}개월")
info_cols[5].metric("공정률", f"{latest['ev_rate']:.1f}%")

# EVM 핵심 지표
st.divider()
evm_cols = st.columns(6)
spi_delta = "정상" if latest["spi"] >= 0.95 else "지연" if latest["spi"] >= 0.9 else "심각 지연"
cpi_delta = "정상" if latest["cpi"] >= 0.95 else "초과" if latest["cpi"] >= 0.9 else "심각 초과"
evm_cols[0].metric("SPI", f"{latest['spi']:.3f}", spi_delta)
evm_cols[1].metric("CPI", f"{latest['cpi']:.3f}", cpi_delta)
evm_cols[2].metric("SPI(t)", f"{latest['spi_t']:.3f}",
                    "정상" if latest["spi_t"] >= 0.95 else "주의")
evm_cols[3].metric("EAC", f"{latest['eac']:,.0f}억",
                    f"BAC 대비 {latest['vac']:+,.0f}억")
evm_cols[4].metric("TCPI", f"{latest['tcpi']:.3f}",
                    "달성가능" if latest["tcpi"] <= 1.1 else "어려움")
evm_cols[5].metric("IEAC(t)", f"{latest['ieac_t']:.1f}개월",
                    f"계획 {proj_info['duration']}개월 대비")


# ── TABs ──
tab1, tab2, tab3, tab4 = st.tabs([
    "S-Curve (PV/EV/AC)", "CPI/SPI 추세", "Earned Schedule 분석", "EAC 예측"
])


# ════════════════════════════════════════════════
# TAB 1: S-Curve
# ════════════════════════════════════════════════
with tab1:
    st.subheader("S-Curve (누적 공정률 / 원가)")

    col_rate, col_cost = st.columns(2)

    with col_rate:
        st.markdown("#### 공정률 S-Curve (%)")
        fig_rate = go.Figure()
        fig_rate.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["pv_rate"],
            mode="lines+markers", name="PV (계획 공정률)",
            line=dict(color="#888", width=2, dash="dash"), marker=dict(size=4),
        ))
        fig_rate.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["ev_rate"],
            mode="lines+markers", name="EV (실적 공정률)",
            line=dict(color="#4A90D9", width=2.5), marker=dict(size=5),
        ))
        # Schedule Variance 음영
        fig_rate.add_trace(go.Scatter(
            x=list(evm_df["month"]) + list(evm_df["month"][::-1]),
            y=list(evm_df["pv_rate"]) + list(evm_df["ev_rate"][::-1]),
            fill="toself", fillcolor="rgba(192,0,0,0.08)",
            line=dict(width=0), name="SV 영역", showlegend=True,
        ))
        fig_rate.update_layout(height=350, margin=dict(t=20, b=30),
                                xaxis_title="경과 월", yaxis_title="공정률 (%)",
                                yaxis=dict(range=[0, 105]))
        st.plotly_chart(fig_rate, use_container_width=True)

    with col_cost:
        st.markdown("#### 원가 S-Curve (억원)")
        fig_cost = go.Figure()
        fig_cost.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["pv"],
            mode="lines+markers", name="PV (Planned Value)",
            line=dict(color="#888", width=2, dash="dash"), marker=dict(size=4),
        ))
        fig_cost.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["ev"],
            mode="lines+markers", name="EV (Earned Value)",
            line=dict(color="#4A90D9", width=2.5), marker=dict(size=5),
        ))
        fig_cost.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["ac"],
            mode="lines+markers", name="AC (Actual Cost)",
            line=dict(color="#C00000", width=2), marker=dict(size=4),
        ))
        # BAC 기준선
        fig_cost.add_hline(y=proj_info["bac"], line_dash="dot", line_color="#548235",
                           annotation_text=f"BAC: {proj_info['bac']:,.0f}억")
        # EAC 기준선
        fig_cost.add_hline(y=latest["eac"], line_dash="dot", line_color="#F58220",
                           annotation_text=f"EAC: {latest['eac']:,.0f}억")
        fig_cost.update_layout(height=350, margin=dict(t=20, b=30),
                                xaxis_title="경과 월", yaxis_title="억원")
        st.plotly_chart(fig_cost, use_container_width=True)

    # SV/CV 바 차트
    st.markdown("#### Schedule Variance (SV) & Cost Variance (CV)")
    fig_var = make_subplots(rows=1, cols=2, subplot_titles=["SV (공정 편차)", "CV (원가 편차)"])
    sv_colors = ["#C00000" if v < 0 else "#4A90D9" for v in evm_df["sv"]]
    cv_colors = ["#C00000" if v < 0 else "#548235" for v in evm_df["cv"]]
    fig_var.add_trace(go.Bar(x=evm_df["month"], y=evm_df["sv"], marker_color=sv_colors,
                             name="SV", showlegend=False), row=1, col=1)
    fig_var.add_trace(go.Bar(x=evm_df["month"], y=evm_df["cv"], marker_color=cv_colors,
                             name="CV", showlegend=False), row=1, col=2)
    fig_var.update_layout(height=250, margin=dict(t=30, b=20))
    fig_var.update_xaxes(title_text="경과 월")
    fig_var.update_yaxes(title_text="억원")
    st.plotly_chart(fig_var, use_container_width=True)


# ════════════════════════════════════════════════
# TAB 2: CPI/SPI 추세
# ════════════════════════════════════════════════
with tab2:
    st.subheader("CPI / SPI 추세 분석")

    fig_index = go.Figure()
    fig_index.add_trace(go.Scatter(
        x=evm_df["month"], y=evm_df["spi"],
        mode="lines+markers", name="SPI (Schedule)",
        line=dict(color="#4A90D9", width=2.5), marker=dict(size=6),
    ))
    fig_index.add_trace(go.Scatter(
        x=evm_df["month"], y=evm_df["cpi"],
        mode="lines+markers", name="CPI (Cost)",
        line=dict(color="#548235", width=2.5), marker=dict(size=6),
    ))
    fig_index.add_trace(go.Scatter(
        x=evm_df["month"], y=evm_df["spi_t"],
        mode="lines+markers", name="SPI(t) (Earned Schedule)",
        line=dict(color="#BF8F00", width=2, dash="dash"), marker=dict(size=5),
    ))
    # 기준선
    fig_index.add_hline(y=1.0, line_dash="solid", line_color="#888", line_width=1,
                        annotation_text="Baseline (1.0)")
    fig_index.add_hline(y=0.95, line_dash="dash", line_color="#F58220", line_width=1,
                        annotation_text="주의선 (0.95)")
    fig_index.add_hline(y=0.90, line_dash="dash", line_color="#C00000", line_width=1,
                        annotation_text="경고선 (0.90)")
    # 위험 영역 음영
    fig_index.add_hrect(y0=0, y1=0.90, fillcolor="rgba(192,0,0,0.05)", line_width=0)
    fig_index.add_hrect(y0=0.90, y1=0.95, fillcolor="rgba(245,130,32,0.05)", line_width=0)

    fig_index.update_layout(
        height=400, margin=dict(t=20, b=30),
        xaxis_title="경과 월", yaxis_title="Index",
        yaxis=dict(range=[0.7, 1.2]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_index, use_container_width=True)

    # TCPI 추세
    st.markdown("#### TCPI (To-Complete Performance Index) 추세")
    st.caption("남은 작업에서 달성해야 할 효율 지표. 1.0 초과 시 잔여 예산으로 완료 어려움을 의미")
    fig_tcpi = go.Figure()
    tcpi_colors = ["#C00000" if v > 1.1 else "#F58220" if v > 1.0 else "#548235" for v in evm_df["tcpi"]]
    fig_tcpi.add_trace(go.Bar(
        x=evm_df["month"], y=evm_df["tcpi"],
        marker_color=tcpi_colors, name="TCPI",
    ))
    fig_tcpi.add_hline(y=1.0, line_dash="dash", line_color="#888")
    fig_tcpi.add_hline(y=1.1, line_dash="dash", line_color="#C00000",
                       annotation_text="달성 곤란 (>1.10)")
    fig_tcpi.update_layout(height=280, margin=dict(t=20, b=20),
                            xaxis_title="경과 월", yaxis_title="TCPI")
    st.plotly_chart(fig_tcpi, use_container_width=True)


# ════════════════════════════════════════════════
# TAB 3: Earned Schedule 분석
# ════════════════════════════════════════════════
with tab3:
    st.subheader("Earned Schedule (ES) & Earned Duration (ED) 분석")
    st.caption("전통적 SPI는 프로젝트 후반부에 왜곡됨. ES 기반 SPI(t)가 더 정확한 일정 성과를 반영합니다.")

    col_es, col_comp = st.columns(2)

    with col_es:
        st.markdown("#### ES vs ED (Actual Time) 추세")
        fig_es = go.Figure()
        # 기준선 (ES = ED = 정상)
        fig_es.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["month"],
            mode="lines", name="기준선 (ES=AT)",
            line=dict(color="#888", width=1.5, dash="dash"),
        ))
        fig_es.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["es"],
            mode="lines+markers", name="Earned Schedule (ES)",
            line=dict(color="#4A90D9", width=2.5), marker=dict(size=6),
            fill="tonexty", fillcolor="rgba(192,0,0,0.06)",
        ))
        # Schedule Delay 표시
        last_delay = latest["ed"] - latest["es"]
        fig_es.add_annotation(
            x=latest["ed"], y=latest["es"],
            text=f"지연: {last_delay:.1f}개월",
            showarrow=True, arrowhead=2, font=dict(color="#C00000", size=12),
        )
        fig_es.update_layout(
            height=380, margin=dict(t=20, b=30),
            xaxis_title="Actual Time (개월)", yaxis_title="Earned Schedule (개월)",
        )
        st.plotly_chart(fig_es, use_container_width=True)

    with col_comp:
        st.markdown("#### SPI vs SPI(t) 비교")
        st.caption("SPI(t)는 시간 기반 지표로, 프로젝트 후반부에서 SPI보다 더 정확합니다")
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["spi"],
            mode="lines+markers", name="SPI (전통)",
            line=dict(color="#4A90D9", width=2), marker=dict(size=5),
        ))
        fig_comp.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["spi_t"],
            mode="lines+markers", name="SPI(t) (Earned Schedule)",
            line=dict(color="#BF8F00", width=2.5), marker=dict(size=6),
        ))
        fig_comp.add_hline(y=1.0, line_dash="dash", line_color="#888")
        fig_comp.add_hline(y=0.95, line_dash="dot", line_color="#F58220")
        fig_comp.update_layout(
            height=380, margin=dict(t=20, b=30),
            xaxis_title="경과 월", yaxis_title="Index",
            yaxis=dict(range=[0.7, 1.15]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    # ES 요약 테이블
    st.markdown("#### Earned Schedule 핵심 지표")
    es_summary = {
        "지표": ["Earned Schedule (ES)", "Actual Time (AT)", "Schedule Delay",
                 "SPI(t)", "IEAC(t) 예측 공기", "계획 공기 (PD)", "예상 지연"],
        "값": [f"{latest['es']:.1f}개월", f"{latest['ed']:.0f}개월",
               f"{latest['ed'] - latest['es']:.1f}개월",
               f"{latest['spi_t']:.3f}",
               f"{latest['ieac_t']:.1f}개월", f"{proj_info['duration']}개월",
               f"{latest['ieac_t'] - proj_info['duration']:+.1f}개월"],
        "판정": ["", "", "지연" if latest["ed"] > latest["es"] else "정상",
                 "정상" if latest["spi_t"] >= 0.95 else "주의" if latest["spi_t"] >= 0.9 else "경고",
                 "", "", "초과" if latest["ieac_t"] > proj_info["duration"] else "이내"],
    }
    st.dataframe(pd.DataFrame(es_summary), use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════
# TAB 4: EAC 예측
# ════════════════════════════════════════════════
with tab4:
    st.subheader("EAC (Estimate At Completion) 예측 분석")

    col_eac, col_detail = st.columns([2, 1])

    with col_eac:
        st.markdown("#### EAC 추세 (원가 예측)")
        fig_eac = go.Figure()
        fig_eac.add_trace(go.Scatter(
            x=evm_df["month"], y=evm_df["eac"],
            mode="lines+markers", name="EAC (BAC/CPI)",
            line=dict(color="#C00000", width=2.5), marker=dict(size=5),
        ))
        fig_eac.add_hline(y=proj_info["bac"], line_dash="dash", line_color="#548235",
                          annotation_text=f"BAC: {proj_info['bac']:,.0f}억")
        fig_eac.add_hline(y=proj_info["contract"], line_dash="dot", line_color="#BF8F00",
                          annotation_text=f"계약액: {proj_info['contract']:,.0f}억")
        fig_eac.update_layout(height=350, margin=dict(t=20, b=30),
                               xaxis_title="경과 월", yaxis_title="억원")
        st.plotly_chart(fig_eac, use_container_width=True)

    with col_detail:
        st.markdown("#### 원가 예측 상세")
        cost_summary = {
            "항목": ["BAC (예산)", "AC (실투입)", "EV (실적가치)", "EAC (예측 총원가)",
                     "ETC (잔여 소요)", "VAC (원가 편차)", "TCPI (필요 효율)"],
            "금액": [f"{proj_info['bac']:,.0f}억", f"{latest['ac']:,.0f}억",
                     f"{latest['ev']:,.0f}억", f"{latest['eac']:,.0f}억",
                     f"{latest['etc']:,.0f}억", f"{latest['vac']:+,.0f}억",
                     f"{latest['tcpi']:.3f}"],
            "판정": ["기준", "투입중", "달성",
                     "초과" if latest["eac"] > proj_info["bac"] else "이내",
                     "", "손실 예상" if latest["vac"] < 0 else "여유",
                     "달성가능" if latest["tcpi"] <= 1.1 else "어려움"],
        }
        st.dataframe(pd.DataFrame(cost_summary), use_container_width=True, hide_index=True)

    # 일정 예측
    st.markdown("#### 일정 예측 (IEAC(t))")
    fig_ieac = go.Figure()
    fig_ieac.add_trace(go.Scatter(
        x=evm_df["month"], y=evm_df["ieac_t"],
        mode="lines+markers", name="IEAC(t) = PD / SPI(t)",
        line=dict(color="#BF8F00", width=2.5), marker=dict(size=5),
    ))
    fig_ieac.add_hline(y=proj_info["duration"], line_dash="dash", line_color="#548235",
                       annotation_text=f"계획 공기: {proj_info['duration']}개월")
    fig_ieac.update_layout(height=300, margin=dict(t=20, b=30),
                            xaxis_title="경과 월", yaxis_title="예측 공기 (개월)")
    st.plotly_chart(fig_ieac, use_container_width=True)

    # 전체 EVM 데이터 테이블
    with st.expander("EVM 월별 상세 데이터", expanded=False):
        display_evm = evm_df.copy()
        display_evm.columns = [
            "월", "일자", "PV", "EV", "AC", "PV율(%)", "EV율(%)",
            "SV", "CV", "SPI", "CPI", "ES", "ED", "SPI(t)",
            "EAC", "ETC", "VAC", "IEAC(t)", "TCPI"
        ]
        st.dataframe(display_evm, use_container_width=True, hide_index=True)
