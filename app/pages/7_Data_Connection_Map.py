"""Data Connection Map - 데이터 연결 현황 및 소스 시스템 매핑"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import math
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db.models import SessionLocal, engine
from config.settings import BUSINESS_UNITS, DECISION_AREAS, MODULES
from sqlalchemy import inspect, text

st.set_page_config(page_title="Data Connection Map", page_icon="<C2><AC>", layout="wide")
st.title("Data Connection Map")
st.caption("소스 시스템 -> DSS 테이블 -> 모듈 연결 현황 및 데이터 리니지")

# ══════════════════════════════════════════════════
# 소스 시스템 정의 (SK에코플랜트 실제 시스템 구조 기반)
# ══════════════════════════════════════════════════
SOURCE_SYSTEMS = {
    "SAP_ERP": {
        "name": "SAP ERP (FI/CO)",
        "type": "ERP",
        "desc": "재무회계/관리회계 통합 시스템",
        "owner": "재무팀",
        "color": "#0070C0",
        "tables": {
            "BKPF/BSEG": {"desc": "회계전표 (매출/매출원가/판관비)", "target_table": "financials", "target_cols": ["revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit"], "frequency": "일별"},
            "ANLAV": {"desc": "고정자산 (감가상각비/CAPEX)", "target_table": "financials", "target_cols": ["capex"], "frequency": "월별"},
            "FAGLFLEXA": {"desc": "총계정원장 (영업현금흐름)", "target_table": "financials", "target_cols": ["operating_cf"], "frequency": "월별"},
            "COSP/COSS": {"desc": "원가센터 실적 (OPEX 상세)", "target_table": "kpi_values", "target_cols": ["P-014 판관비율"], "frequency": "월별"},
        },
    },
    "SAP_PS": {
        "name": "SAP PS (Project System)",
        "type": "PMS",
        "desc": "프로젝트 관리 시스템 (EPC)",
        "owner": "PM실",
        "color": "#2F5496",
        "tables": {
            "PROJ/PRPS": {"desc": "프로젝트/WBS 마스터", "target_table": "projects", "target_cols": ["id", "name", "project_type", "client", "contract_value", "bac"], "frequency": "수시"},
            "COOIS": {"desc": "프로젝트 원가 실적 (EV/AC/PV)", "target_table": "evm_monthly", "target_cols": ["pv", "ev", "ac", "sv", "cv", "spi", "cpi"], "frequency": "주별"},
            "AFRU": {"desc": "공정 확인 (진척률/Earned Schedule)", "target_table": "evm_monthly", "target_cols": ["pv_rate", "ev_rate", "es", "es_spi_t", "eac", "tcpi"], "frequency": "주별"},
            "J_AUFNR": {"desc": "수주/계약 (수주잔고/VO)", "target_table": "financials", "target_cols": ["backlog"], "frequency": "월별"},
        },
    },
    "PLAN_BUDGET": {
        "name": "경영계획 시스템",
        "type": "Planning",
        "desc": "연간/월별 경영계획 및 예산",
        "owner": "경영기획팀",
        "color": "#548235",
        "tables": {
            "PLAN_REV": {"desc": "매출 계획 (사업부별/월별)", "target_table": "financials", "target_cols": ["plan_revenue"], "frequency": "연 1회 (월별 분할)"},
            "PLAN_EBITDA": {"desc": "EBITDA 계획", "target_table": "financials", "target_cols": ["plan_ebitda"], "frequency": "연 1회 (월별 분할)"},
            "KPI_TARGET": {"desc": "KPI 목표값", "target_table": "kpi_values", "target_cols": ["plan"], "frequency": "연 1회"},
            "CAPEX_PLAN": {"desc": "투자계획 (CAPEX/NPV/IRR)", "target_table": "kpi_values", "target_cols": ["I-001 CAPEX집행률", "I-002 NPV", "I-003 IRR"], "frequency": "분기별"},
        },
    },
    "MES_IOT": {
        "name": "MES / IoT 플랫폼",
        "type": "OT/IoT",
        "desc": "설비운영 데이터 (Green Energy, Recycling)",
        "owner": "설비운영팀",
        "color": "#BF8F00",
        "tables": {
            "EQUIP_STATUS": {"desc": "설비 가동/비가동 상태", "target_table": "kpi_values", "target_cols": ["O-011 설비가동률", "O-012 다운타임"], "frequency": "실시간"},
            "THROUGHPUT": {"desc": "처리량/수율 데이터", "target_table": "kpi_values", "target_cols": ["O-013 처리량/수율", "O-014 Diversion Rate"], "frequency": "일별"},
            "ENERGY_METER": {"desc": "에너지 생산/소비량", "target_table": "kpi_values", "target_cols": ["O-015 WtE효율", "I-007 LCOE"], "frequency": "시간별"},
            "SENSOR_DATA": {"desc": "환경 센서 (배출량/온도)", "target_table": "kpi_values", "target_cols": ["R-005 탄소배출량"], "frequency": "실시간"},
        },
    },
    "HR_SAFETY": {
        "name": "HR / 안전관리 시스템",
        "type": "HR/EHS",
        "desc": "인사관리 및 안전보건 시스템",
        "owner": "HR팀 / 안전환경팀",
        "color": "#C00000",
        "tables": {
            "INCIDENT_LOG": {"desc": "안전사고/아차사고 이력", "target_table": "kpi_values", "target_cols": ["R-006 LTIR", "R-007 Near-miss"], "frequency": "수시"},
            "COMPLIANCE": {"desc": "규제 점검/인허가 현황", "target_table": "kpi_values", "target_cols": ["R-008 규제준수율"], "frequency": "월별"},
            "ESG_DATA": {"desc": "ESG 평가 데이터", "target_table": "kpi_values", "target_cols": ["R-004 ESG Score"], "frequency": "분기별"},
        },
    },
    "TREASURY": {
        "name": "자금관리 / 리스크 시스템",
        "type": "Treasury",
        "desc": "환율, 금리, 자금 관리",
        "owner": "재무팀",
        "color": "#7030A0",
        "tables": {
            "FX_POSITION": {"desc": "외화 포지션/환율 노출", "target_table": "kpi_values", "target_cols": ["R-002 환율리스크"], "frequency": "일별"},
            "COMMODITY": {"desc": "원자재(철강/구리) 시세", "target_table": "kpi_values", "target_cols": ["R-003 원자재가격리스크"], "frequency": "일별"},
            "DEBT_POSITION": {"desc": "차입금/부채 현황", "target_table": "kpi_values", "target_cols": ["R-009 부채비율", "R-010 차입금의존도"], "frequency": "월별"},
            "AR_AP": {"desc": "매출채권/매입채무", "target_table": "kpi_values", "target_cols": ["O-021 CCC", "O-022 매출채권회전일", "O-024 미청구공사"], "frequency": "월별"},
        },
    },
    "EXTERNAL": {
        "name": "외부 데이터",
        "type": "External API",
        "desc": "시장 데이터, REC 가격, 환율 등",
        "owner": "데이터팀",
        "color": "#999999",
        "tables": {
            "REC_PRICE": {"desc": "REC 거래가격 (전력거래소)", "target_table": "kpi_values", "target_cols": ["R-011 REC/탄소크레딧가격"], "frequency": "일별"},
            "MARKET_INDEX": {"desc": "시장지표 (환율/금리/원자재)", "target_table": "risk_items", "target_cols": ["probability", "impact"], "frequency": "일별"},
            "PEER_BENCHMARK": {"desc": "경쟁사/업계 벤치마크", "target_table": "kpi_definitions", "target_cols": ["description"], "frequency": "분기별"},
        },
    },
}

# DSS 테이블 -> 모듈 매핑
TABLE_MODULE_MAP = {
    "business_units": ["M1", "M2", "M3", "M4", "M5", "M6"],
    "financials": ["M1", "M2", "M4"],
    "kpi_definitions": ["M1", "M2", "M3"],
    "kpi_values": ["M1", "M2", "M3", "M5"],
    "biz_questions": ["M3"],
    "risk_items": ["M5", "M4"],
    "scenario_runs": ["M4"],
    "projects": ["M6"],
    "evm_monthly": ["M6"],
}

# ══════════════════════════════════════════════════
# DB 실시간 상태 조회
# ══════════════════════════════════════════════════
@st.cache_data(ttl=60)
def get_db_stats():
    session = SessionLocal()
    insp = inspect(engine)
    try:
        stats = {}
        for table_name in insp.get_table_names():
            row_count = session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            cols = insp.get_columns(table_name)
            fks = insp.get_foreign_keys(table_name)
            stats[table_name] = {
                "rows": row_count,
                "columns": len(cols),
                "col_names": [c["name"] for c in cols],
                "col_types": [str(c["type"]) for c in cols],
                "fk_count": len(fks),
                "fks": [{"from": fk["constrained_columns"], "to_table": fk["referred_table"], "to_col": fk["referred_columns"]} for fk in fks],
            }
        return stats
    finally:
        session.close()

db_stats = get_db_stats()


# ══════════════════════════════════════════════════
# TAB 구조
# ══════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "Data Flow Diagram",
    "Source System Mapping",
    "DSS Table Detail",
    "Connection Status",
])


# ══════════════════════════════════════════════════
# TAB 1: ECharts 기반 데이터 플로우 다이어그램
# ══════════════════════════════════════════════════
with tab1:
    st.subheader("데이터 연결 플로우 (소스 시스템 → DSS 테이블 → 모듈)")

    # ── 노드/링크 데이터 구성 (Palantir Foundry 스타일) ──
    # 3-tier 레이아웃: 소스(x=100) → DSS테이블(x=450) → 모듈(x=800)
    flow_nodes = []
    flow_links = []

    # 노드 y좌표: 헤더 영역(0~60) 확보 후 70부터 배치
    NODE_Y_START = 70
    NODE_Y_RANGE = 560

    # 소스 시스템 노드 (좌측 열)
    src_list = list(SOURCE_SYSTEMS.items())
    src_y_step = NODE_Y_RANGE // max(len(src_list), 1)
    for i, (sys_id, sys_info) in enumerate(src_list):
        table_count = len(sys_info["tables"])
        flow_nodes.append({
            "id": f"src_{sys_id}",
            "name": sys_info["name"],
            "x": 80,
            "y": NODE_Y_START + i * src_y_step,
            "category": 0,
            "table_count": table_count,
            "owner": sys_info["owner"],
            "sys_type": sys_info["type"],
            "color": sys_info["color"],
        })

    # DSS 테이블 노드 (중앙 열)
    tbl_list = list(db_stats.keys())
    tbl_y_step = NODE_Y_RANGE // max(len(tbl_list), 1)
    for i, table_name in enumerate(tbl_list):
        stats = db_stats[table_name]
        flow_nodes.append({
            "id": f"tbl_{table_name}",
            "name": table_name,
            "x": 420,
            "y": NODE_Y_START + i * tbl_y_step,
            "category": 1,
            "rows": stats["rows"],
            "columns": stats["columns"],
            "fk_count": stats["fk_count"],
        })

    # 모듈 노드 (우측 열)
    module_colors_map = {"M1": "#2F5496", "M2": "#548235", "M3": "#BF8F00", "M4": "#7030A0", "M5": "#C00000", "M6": "#0097A7"}
    mod_list = list(MODULES.items())
    mod_y_step = NODE_Y_RANGE // max(len(mod_list), 1)
    for i, (mod_key, mod_name) in enumerate(mod_list):
        flow_nodes.append({
            "id": f"mod_{mod_key}",
            "name": f"{mod_key} {mod_name}",
            "x": 760,
            "y": NODE_Y_START + i * mod_y_step,
            "category": 2,
            "color": module_colors_map.get(mod_key, "#666"),
        })

    # 소스 → 테이블 링크 (중복 제거)
    seen_links = set()
    for sys_id, sys_info in SOURCE_SYSTEMS.items():
        for src_table, mapping in sys_info["tables"].items():
            key = (f"src_{sys_id}", f"tbl_{mapping['target_table']}")
            if key not in seen_links:
                seen_links.add(key)
                col_count = len(mapping["target_cols"])
                flow_links.append({
                    "source": key[0],
                    "target": key[1],
                    "col_count": col_count,
                    "color": sys_info["color"],
                    "frequency": mapping["frequency"],
                    "label": src_table,
                })

    # 테이블 → 모듈 링크
    for table_name, module_list in TABLE_MODULE_MAP.items():
        if table_name in db_stats:
            for mod in module_list:
                key = (f"tbl_{table_name}", f"mod_{mod}")
                if key not in seen_links:
                    seen_links.add(key)
                    flow_links.append({
                        "source": key[0],
                        "target": key[1],
                        "col_count": 1,
                        "color": module_colors_map.get(mod, "#999"),
                        "frequency": "",
                        "label": "",
                    })

    flow_nodes_json = json.dumps(flow_nodes, ensure_ascii=False)
    flow_links_json = json.dumps(flow_links, ensure_ascii=False)

    html_graph = f"""
    <div id="data-flow" style="width:100%;height:780px;background:#0e1117;"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <script>
    (function() {{
        var dom = document.getElementById('data-flow');
        var chart = echarts.init(dom, 'dark');

        var rawNodes = {flow_nodes_json};
        var rawLinks = {flow_links_json};

        // ── Custom SVG paths ──
        var dbIcon = 'path://M4,2 C4,0.9 8,0 13,0 C18,0 22,0.9 22,2 L22,18 C22,19.1 18,20 13,20 C8,20 4,19.1 4,18 Z M4,2 C4,3.1 8,4 13,4 C18,4 22,3.1 22,2';
        var moduleIcon = 'path://M2,0 L22,0 C23.1,0 24,0.9 24,2 L24,16 C24,17.1 23.1,18 22,18 L2,18 C0.9,18 0,17.1 0,16 L0,2 C0,0.9 0.9,0 2,0 Z M0,5 L24,5';

        // ── Build ECharts nodes ──
        var nodes = rawNodes.map(function(n) {{
            var node = {{
                id: n.id,
                name: n.name,
                x: n.x,
                y: n.y,
                fixed: true,
                category: n.category,
            }};

            if (n.category === 0) {{
                // Source system: rounded-rect with DB icon look
                node.symbol = 'roundRect';
                node.symbolSize = [160, 52];
                node.itemStyle = {{
                    color: n.color,
                    borderColor: '#ffffff22',
                    borderWidth: 1,
                    shadowColor: n.color + '55',
                    shadowBlur: 12,
                    borderRadius: 6,
                }};
                node.label = {{
                    show: true,
                    color: '#fff',
                    fontSize: 11,
                    fontWeight: 'bold',
                    formatter: function(p) {{
                        var d = rawNodes.find(function(x){{ return x.id === p.data.id; }});
                        return '  ' + p.name + '\\n  ' + (d ? d.sys_type : '');
                    }},
                    lineHeight: 18,
                }};
            }} else if (n.category === 1) {{
                // DSS Table: database cylinder shape
                node.symbol = dbIcon;
                node.symbolSize = [130, 48];
                node.itemStyle = {{
                    color: '#1a3a2a',
                    borderColor: '#548235',
                    borderWidth: 2,
                    shadowColor: '#54823566',
                    shadowBlur: 10,
                    borderRadius: 4,
                }};
                node.label = {{
                    show: true,
                    color: '#8fbc6a',
                    fontSize: 11,
                    fontWeight: 'bold',
                    formatter: function(p) {{
                        var d = rawNodes.find(function(x){{ return x.id === p.data.id; }});
                        return p.name + '\\n' + (d ? d.rows + ' rows · ' + d.columns + ' cols' : '');
                    }},
                    lineHeight: 16,
                }};
            }} else {{
                // Module: rounded rect with accent
                node.symbol = moduleIcon;
                node.symbolSize = [150, 46];
                node.itemStyle = {{
                    color: n.color + '33',
                    borderColor: n.color,
                    borderWidth: 2,
                    shadowColor: n.color + '44',
                    shadowBlur: 8,
                    borderRadius: 8,
                }};
                node.label = {{
                    show: true,
                    color: '#ddd',
                    fontSize: 11,
                    fontWeight: 'bold',
                }};
            }}
            return node;
        }});

        // ── Build ECharts links ──
        var links = rawLinks.map(function(l) {{
            var w = Math.min(5, 1 + l.col_count * 0.6);
            return {{
                source: l.source,
                target: l.target,
                lineStyle: {{
                    color: l.color,
                    width: w,
                    opacity: 0.55,
                    type: l.frequency === '실시간' ? 'solid' : (l.frequency === '' ? 'dashed' : 'solid'),
                    curveness: 0.15,
                }},
                emphasis: {{
                    lineStyle: {{ width: w + 3, opacity: 1 }},
                }},
            }};
        }});

        var option = {{
            backgroundColor: 'transparent',
            tooltip: {{
                trigger: 'item',
                backgroundColor: '#1a1a2e',
                borderColor: '#333',
                textStyle: {{ color: '#ddd', fontSize: 12 }},
                formatter: function(p) {{
                    if (p.dataType === 'node') {{
                        var d = rawNodes.find(function(x){{ return x.id === p.data.id; }});
                        if (!d) return p.name;
                        if (d.category === 0) return '<b>' + d.name + '</b><br/>유형: ' + d.sys_type + '<br/>담당: ' + d.owner + '<br/>연결 테이블: ' + d.table_count + '개';
                        if (d.category === 1) return '<b>📦 ' + d.name + '</b><br/>행: ' + d.rows.toLocaleString() + '<br/>컬럼: ' + d.columns + '개<br/>FK: ' + d.fk_count + '개';
                        return '<b>' + d.name + '</b>';
                    }}
                    if (p.dataType === 'edge') {{
                        var l = rawLinks.find(function(x){{ return x.source === p.data.source && x.target === p.data.target; }});
                        if (!l) return '';
                        var parts = ['<b>' + l.source.replace('src_','').replace('tbl_','') + ' → ' + l.target.replace('tbl_','').replace('mod_','') + '</b>'];
                        if (l.label) parts.push('테이블: ' + l.label);
                        if (l.frequency) parts.push('주기: ' + l.frequency);
                        parts.push('매핑 컬럼: ' + l.col_count + '개');
                        return parts.join('<br/>');
                    }}
                }},
            }},
            legend: {{
                data: ['소스 시스템', 'DSS 테이블', '시스템 모듈'],
                top: 8,
                right: 20,
                textStyle: {{ color: '#aaa', fontSize: 11 }},
                itemWidth: 16,
                itemHeight: 12,
            }},
            graphic: [
                {{ type: 'text', left: '12%', top: 38, style: {{ text: 'SOURCE SYSTEMS', fill: '#8899aa', fontSize: 13, fontWeight: 'bold', letterSpacing: 2, textAlign: 'center' }} }},
                {{ type: 'text', left: '48%', top: 38, style: {{ text: 'DSS DATABASE', fill: '#8899aa', fontSize: 13, fontWeight: 'bold', letterSpacing: 2, textAlign: 'center' }} }},
                {{ type: 'text', left: '85%', top: 38, style: {{ text: 'MODULES', fill: '#8899aa', fontSize: 13, fontWeight: 'bold', letterSpacing: 2, textAlign: 'center' }} }},
                {{ type: 'rect', left: 0, top: 58, shape: {{ width: 2000, height: 1 }}, style: {{ fill: '#333' }} }},
            ],
            series: [{{
                type: 'graph',
                layout: 'none',
                data: nodes,
                links: links,
                categories: [
                    {{ name: '소스 시스템' }},
                    {{ name: 'DSS 테이블' }},
                    {{ name: '시스템 모듈' }},
                ],
                roam: true,
                edgeSymbol: ['none', 'arrow'],
                edgeSymbolSize: [0, 8],
                emphasis: {{
                    focus: 'adjacency',
                    itemStyle: {{ shadowBlur: 20 }},
                }},
            }}],
        }};

        chart.setOption(option);
        window.addEventListener('resize', function() {{ chart.resize(); }});
    }})();
    </script>
    """
    components.html(html_graph, height=800, scrolling=False)

    st.markdown("""
    **조작 방법:** 마우스 드래그로 캔버스 이동 / 스크롤로 확대축소 / 노드·링크 hover 시 상세 정보 표시
    """)

    # 범례
    leg_cols = st.columns(3)
    leg_cols[0].markdown("🔷 **소스 시스템** (좌측) - ERP, PMS, IoT, 외부 데이터 등")
    leg_cols[1].markdown("🟩 **DSS 테이블** (중앙) - 디지털 트윈 DB 7개 테이블 (실린더 아이콘)")
    leg_cols[2].markdown("🔶 **시스템 모듈** (우측) - M1~M6 6대 모듈")


# ══════════════════════════════════════════════════
# TAB 2: 소스 시스템별 상세 매핑
# ══════════════════════════════════════════════════
with tab2:
    st.subheader("소스 시스템 -> DSS 테이블 매핑 상세")

    for sys_id, sys_info in SOURCE_SYSTEMS.items():
        with st.expander(
            f"**{sys_info['name']}** ({sys_info['type']}) - {sys_info['desc']}  |  담당: {sys_info['owner']}",
            expanded=False
        ):
            mapping_rows = []
            for src_table, mapping in sys_info["tables"].items():
                target_rows = db_stats.get(mapping["target_table"], {}).get("rows", 0)
                mapping_rows.append({
                    "소스 테이블": src_table,
                    "설명": mapping["desc"],
                    "DSS 테이블": mapping["target_table"],
                    "매핑 컬럼": ", ".join(mapping["target_cols"]),
                    "수집 주기": mapping["frequency"],
                    "현재 건수": target_rows,
                    "상태": "Virtual (Seed)" if target_rows > 0 else "미연결",
                })

            df_mapping = pd.DataFrame(mapping_rows)
            st.dataframe(df_mapping, use_container_width=True, hide_index=True)

    # 전체 매핑 요약
    st.divider()
    st.subheader("전체 매핑 요약 통계")
    summary_data = []
    for sys_id, sys_info in SOURCE_SYSTEMS.items():
        total_cols = sum(len(m["target_cols"]) for m in sys_info["tables"].values())
        target_tables = set(m["target_table"] for m in sys_info["tables"].values())
        summary_data.append({
            "소스 시스템": sys_info["name"],
            "유형": sys_info["type"],
            "소스 테이블 수": len(sys_info["tables"]),
            "매핑 항목 수": total_cols,
            "DSS 테이블": ", ".join(sorted(target_tables)),
            "담당": sys_info["owner"],
        })
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════
# TAB 3: DSS 테이블 상세 (ERD 스타일)
# ══════════════════════════════════════════════════
with tab3:
    st.subheader("DSS 데이터베이스 테이블 상세")

    # 테이블 선택
    selected_table = st.selectbox("테이블 선택", list(db_stats.keys()))

    if selected_table:
        stats = db_stats[selected_table]

        # 메트릭 카드
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("행 수", f"{stats['rows']:,}")
        mc2.metric("컬럼 수", stats["columns"])
        mc3.metric("FK 관계", stats["fk_count"])
        mc4.metric("연결 모듈", ", ".join(TABLE_MODULE_MAP.get(selected_table, [])))

        # 컬럼 상세
        col_data = []
        for name, typ in zip(stats["col_names"], stats["col_types"]):
            # 소스 시스템 역추적
            source_sys = ""
            for sys_id, sys_info in SOURCE_SYSTEMS.items():
                for src_t, mapping in sys_info["tables"].items():
                    if mapping["target_table"] == selected_table:
                        if any(name in col for col in mapping["target_cols"]):
                            source_sys = f"{sys_info['name']} ({src_t})"
                            break

            col_data.append({
                "컬럼명": name,
                "데이터 타입": typ,
                "소스 시스템": source_sys or "-",
            })

        st.markdown("#### 컬럼 구조")
        st.dataframe(pd.DataFrame(col_data), use_container_width=True, hide_index=True)

        # FK 관계
        if stats["fks"]:
            st.markdown("#### FK 관계 (참조)")
            for fk in stats["fks"]:
                st.markdown(f"- `{selected_table}.{fk['from']}` -> `{fk['to_table']}.{fk['to_col']}`")

        # 샘플 데이터
        st.markdown("#### 샘플 데이터 (최근 5건)")
        session = SessionLocal()
        try:
            sample = session.execute(text(f"SELECT * FROM {selected_table} LIMIT 5")).fetchall()
            if sample:
                sample_df = pd.DataFrame(sample, columns=stats["col_names"])
                st.dataframe(sample_df, use_container_width=True, hide_index=True)
            else:
                st.info("데이터 없음")
        finally:
            session.close()

    # ERD 시각화
    st.divider()
    st.subheader("테이블 관계도 (ERD)")

    # ── ERD 노드/링크 데이터 (Palantir Foundry 스타일) ──
    erd_raw_nodes = []
    erd_raw_links = []

    # 테이블별 색상 - 연결 모듈 기반
    erd_table_colors = {
        "business_units": "#2F5496",
        "financials": "#0070C0",
        "kpi_definitions": "#548235",
        "kpi_values": "#BF8F00",
        "biz_questions": "#7030A0",
        "risk_items": "#C00000",
        "scenario_runs": "#7030A0",
        "projects": "#0097A7",
        "evm_monthly": "#0097A7",
    }

    # 원형 배치 좌표 계산
    tbl_names = list(db_stats.keys())
    n_tables = len(tbl_names)
    cx, cy, radius = 400, 300, 220
    for i, table_name in enumerate(tbl_names):
        angle = (2 * math.pi * i / n_tables) - math.pi / 2
        stats = db_stats[table_name]
        tbl_color = erd_table_colors.get(table_name, "#548235")
        connected_modules = TABLE_MODULE_MAP.get(table_name, [])

        # 소스 시스템 역추적
        source_systems = []
        for sys_id, sys_info in SOURCE_SYSTEMS.items():
            for src_t, mapping in sys_info["tables"].items():
                if mapping["target_table"] == table_name:
                    source_systems.append(sys_info["name"])
                    break

        erd_raw_nodes.append({
            "id": table_name,
            "name": table_name,
            "x": cx + radius * math.cos(angle),
            "y": cy + radius * math.sin(angle),
            "rows": stats["rows"],
            "columns": stats["columns"],
            "col_names": stats["col_names"][:8],
            "fk_count": stats["fk_count"],
            "color": tbl_color,
            "modules": connected_modules,
            "sources": list(set(source_systems)),
        })

        for fk in stats["fks"]:
            fk_from_col = fk["from"][0] if fk["from"] else ""
            fk_to_col = fk["to_col"][0] if fk["to_col"] else ""
            erd_raw_links.append({
                "source": table_name,
                "target": fk["to_table"],
                "from_col": fk_from_col,
                "to_col": fk_to_col,
                "color": tbl_color,
            })

    erd_nodes_json = json.dumps(erd_raw_nodes, ensure_ascii=False)
    erd_links_json = json.dumps(erd_raw_links, ensure_ascii=False)

    # 선택된 테이블 강조
    hl_table = selected_table if selected_table else ""

    html_erd = f"""
    <div id="erd" style="width:100%;height:560px;background:#0e1117;"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <script>
    (function() {{
        var dom = document.getElementById('erd');
        var chart2 = echarts.init(dom, 'dark');

        var rawNodes = {erd_nodes_json};
        var rawLinks = {erd_links_json};
        var hlTable = '{hl_table}';

        var dbIcon = 'path://M4,2 C4,0.9 8,0 13,0 C18,0 22,0.9 22,2 L22,18 C22,19.1 18,20 13,20 C8,20 4,19.1 4,18 Z M4,2 C4,3.1 8,4 13,4 C18,4 22,3.1 22,2';

        var nodes = rawNodes.map(function(n) {{
            var isHighlighted = (hlTable === n.id);
            return {{
                id: n.id,
                name: n.name,
                x: n.x,
                y: n.y,
                fixed: true,
                symbol: dbIcon,
                symbolSize: [150, 60],
                itemStyle: {{
                    color: isHighlighted ? (n.color + 'aa') : '#151c25',
                    borderColor: n.color,
                    borderWidth: isHighlighted ? 3 : 2,
                    shadowColor: n.color + (isHighlighted ? '88' : '44'),
                    shadowBlur: isHighlighted ? 20 : 8,
                }},
                label: {{
                    show: true,
                    color: isHighlighted ? '#fff' : '#ccc',
                    fontSize: 11,
                    fontWeight: 'bold',
                    lineHeight: 16,
                    formatter: function(p) {{
                        var d = rawNodes.find(function(x) {{ return x.id === p.data.id; }});
                        if (!d) return p.name;
                        return p.name + '\\n' + d.rows + ' rows | ' + d.columns + ' cols | FK ' + d.fk_count;
                    }},
                }},
            }};
        }});

        var links = rawLinks.map(function(l) {{
            var isHl = (hlTable === l.source || hlTable === l.target);
            return {{
                source: l.source,
                target: l.target,
                lineStyle: {{
                    color: l.color,
                    width: isHl ? 3.5 : 2,
                    opacity: isHl ? 0.9 : 0.45,
                    type: 'solid',
                    curveness: 0.18,
                }},
                label: {{
                    show: true,
                    formatter: l.from_col + ' → ' + l.to_col,
                    fontSize: 9,
                    color: '#888',
                    backgroundColor: '#1a1a2ecc',
                    padding: [2, 6],
                    borderRadius: 3,
                }},
                emphasis: {{
                    lineStyle: {{ width: 5, opacity: 1 }},
                    label: {{ fontSize: 11, color: '#fff' }},
                }},
            }};
        }});

        var option = {{
            backgroundColor: 'transparent',
            title: {{
                text: 'DATABASE SCHEMA',
                left: 16,
                top: 10,
                textStyle: {{ color: '#555', fontSize: 12, fontWeight: 'bold' }},
            }},
            tooltip: {{
                trigger: 'item',
                backgroundColor: '#1a1a2e',
                borderColor: '#333',
                textStyle: {{ color: '#ddd', fontSize: 12 }},
                formatter: function(p) {{
                    if (p.dataType === 'node') {{
                        var d = rawNodes.find(function(x) {{ return x.id === p.data.id; }});
                        if (!d) return p.name;
                        var html = '<b style="color:' + d.color + '">📦 ' + d.name + '</b><br/>';
                        html += '행: ' + d.rows.toLocaleString() + ' | 컬럼: ' + d.columns + ' | FK: ' + d.fk_count + '<br/>';
                        html += '<span style="color:#8fbc6a">컬럼:</span> ' + d.col_names.join(', ');
                        if (d.columns > 8) html += ', ...';
                        html += '<br/>';
                        if (d.modules.length > 0) html += '<span style="color:#BF8F00">모듈:</span> ' + d.modules.join(', ') + '<br/>';
                        if (d.sources.length > 0) html += '<span style="color:#0070C0">소스:</span> ' + d.sources.join(', ');
                        return html;
                    }}
                    if (p.dataType === 'edge') {{
                        var l = rawLinks.find(function(x) {{ return x.source === p.data.source && x.target === p.data.target; }});
                        if (!l) return '';
                        return '<b>FK 관계</b><br/>' + l.source + '.' + l.from_col + ' → ' + l.target + '.' + l.to_col;
                    }}
                }},
            }},
            series: [{{
                type: 'graph',
                layout: 'none',
                data: nodes,
                links: links,
                roam: true,
                edgeSymbol: ['circle', 'arrow'],
                edgeSymbolSize: [4, 10],
                emphasis: {{
                    focus: 'adjacency',
                    itemStyle: {{ shadowBlur: 25 }},
                }},
            }}],
        }};

        chart2.setOption(option);
        window.addEventListener('resize', function() {{ chart2.resize(); }});
    }})();
    </script>
    """
    components.html(html_erd, height=580, scrolling=False)

    st.markdown("""
    **조작:** 스크롤 확대축소 / 노드 hover 시 컬럼·소스·모듈 정보 표시 / 링크 hover 시 FK 관계 표시
    """)


# ══════════════════════════════════════════════════
# TAB 4: 연결 상태 대시보드
# ══════════════════════════════════════════════════
with tab4:
    st.subheader("데이터 연결 상태 현황")

    # 현재 상태: 디지털 트윈 (가상 데이터)
    st.markdown("""
    > **현재 모드: Digital Twin (Virtual Seed Data)**
    > 실제 소스 시스템 연결 전, 가상 데이터로 시스템을 검증하는 단계입니다.
    > 아래에서 각 소스 시스템의 연결 상태와 구축 시 필요한 연결 작업을 확인할 수 있습니다.
    """)

    # 연결 상태 매트릭스
    status_data = []
    for sys_id, sys_info in SOURCE_SYSTEMS.items():
        for src_table, mapping in sys_info["tables"].items():
            target_rows = db_stats.get(mapping["target_table"], {}).get("rows", 0)
            if target_rows > 0:
                status = "Virtual"
                status_icon = "🟡"
            else:
                status = "미연결"
                status_icon = "🔴"

            status_data.append({
                "상태": status_icon,
                "소스 시스템": sys_info["name"],
                "소스 테이블": src_table,
                "설명": mapping["desc"],
                "DSS 테이블": mapping["target_table"],
                "매핑 컬럼": ", ".join(mapping["target_cols"][:3]) + ("..." if len(mapping["target_cols"]) > 3 else ""),
                "수집 주기": mapping["frequency"],
                "연결 상태": status,
                "비고": "Seed 데이터 운영중" if target_rows > 0 else "구축 시 연결 필요",
            })

    df_status = pd.DataFrame(status_data)

    # 요약 통계
    total = len(df_status)
    virtual = len(df_status[df_status["연결 상태"] == "Virtual"])
    disconnected = len(df_status[df_status["연결 상태"] == "미연결"])

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("전체 연결 항목", total)
    sc2.metric("Virtual (Seed)", virtual, help="가상 데이터로 검증 중")
    sc3.metric("미연결", disconnected, help="구축 시 연결 필요")
    sc4.metric("실제 연결", "0", help="실제 소스 시스템 연결 (구축 Phase)")

    st.divider()

    # 필터
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        sys_filter = st.multiselect(
            "소스 시스템 필터",
            options=df_status["소스 시스템"].unique().tolist(),
            default=df_status["소스 시스템"].unique().tolist(),
        )
    with filter_col2:
        status_filter = st.multiselect(
            "상태 필터",
            options=["Virtual", "미연결"],
            default=["Virtual", "미연결"],
        )

    filtered = df_status[
        (df_status["소스 시스템"].isin(sys_filter)) &
        (df_status["연결 상태"].isin(status_filter))
    ]

    st.dataframe(filtered, use_container_width=True, hide_index=True)

    # 구축 로드맵
    st.divider()
    st.subheader("구축 시 데이터 연결 로드맵")

    phases = [
        {
            "phase": "Phase 1: 핵심 재무 데이터",
            "systems": ["SAP ERP (FI/CO)", "경영계획 시스템"],
            "tables": ["financials", "business_units"],
            "priority": "P1 (최우선)",
            "desc": "매출/EBITDA/CAPEX 실적 + 계획 데이터 연결. M1 Executive Dashboard 운영 가능.",
            "color": "#C00000",
        },
        {
            "phase": "Phase 2: EPC 프로젝트 데이터",
            "systems": ["SAP PS (Project System)"],
            "tables": ["projects", "evm_monthly", "kpi_values (EVM)"],
            "priority": "P1 (최우선)",
            "desc": "CPI/SPI/EAC/공정진척률/Earned Schedule 연결. M2 Driver Tree + M5 Early Warning + M6 EVM Monitor 운영 가능.",
            "color": "#2F5496",
        },
        {
            "phase": "Phase 3: 설비/운영 데이터",
            "systems": ["MES / IoT 플랫폼"],
            "tables": ["kpi_values (가동률/처리량)"],
            "priority": "P2 (차순위)",
            "desc": "설비 가동률/다운타임/처리량 실시간 연결. Green Energy/Recycling 사업부 운영 최적화.",
            "color": "#548235",
        },
        {
            "phase": "Phase 4: 리스크/ESG 데이터",
            "systems": ["HR/안전관리", "자금관리/리스크", "외부 데이터"],
            "tables": ["risk_items", "kpi_values (리스크)"],
            "priority": "P2 (차순위)",
            "desc": "환율/안전/ESG/시장 데이터 연결. M4 What-if + M5 Early Warning 완전 운영.",
            "color": "#BF8F00",
        },
    ]

    for p in phases:
        st.markdown(
            f'<div style="border-left:4px solid {p["color"]};padding:0.8rem 1rem;'
            f'margin-bottom:0.8rem;border-radius:0 8px 8px 0;'
            f'border:1px solid rgba(128,128,128,0.2);border-left:4px solid {p["color"]};">'
            f'<strong style="color:{p["color"]};">{p["phase"]}</strong> '
            f'<span style="font-size:0.85rem;opacity:0.7;">({p["priority"]})</span><br>'
            f'<span style="font-size:0.9rem;">{p["desc"]}</span><br>'
            f'<span style="font-size:0.8rem;opacity:0.6;">'
            f'소스: {", ".join(p["systems"])} | 대상: {", ".join(p["tables"])}</span>'
            f'</div>',
            unsafe_allow_html=True
        )
