"""Data Connection Map - SK네트웍스 데이터 연결 현황 및 소스 시스템 매핑"""
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

st.set_page_config(page_title="Data Connection Map", page_icon="🔗", layout="wide")
st.title("🔗 Data Connection Map")
st.caption("소스 시스템 -> DSS 테이블 -> 모듈 연결 현황 및 데이터 리니지")

# ══════════════════════════════════════════════════
# 소스 시스템 정의 (SK네트웍스 지주사 시스템 구조)
# ══════════════════════════════════════════════════
SOURCE_SYSTEMS = {
    "SAP_ERP": {
        "name": "SAP ERP (FI/CO)",
        "type": "ERP",
        "desc": "연결재무회계/관리회계 통합",
        "owner": "재무팀",
        "color": "#0070C0",
        "tables": {
            "BKPF/BSEG": {"desc": "회계전표 (매출/매출원가/판관비)", "target_table": "financials", "target_cols": ["revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit"], "frequency": "일별"},
            "ANLAV": {"desc": "고정자산 (감가상각/CAPEX)", "target_table": "financials", "target_cols": ["capex"], "frequency": "월별"},
            "FAGLFLEXA": {"desc": "총계정원장 (영업현금흐름)", "target_table": "financials", "target_cols": ["operating_cf"], "frequency": "월별"},
        },
    },
    "CRM_RENTAL": {
        "name": "CRM / 렌탈관리",
        "type": "CRM",
        "desc": "구독/렌탈 계약 및 고객 관리",
        "owner": "영업지원팀",
        "color": "#2F5496",
        "tables": {
            "CONTRACT": {"desc": "렌탈/구독 계약 (계정수/ARPU)", "target_table": "kpi_values", "target_cols": ["SUB_BASE", "SUB_ARPU", "SUB_MAGIC_ACC", "SUB_RENT_ACC"], "frequency": "일별"},
            "CHURN_LOG": {"desc": "해지/이탈 이력", "target_table": "kpi_values", "target_cols": ["SUB_CHURN", "CHURN_MAGIC", "CHURN_RENT", "CHURN_REASON"], "frequency": "일별"},
            "NEW_SIGNUP": {"desc": "신규가입/재가입", "target_table": "kpi_values", "target_cols": ["SUB_NEW", "SUB_RENEW"], "frequency": "일별"},
        },
    },
    "ASSET_MGMT": {
        "name": "자산관리 시스템",
        "type": "Asset",
        "desc": "차량/호텔/키오스크 자산 운영",
        "owner": "자산관리팀",
        "color": "#548235",
        "tables": {
            "VEHICLE_STATUS": {"desc": "차량 가동/정비 상태", "target_table": "kpi_values", "target_cols": ["UTIL_VEHICLE", "VH_TOTAL", "VH_ACTIVE", "VH_MAINT"], "frequency": "일별"},
            "HOTEL_OPS": {"desc": "객실 점유/매출 데이터", "target_table": "kpi_values", "target_cols": ["UTIL_HOTEL", "HOTEL_ADR", "HOTEL_REVPAR"], "frequency": "일별"},
            "KIOSK_STATUS": {"desc": "민팃 키오스크 가동 현황", "target_table": "kpi_values", "target_cols": ["UTIL_KIOSK"], "frequency": "실시간"},
        },
    },
    "PLAN_BUDGET": {
        "name": "경영계획 시스템",
        "type": "Planning",
        "desc": "연간/월별 경영계획 및 예산",
        "owner": "경영기획팀",
        "color": "#BF8F00",
        "tables": {
            "PLAN_REV": {"desc": "매출 계획 (계열사별/월별)", "target_table": "financials", "target_cols": ["plan_revenue"], "frequency": "연 1회"},
            "PLAN_EBITDA": {"desc": "EBITDA 계획", "target_table": "financials", "target_cols": ["plan_ebitda"], "frequency": "연 1회"},
            "KPI_TARGET": {"desc": "KPI 목표값", "target_table": "kpi_values", "target_cols": ["plan"], "frequency": "연 1회"},
        },
    },
    "INVEST_MGMT": {
        "name": "투자관리 시스템",
        "type": "Investment",
        "desc": "포트폴리오/지분/신사업 관리",
        "owner": "투자전략팀",
        "color": "#7030A0",
        "tables": {
            "PORTFOLIO": {"desc": "계열사 지분가치/배당", "target_table": "kpi_values", "target_cols": ["PORTFOLIO_VAL", "EQUITY_INCOME", "DIV_YIELD"], "frequency": "분기별"},
            "NEW_BIZ": {"desc": "신사업 투자 현황", "target_table": "kpi_values", "target_cols": ["NB_CAPEX", "NB_IRR", "NB_PAYBACK"], "frequency": "월별"},
        },
    },
    "RISK_ESG": {
        "name": "리스크/ESG 관리",
        "type": "Risk/ESG",
        "desc": "재무리스크, ESG, 규제 관리",
        "owner": "리스크관리팀",
        "color": "#C00000",
        "tables": {
            "FIN_RISK": {"desc": "재무건전성 지표", "target_table": "kpi_values", "target_cols": ["FIN_DEBT_RATIO", "FIN_LIQUIDITY", "FIN_INTEREST"], "frequency": "월별"},
            "ESG_DATA": {"desc": "ESG 평가 데이터", "target_table": "kpi_values", "target_cols": ["ESG_SCORE", "ESG_ENV", "ESG_SOCIAL", "ESG_GOV"], "frequency": "분기별"},
            "REG_MONITOR": {"desc": "규제 변화 모니터링", "target_table": "risk_items", "target_cols": ["probability", "impact"], "frequency": "수시"},
        },
    },
    "EXTERNAL": {
        "name": "외부 데이터",
        "type": "External API",
        "desc": "시장 데이터, 경쟁 벤치마크",
        "owner": "데이터팀",
        "color": "#999999",
        "tables": {
            "MARKET_INDEX": {"desc": "경기지표/금리/환율", "target_table": "kpi_values", "target_cols": ["MKT_DEMAND", "MKT_COMPETE"], "frequency": "일별"},
            "PEER_BENCHMARK": {"desc": "경쟁사/업계 벤치마크", "target_table": "kpi_definitions", "target_cols": ["description"], "frequency": "분기별"},
        },
    },
}

# DSS 테이블 -> 모듈 매핑 (M6 제외)
TABLE_MODULE_MAP = {
    "business_units": ["M1", "M2", "M3", "M4", "M5"],
    "financials": ["M1", "M2", "M4"],
    "kpi_definitions": ["M1", "M2", "M3"],
    "kpi_values": ["M1", "M2", "M3", "M5"],
    "biz_questions": ["M3"],
    "risk_items": ["M5", "M4"],
    "scenario_runs": ["M4"],
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

    flow_nodes = []
    flow_links = []

    NODE_Y_START = 70
    NODE_Y_RANGE = 560

    # 소스 시스템 노드
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

    # DSS 테이블 노드
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

    # 모듈 노드
    module_colors_map = {"M1": "#2F5496", "M2": "#548235", "M3": "#BF8F00", "M4": "#7030A0", "M5": "#C00000"}
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

    # 소스 → 테이블 링크
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

        var dbIcon = 'path://M4,2 C4,0.9 8,0 13,0 C18,0 22,0.9 22,2 L22,18 C22,19.1 18,20 13,20 C8,20 4,19.1 4,18 Z M4,2 C4,3.1 8,4 13,4 C18,4 22,3.1 22,2';
        var moduleIcon = 'path://M2,0 L22,0 C23.1,0 24,0.9 24,2 L24,16 C24,17.1 23.1,18 22,18 L2,18 C0.9,18 0,17.1 0,16 L0,2 C0,0.9 0.9,0 2,0 Z M0,5 L24,5';

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
                        if (d.category === 1) return '<b>' + d.name + '</b><br/>행: ' + d.rows.toLocaleString() + '<br/>컬럼: ' + d.columns + '개<br/>FK: ' + d.fk_count + '개';
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

    leg_cols = st.columns(3)
    leg_cols[0].markdown("**소스 시스템** (좌측) - ERP, CRM, 자산관리, 투자관리 등")
    leg_cols[1].markdown("**DSS 테이블** (중앙) - 디지털 트윈 DB 7개 테이블")
    leg_cols[2].markdown("**시스템 모듈** (우측) - M1~M5 5대 모듈")


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

    selected_table = st.selectbox("테이블 선택", list(db_stats.keys()))

    if selected_table:
        stats = db_stats[selected_table]

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("행 수", f"{stats['rows']:,}")
        mc2.metric("컬럼 수", stats["columns"])
        mc3.metric("FK 관계", stats["fk_count"])
        mc4.metric("연결 모듈", ", ".join(TABLE_MODULE_MAP.get(selected_table, [])))

        col_data = []
        for name, typ in zip(stats["col_names"], stats["col_types"]):
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

        if stats["fks"]:
            st.markdown("#### FK 관계 (참조)")
            for fk in stats["fks"]:
                st.markdown(f"- `{selected_table}.{fk['from']}` -> `{fk['to_table']}.{fk['to_col']}`")

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

    st.divider()
    st.subheader("테이블 관계도 (ERD)")

    erd_raw_nodes = []
    erd_raw_links = []

    erd_table_colors = {
        "business_units": "#2F5496",
        "financials": "#0070C0",
        "kpi_definitions": "#548235",
        "kpi_values": "#BF8F00",
        "biz_questions": "#7030A0",
        "risk_items": "#C00000",
        "scenario_runs": "#7030A0",
    }

    tbl_names = list(db_stats.keys())
    n_tables = len(tbl_names)
    cx, cy, radius = 400, 300, 220
    for i, table_name in enumerate(tbl_names):
        angle = (2 * math.pi * i / n_tables) - math.pi / 2
        stats = db_stats[table_name]
        tbl_color = erd_table_colors.get(table_name, "#548235")
        connected_modules = TABLE_MODULE_MAP.get(table_name, [])

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
                        var html = '<b style="color:' + d.color + '">' + d.name + '</b><br/>';
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


# ══════════════════════════════════════════════════
# TAB 4: 연결 상태 대시보드
# ══════════════════════════════════════════════════
with tab4:
    st.subheader("데이터 연결 상태 현황")

    st.markdown("""
    > **현재 모드: Digital Twin (Virtual Seed Data)**
    > 실제 소스 시스템 연결 전, 가상 데이터로 시스템을 검증하는 단계입니다.
    """)

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
                "수집 주기": mapping["frequency"],
                "연결 상태": status,
            })

    df_status = pd.DataFrame(status_data)

    total = len(df_status)
    virtual = len(df_status[df_status["연결 상태"] == "Virtual"])
    disconnected = len(df_status[df_status["연결 상태"] == "미연결"])

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("전체 연결 항목", total)
    sc2.metric("Virtual (Seed)", virtual)
    sc3.metric("미연결", disconnected)
    sc4.metric("실제 연결", "0")

    st.dataframe(df_status, use_container_width=True, hide_index=True)
