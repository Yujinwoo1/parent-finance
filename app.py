import re
from datetime import datetime
from zoneinfo import ZoneInfo
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import math
from database import (save_to_notion, add_favorite, get_favorites, remove_favorite,
                      get_audit_stats, get_all_reports)
from data_fetcher import (prepare_investment_data, _fetch_ticker_data,
                          get_sp500_tickers, get_ndx100_tickers,
                          scan_ticker_batch, get_price_on_or_after,
                          get_ticker_history_cached, get_price_on_or_after_local)
from ai_generator import generate_investment_report
from notifier import check_and_notify_favorites

# ---------------------------------------------------------
# 1. 페이지 설정 및 스타일
# ---------------------------------------------------------
st.set_page_config(page_title="AI 투자 위원회", layout="wide")
st.markdown("""
    <style>
    /* ── 숨김 ── */
    #MainMenu {visibility: hidden;}
    footer    {visibility: hidden;}

    /* ── CSS 변수 — 라이트/다크 자동 대응 ── */
    :root {
        --text-main: #1E1E1E;
        --border:    rgba(49,51,63,.12);
        --bg-card:   #FFFFFF;
    }
    @media (prefers-color-scheme: dark) {
        :root {
            --text-main: #FAFAFA;
            --border:    rgba(250,250,250,.12);
            --bg-card:   #1E2130;
        }
        strong { color: var(--text-main) !important; }
    }

    /* ── 공통 타이포그래피 ── */
    h1 { font-size: 24px !important; font-weight: 700 !important; margin-bottom: 8px !important; }
    h2 { font-size: 20px !important; font-weight: 700 !important; margin-top: 16px !important; }
    h3 { font-size: 17px !important; font-weight: 700 !important; }
    strong { font-weight: 600 !important; color: var(--text-main); }
    .stMarkdown p, .stMarkdown li {
        font-size: 15px !important;
        line-height: 1.75 !important;
        letter-spacing: -0.01em !important;
    }

    /* ── 데스크탑 (768px 이상) ── */
    @media (min-width: 768px) {
        .main .block-container {
            padding: 1.5rem 2.5rem !important;
            max-width: 1440px !important;
        }
        .stFormSubmitButton > button { font-size: 16px !important; }
    }

    /* ── 모바일 (767px 이하) ── */
    @media (max-width: 767px) {
        /* 컨테이너 여백 최소화 */
        .main .block-container {
            padding: 0.75rem 0.5rem !important;
            max-width: 100% !important;
        }

        /* ▼ 모든 st.columns → 세로 1열 ▼ */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }

        /* 타이포그래피 */
        h1 { font-size: 20px !important; }
        .stMarkdown p, .stMarkdown li { font-size: 16px !important; }

        /* 폼 입력 줌 방지 (iOS: 16px 미만이면 자동 줌) */
        input, select, textarea,
        .stTextInput input,
        .stNumberInput input { font-size: 16px !important; }

        /* 터치 영역 최소 48px */
        .stButton > button {
            min-height: 48px !important;
            font-size: 16px !important;
        }
        .stFormSubmitButton > button {
            min-height: 52px !important;
            font-size: 17px !important;
        }

        /* 라디오 버튼 세로 배치 */
        div[role="radiogroup"] { flex-direction: column !important; gap: 8px !important; }
        div[role="radiogroup"] label {
            white-space: normal !important;
            line-height: 1.5 !important;
            font-size: 16px !important;
            padding: 4px 0 !important;
        }

        /* 입력 필드 간격 */
        .stNumberInput, .stSlider, .stSelectbox { margin-bottom: 0.5rem !important; }

        /* Plotly 캔들 차트 높이를 300px으로 축소 (Streamlit 1.31+ 렌더러) */
        .price-chart [data-testid="stPlotlyChart"] > div:first-child {
            height: 300px !important;
            min-height: 300px !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. 초기화
# ---------------------------------------------------------
def parse_verdict(report_text):
    """AI 리포트 6섹션(의장 최종 전략)에서 BUY / HOLD / SELL 추출."""
    if not report_text:
        return None
    section = report_text
    for marker in ["6.", "의장의 최종", "최종 전략", "최종판결", "종합 전략"]:
        idx = report_text.find(marker)
        if idx != -1:
            section = report_text[idx : idx + 2000]
            break
    m = re.search(r"\b(STRONG[\s_]?BUY|BUY|HOLD|WATCH|SELL|STRONG[\s_]?SELL)\b",
                  section, re.IGNORECASE)
    if m:
        v = m.group(1).upper()
        if "BUY" in v:          return "BUY"
        if "SELL" in v:         return "SELL"
        if "HOLD" in v or "WATCH" in v: return "HOLD"
    if re.search(r"(적극\s*)?(매수|진입)\s*(추천|신호|권고|판결|승인)", section):
        return "BUY"
    if re.search(r"(적극\s*)?(매도|청산)\s*(추천|권고|판결)", section):
        return "SELL"
    if re.search(r"(관망|홀딩|보유\s*유지|매매\s*보류)", section):
        return "HOLD"
    return None


def parse_audit_winner(report_text):
    """AI 리포트 감사 섹션에서 승자(A / B / 무승부)를 추출."""
    try:
        idx = report_text.find('지난 예측 검증')
        if idx == -1:
            idx = report_text.find('Audit')
        section = report_text[idx:idx + 600] if idx != -1 else report_text[:600]
        if re.search(r'🏆\s*(?:전문가\s*)?A', section):
            return 'A'
        if re.search(r'🏆\s*(?:전문가\s*)?B', section):
            return 'B'
        if re.search(r'🤝|무승부', section):
            return '무승부'
    except Exception:
        pass
    return None

if 'active_ticker' not in st.session_state:
    st.session_state['active_ticker'] = 'TSLA'

# ---------------------------------------------------------
# 3. 사이드바: 장 상태 + 즐겨찾기 신호 스캔 + 예측 적중률
# ---------------------------------------------------------
with st.sidebar:
    # --- 미국 동부시간 기준 장 중 여부 ---
    et_now   = datetime.now(ZoneInfo("America/New_York"))
    et_min   = et_now.hour * 60 + et_now.minute
    is_open  = et_now.weekday() < 5 and 570 <= et_min < 960  # 9:30~16:00
    st.markdown(
        f"{'**🕐 장 중**' if is_open else '**🌙 장 마감**'}"
        f"  ·  ET {et_now.strftime('%m/%d %H:%M')}"
    )
    st.divider()

    # --- 즐겨찾기 토글 ---
    with st.expander("⭐ 즐겨찾기", expanded=True):
        # 엔터/버튼 모두 추가 가능한 미니 폼
        with st.form("_fav_add_form", clear_on_submit=True):
            _fav_cols = st.columns([4, 1])
            with _fav_cols[0]:
                new_ticker = st.text_input(
                    "티커 추가", placeholder="TSLA…",
                    label_visibility="collapsed"
                )
            with _fav_cols[1]:
                submitted_fav = st.form_submit_button("＋", use_container_width=True)

        if submitted_fav:
            sym = new_ticker.strip().upper()
            if sym:
                with st.spinner(f"{sym} 확인 중..."):
                    try:
                        import yfinance as yf
                        info = yf.Ticker(sym).fast_info
                        if not info.last_price:
                            raise ValueError("가격 없음")
                        add_favorite(sym)
                        st.toast(f"⭐ {sym} 즐겨찾기 추가 완료!")
                        st.rerun()
                    except Exception:
                        st.error(f"존재하지 않는 티커: {sym}")

        # 즐겨찾기 목록 + 신호 스캔
        favorites = get_favorites()
        if not favorites:
            st.caption("아직 추가된 종목이 없습니다.")
        else:
            fav_scan = []
            green_cnt = yellow_cnt = red_cnt = 0
            rows = []   # (icon, fav, score, price, grade, rsi, stop, target)
            for fav in favorites:
                try:
                    td    = _fetch_ticker_data(fav)
                    score = td['entry_score']
                    grade = td['entry_grade']
                    price = td['current_price']
                    rsi_v = float(td['rsi'].split('(')[0].strip())
                    icon  = '🟢' if grade == 'GREEN' else '🔴' if grade == 'RED' else '🟡'
                    if grade == 'GREEN':   green_cnt  += 1
                    elif grade == 'RED':   red_cnt    += 1
                    else:                  yellow_cnt += 1
                    fav_scan.append({
                        'ticker': fav, 'price': price, 'entry_score': score,
                        'entry_grade': grade, 'rsi': rsi_v,
                        'stop_loss': td['stop_loss'], 'target1': td['target1'],
                    })
                    rows.append((icon, fav, score, price, grade))
                except Exception:
                    rows.append(('⚪', fav, None, None, None))

            total_favs = len(favorites)
            st.markdown(
                f"<div style='font-size:12px;color:gray;margin-bottom:4px'>"
                f"총 {total_favs}종목 &nbsp;🟢 {green_cnt} &nbsp;🟡 {yellow_cnt} &nbsp;🔴 {red_cnt}"
                f"</div>",
                unsafe_allow_html=True
            )

            with st.container(height=180, border=False):
                for icon, fav, score, price, grade in rows:
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        label = (
                            f"{icon} {fav:<6s}  {score}pt  ${price:.1f}"
                            if score is not None else f"⚪ {fav} (로드 실패)"
                        )
                        if st.button(label, key=f"fav_{fav}", use_container_width=True):
                            st.session_state['active_ticker'] = fav
                            st.rerun()
                    with c2:
                        if st.button("✕", key=f"del_{fav}"):
                            remove_favorite(fav)
                            st.toast(f"✕ {fav} 즐겨찾기 삭제 완료")
                            st.rerun()

            if fav_scan:
                check_and_notify_favorites(fav_scan)

    st.divider()
    st.markdown("### 📊 예측 적중률")
    stats = get_audit_stats()
    total = stats['total']
    if total == 0:
        st.caption("분석 기록이 쌓이면 통계가 표시됩니다.")
    else:
        st.markdown(f"총 **{total}회** 분석 결과")
        a_pct = stats['A'] / total * 100
        b_pct = stats['B'] / total * 100
        d_pct = stats['무승부'] / total * 100
        st.markdown(f"📈 A (Chartist) 승: **{stats['A']}회** ({a_pct:.0f}%)")
        st.markdown(f"🐢 B (Believer) 승: **{stats['B']}회** ({b_pct:.0f}%)")
        st.markdown(f"🤝 무승부: **{stats['무승부']}회** ({d_pct:.0f}%)")
        st.progress(stats['A'] / total, text=f"A 누적 승률 {a_pct:.0f}%")

# ---------------------------------------------------------
# 4. 헤더 + 즐겨찾기 바 + 탭 분기
# ---------------------------------------------------------
st.title("🏛️ AI 투자 위원회 분석 시스템")
st.markdown("객관적 지표와 행동 심리 분석을 통해 **오늘의 BUY / HOLD / SELL 전략**을 확인하세요.")

st.divider()

tab_main, tab_backtest, tab_scanner = st.tabs(["📊 AI 분석", "🔬 백테스트", "🔭 시장 스캐너"])

# ═══════════════════════════════════════════════════════════
# TAB 1 — AI 분석 폼
# ═══════════════════════════════════════════════════════════
with tab_main:
# ---------------------------------------------------------
# 5. 분석 폼 — 데스크탑: 좌/우 2열 / 모바일: CSS로 세로 1열
# ---------------------------------------------------------
# 포지션 선택은 폼 밖에 배치 → 즉각 반응해 평단가/비중 표시 여부 결정
    st.markdown("#### 💼 현재 포지션")
    position = st.selectbox(
        "현재 포지션",
        ["✅ 이미 보유 중 (추매/매도 고민)", "👀 미보유 (신규 진입 대기)"],
        key="_position_select",
        label_visibility="collapsed",
    )

# 기본값 선언 (미보유 분기에서 위젯이 렌더링되지 않을 때 대비)
    avg_price, weight = 0.0, 0

    with st.form("analysis_form"):
        TARGET_TICKER = st.text_input(
            "▶️ 분석할 기업의 티커 (예: TSLA, AAPL)",
            value=st.session_state['active_ticker']
        )
        form_left, form_right = st.columns(2)
        with form_left:
            st.markdown("### 💼 포트폴리오 상태")
            if "보유 중" in position:
                avg_price = st.number_input("내 평단가 ($)", min_value=0.0, value=0.0, step=10.0)
                weight    = st.slider("포트폴리오 내 비중 (%)", 0, 100, 10)
            else:
                st.info("미보유 상태 — 신규 진입 관점으로 분석합니다.")
        with form_right:
            st.markdown("### 🧠 나의 현재 상태")
            psycho_state = st.selectbox(
                "지금 내 속마음은?",
                [
                    "😰 수익 중인데 언제 떨어질지 불안 (익절 타이밍 고민)",
                    "😤 손실 중인데 본전오면 팔고 싶음 (손실 회피)",
                    "😱 안 사면 벼락거지 될 것 같음 (FOMO)",
                    "😶 크게 물렸지만 언젠가 오를 거라 믿음 (비자발적 장기투자)",
                    "🤔 분할 매수/매도 원칙대로 진행 중 (이성적)",
                    "😌 그냥 지켜보는 중 (단순 관망)",
                    "💸 손절 고민 중인데 결정 못하고 있음",
                    "🎯 목표가 도달 임박, 익절 타이밍 재는 중",
                ]
            )
            action_plan = st.selectbox(
                "오늘 내가 하고 싶은 행동은?",
                [
                    "🛒 신규 진입하고 싶다 (처음 매수)",
                    "➕ 추가 매수하고 싶다 (불타기/물타기)",
                    "✂️ 일부 익절하고 싶다 (비중 줄이기)",
                    "🚪 전량 매도하고 싶다 (완전 정리)",
                    "🔄 종목 교체를 고민 중이다",
                    "🧘 그냥 홀딩하고 싶다 (관망)",
                    "⏰ 분할 매수/매도 진행 중이다",
                ]
            )
            with st.expander("📊 [선택] 거시 시장 심리 지수 직접 입력"):
                st.info("수치를 입력하면 '전문가 C'가 군중 심리와 비교 분석을 추가합니다.")
                mx1, mx2 = st.columns(2)
                with mx1:
                    vix_input = st.number_input("VIX 변동성 지수", min_value=0.0, value=0.0, step=1.0)
                with mx2:
                    fg_input = st.number_input("CNN 공포탐욕지수 (0~100)", min_value=0, max_value=100, value=0, step=1)
        submitted = st.form_submit_button("🚀 나의 매매 계획 진단받기", use_container_width=True)

    # ---------------------------------------------------------
    # 6. 제출 후 실행 로직
    # ---------------------------------------------------------
    if submitted:
        TARGET_TICKER = TARGET_TICKER.strip().upper() if TARGET_TICKER else "TSLA"
        st.session_state['active_ticker'] = TARGET_TICKER

        if "보유 중" in position:
            MY_CONTEXT = f"현재 주식을 보유 중(평단가: ${avg_price:.2f}, 비중: {weight}%)입니다. \n나의 오늘 매매 계획은 '{action_plan}' 입니다."
        else:
            MY_CONTEXT = f"현재 주식을 보유하고 있지 않습니다. \n나의 오늘 매매 계획은 '{action_plan}' 입니다."

        MY_FEEDBACK = psycho_state

        if vix_input > 0 or fg_input > 0:
            macro_text = "\n\n[🌐 거시 시장 심리 데이터]\n"
            if vix_input > 0: macro_text += f"- VIX 지수: {vix_input}\n"
            if fg_input > 0:  macro_text += f"- CNN 공포탐욕지수: {fg_input}\n"
            MY_CONTEXT  += macro_text
            MY_FEEDBACK += " \n**(특별 지시: 전문가 C는 방금 제공된 '거시 시장 심리 데이터'의 수치와 나의 '현재 심리/매매 계획'을 직접적으로 비교 분석하여, 내가 군중 심리에 휩쓸린 것인지 역발상 투자인지 날카롭게 비판해 주세요.)**"

        try:
            with st.spinner(f"[{TARGET_TICKER}] 데이터를 분석하고 위원회 토론을 진행 중입니다..."):
                investment_data = prepare_investment_data(TARGET_TICKER, MY_CONTEXT, MY_FEEDBACK)
                final_report    = generate_investment_report(investment_data)
                audit_winner    = parse_audit_winner(final_report)
                verdict         = parse_verdict(final_report)

                notion_vix = vix_input if vix_input > 0 else investment_data.get("vix_raw", 0.0)
                notion_fg = fg_input if fg_input > 0 else investment_data.get("cnn_fg_raw", 0.0)

                notion_success, notion_msg = save_to_notion(
                    TARGET_TICKER, investment_data["current_price"],
                    notion_vix, notion_fg, psycho_state, action_plan,
                    final_report, audit_winner, verdict,
                )

            st.success("분석이 완료되었습니다!")
            if notion_success:
                st.info("✅ 노션 매매일지에 리포트가 성공적으로 백업되었습니다.")
            else:
                st.warning(f"⚠️ 노션 백업 건너뜀 (사유: {notion_msg})")

            current_favs = get_favorites()
            if TARGET_TICKER not in current_favs:
                if st.button(f"⭐ {TARGET_TICKER} 즐겨찾기에 추가", use_container_width=False):
                    add_favorite(TARGET_TICKER)
                    st.rerun()

            st.markdown("### 📊 빠른 진단")

            entry_color = "#2ECC71" if investment_data["entry_grade"] == "GREEN" \
                     else "#E74C3C" if investment_data["entry_grade"] == "RED" \
                     else "#F39C12"
            cs       = investment_data.get("canslim", {})
            cs_total = cs.get("total", 50)
            cs_grade = cs.get("grade", "YELLOW")
            cs_color = "#2ECC71" if cs_grade == "GREEN" else "#E74C3C" if cs_grade == "RED" else "#F39C12"
            rsi_num  = float(investment_data["rsi"].split("(")[0].strip())
            rsi_color = "#E74C3C" if rsi_num >= 70 else "#2ECC71" if rsi_num <= 30 else "#3498DB"

            fig_gauges = make_subplots(
                rows=1, cols=3,
                specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]],
                column_widths=[0.34, 0.33, 0.33],
            )
            fig_gauges.add_trace(go.Indicator(
                mode="gauge+number", value=investment_data["entry_score"],
                title={"text": "기술 진입 점수"},
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": entry_color, "thickness": 0.25},
                       "steps": [{"range": [0,35], "color":"#FADBD8"},{"range":[35,65],"color":"#FEF9E7"},{"range":[65,100],"color":"#D5F5E3"}],
                       "threshold": {"line":{"color":"gray","width":2},"thickness":0.75,"value":investment_data["entry_score"]}},
            ), row=1, col=1)
            fig_gauges.add_trace(go.Indicator(
                mode="gauge+number", value=cs_total,
                title={"text": "CAN SLIM 점수"},
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": cs_color, "thickness": 0.25},
                       "steps": [{"range": [0,35], "color":"#FADBD8"},{"range":[35,65],"color":"#FEF9E7"},{"range":[65,100],"color":"#D5F5E3"}],
                       "threshold": {"line":{"color":"gray","width":2},"thickness":0.75,"value":cs_total}},
            ), row=1, col=2)
            fig_gauges.add_trace(go.Indicator(
                mode="gauge+number", value=rsi_num,
                title={"text": "RSI (14)"},
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": rsi_color, "thickness": 0.25},
                       "steps": [{"range":[0,30],"color":"#D5F5E3"},{"range":[30,70],"color":"#EBF5FB"},{"range":[70,100],"color":"#FADBD8"}],
                       "threshold": {"line":{"color":"gray","width":2},"thickness":0.75,"value":rsi_num}},
            ), row=1, col=3)
            fig_gauges.update_layout(height=220, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_gauges, use_container_width=True)

            if cs and "C" in cs:
                _cs_meta = {"C":"Current EPS (분기 성장)","A":"Annual EPS (ROE)","N":"New High (신고가)",
                            "S":"Supply/Demand (수급)","L":"Leader (상대강도)","I":"Institutional (기관)","M":"Market (시장 방향)"}
                ok_cnt = sum(1 for k in "CANSLIM" if k in cs and isinstance(cs[k], tuple) and cs[k][0] > 0)
                with st.expander(f"📈 CAN SLIM 점수카드  — {ok_cnt}/7 충족  |  {cs_total}점 ({cs_grade})", expanded=True):
                    import pandas as _pd
                    rows_data = []
                    for k in "CANSLIM":
                        if k not in cs or not isinstance(cs[k], tuple): continue
                        sc, val, _ = cs[k]
                        icon = "✅" if sc > 0 else "❌" if sc < 0 else "➖"
                        rows_data.append({"팩터": f"{icon} **{k}**", "항목": _cs_meta[k], "값": val, "점수": f"{sc:+d}"})
                    st.dataframe(_pd.DataFrame(rows_data), use_container_width=True, hide_index=True,
                                 column_config={"팩터": st.column_config.TextColumn(width="small"),
                                                "점수": st.column_config.TextColumn(width="small")})

            cur  = investment_data["current_price"]
            risk = cur - investment_data["stop_loss"]
            rwd1 = investment_data["target1"] - cur
            rwd2 = investment_data["target2"] - cur
            rr1  = rwd1 / risk if risk > 0 else 0
            rr2  = rwd2 / risk if risk > 0 else 0
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("🛡️ 손절가 (ATR×1.5)", f"${investment_data['stop_loss']:.2f}",
                       f"-{risk/cur*100:.1f}%", delta_color="inverse")
            mc2.metric("🎯 1차 익절 (ATR×2.0)", f"${investment_data['target1']:.2f}",
                       f"+{rwd1/cur*100:.1f}%  ·  1:{rr1:.1f}")
            mc3.metric("🚀 2차 익절 (ATR×3.5)", f"${investment_data['target2']:.2f}",
                       f"+{rwd2/cur*100:.1f}%  ·  1:{rr2:.1f}")
            st.caption("✅ 진입 승인 (R/R ≥ 1:2)" if rr1 >= 2 else "⛔ 진입 보류 (R/R < 1:2)")

            oi_data = investment_data.get("oi_heatmap")
            if oi_data and oi_data.get("strikes"):
                st.markdown("##### 📊 옵션 OI 분포 (현재가 ±25%)")
                fig_oi = go.Figure()
                fig_oi.add_trace(go.Bar(x=oi_data["strikes"], y=oi_data["calls"],
                                        name="Call OI", marker_color="rgba(46,204,113,0.7)"))
                fig_oi.add_trace(go.Bar(x=oi_data["strikes"], y=oi_data["puts"],
                                        name="Put OI", marker_color="rgba(231,76,60,0.7)"))
                fig_oi.add_vline(x=cur, line_dash="dash", line_color="#3498DB",
                                 annotation_text=f"현재가 ${cur:.2f}", annotation_position="top left")
                if oi_data.get("max_pain"):
                    fig_oi.add_vline(x=oi_data["max_pain"], line_dash="dot", line_color="orange",
                                     annotation_text=f"Max Pain ${oi_data['max_pain']:.2f}",
                                     annotation_position="top right")
                fig_oi.update_layout(barmode="group", height=260, margin=dict(l=0,r=0,t=35,b=0),
                                     legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig_oi, use_container_width=True)

            st.divider()
            chart_col, report_col = st.columns([6, 4])
            with chart_col:
                st.markdown('<div class="price-chart">', unsafe_allow_html=True)
                df_chart = investment_data["chart_data"].tail(120)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                    vertical_spacing=0.03, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=df_chart.index,
                    open=df_chart["Open"], high=df_chart["High"],
                    low=df_chart["Low"], close=df_chart["Close"], name="Price"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["MA20"],
                                         line=dict(color="orange", width=1.5), name="20일선"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["MA60"],
                                         line=dict(color="green", width=1.5), name="60일선"), row=1, col=1)
                fig.add_trace(go.Bar(x=df_chart.index, y=df_chart["Volume"],
                                     name="Volume", marker_color="rgba(100,150,250,0.5)"), row=2, col=1)
                fig.update_layout(title=f"{TARGET_TICKER} 최근 6개월",
                                  xaxis_rangeslider_visible=False,
                                  height=500, margin=dict(l=0,r=0,t=40,b=0))
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
                st.plotly_chart(fig, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
            with report_col:
                with st.container(border=True):
                    st.markdown(final_report)
                with st.expander("🔍 옵션 데이터 수집 확인 (AI에 전달된 원본값)"):
                    st.markdown("**1차 만기 PCR:**")
                    st.code(investment_data.get("options", "KEY_MISSING"))
                    st.markdown("**만기별 PCR (3개):**")
                    st.code(investment_data.get("options_pcr_multi", "KEY_MISSING"))
                    mp = investment_data.get("max_pain")
                    st.markdown(f"**Max Pain:** {'${:.2f}'.format(mp) if mp else '산출 불가 (None)'}")
                    hm = investment_data.get("oi_heatmap")
                    st.markdown(f"**OI 히트맵 데이터:** {'행사가 {}개 로드됨'.format(len(hm['strikes'])) if hm else '없음'}")
                    st.caption("에러 메시지가 표시되면 해당 종목의 옵션 체인이 yfinance에서 조회 불가인 것입니다.")

        except Exception as e:
            st.error(f"실행 중 오류가 발생했습니다: {e}")

# ═══════════════════════════════════════════════════════════
# TAB 2 — 백테스트
# ═══════════════════════════════════════════════════════════
with tab_backtest:
    st.markdown("### 🔬 AI 판결 백테스트")
    st.caption("노션에 저장된 리포트 기준 — 판결(BUY/HOLD/SELL)과 이후 실제 수익률 비교")

    reports = get_all_reports(limit=200)
    if not reports:
        st.info("아직 저장된 리포트가 없거나 불러오지 못했습니다.")
    else:
        scored = [r for r in reports if r.get("verdict")]
        buy_correct = buy_total = sell_correct = sell_total = 0
        table_rows = []

        # 고유 티커별로 2년 주가 이력을 1회 사전 수집하여 캐싱
        unique_tickers = set(r["ticker"] for r in scored)
        with st.spinner("백테스트를 위한 시장 데이터를 수집 중입니다..."):
            ticker_histories = {t: get_ticker_history_cached(t) for t in unique_tickers}

        for r in scored:
            hist = ticker_histories.get(r["ticker"])
            p10 = get_price_on_or_after_local(hist, r["date"], 10)
            p30 = get_price_on_or_after_local(hist, r["date"], 30)
            p60 = get_price_on_or_after_local(hist, r["date"], 60)
            base = r["price"]

            def _pct(fut):
                if fut is None or base <= 0:
                    return None
                return round((fut - base) / base * 100, 2)

            r10, r30, r60 = _pct(p10), _pct(p30), _pct(p60)

            verdict = r["verdict"]
            if verdict == "BUY" and r10 is not None:
                buy_total += 1
                if r10 > 0: buy_correct += 1
            elif verdict == "SELL" and r10 is not None:
                sell_total += 1
                if r10 < 0: sell_correct += 1

            def _fmt(pct):
                if pct is None: return "미완료"
                sign = "+" if pct >= 0 else ""
                return f"{sign}{pct:.1f}%"

            v_icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(verdict, "⚪")
            table_rows.append({
                "종목":    r["ticker"],
                "날짜":    r["date"],
                "판결":    f"{v_icon} {verdict}",
                "당시가":  f"${base:.2f}",
                "+10일":  _fmt(r10),
                "+30일":  _fmt(r30),
                "+60일":  _fmt(r60),
            })

        # 전체 적중률 요약
        if buy_total + sell_total > 0:
            total_scored = buy_total + sell_total
            correct = buy_correct + sell_correct
            overall_pct = correct / total_scored * 100
            c1, c2, c3 = st.columns(3)
            c1.metric("전체 적중률 (BUY+SELL, +10일 기준)",
                      f"{overall_pct:.0f}%", f"{correct}/{total_scored}건")
            if buy_total:
                c2.metric("BUY 적중률", f"{buy_correct/buy_total*100:.0f}%",
                          f"{buy_correct}/{buy_total}건")
            if sell_total:
                c3.metric("SELL 적중률", f"{sell_correct/sell_total*100:.0f}%",
                          f"{sell_correct}/{sell_total}건")
        else:
            st.info("verdict가 기록된 리포트가 아직 없습니다. AI 분석 탭에서 분석을 진행하면 자동 저장됩니다.")

        # 전문가 A vs B 승률
        winners = [r["winner"] for r in reports if r.get("winner")]
        if winners:
            a_w = winners.count("A"); b_w = winners.count("B"); d_w = winners.count("무승부")
            st.markdown(
                f"**전문가 승률** — 📈 A: {a_w}승  🐢 B: {b_w}승  🤝 무승부: {d_w}"
            )

        import pandas as _pd
        st.dataframe(
            _pd.DataFrame(table_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "+10일": st.column_config.TextColumn(),
                "+30일": st.column_config.TextColumn(),
                "+60일": st.column_config.TextColumn(),
            },
        )

# ═══════════════════════════════════════════════════════════
# TAB 3 — 시장 스캐너
# ═══════════════════════════════════════════════════════════
with tab_scanner:
    st.markdown("### 🔭 시장 전체 스캐너")
    st.caption("AI 없이 기술 진입점수만으로 전체 종목 스캔 (캐시: 1시간)")

    sc_col1, sc_col2 = st.columns([3, 1])
    with sc_col1:
        universe = st.selectbox(
            "스캔 대상",
            ["Nasdaq-100 (~100종목, 빠름)", "S&P 500 (~500종목, 느림)"],
            label_visibility="collapsed",
        )
    with sc_col2:
        scan_btn = st.button("🔭 스캔 시작", use_container_width=True)

    if scan_btn:
        if "S&P 500" in universe:
            all_tickers = get_sp500_tickers()
        else:
            all_tickers = get_ndx100_tickers()

        BATCH = 50
        n_batches = math.ceil(len(all_tickers) / BATCH)
        prog = st.progress(0, text="스캔 준비 중...")
        scan_results = []
        for i in range(n_batches):
            batch = tuple(all_tickers[i * BATCH : (i + 1) * BATCH])
            prog.progress(
                (i + 1) / n_batches,
                text=f"스캔 중... {min((i+1)*BATCH, len(all_tickers))}/{len(all_tickers)}종목",
            )
            scan_results.extend(scan_ticker_batch(batch))
        prog.empty()
        scan_results.sort(key=lambda x: x["entry_score"], reverse=True)
        st.session_state["scan_results"] = scan_results
        st.session_state["scan_universe"] = universe

    results = st.session_state.get("scan_results", [])
    if results:
        green  = [r for r in results if r["entry_grade"] == "GREEN"]
        yellow = [r for r in results if r["entry_grade"] == "YELLOW"]
        red    = [r for r in results if r["entry_grade"] == "RED"]
        total  = len(results)
        green_pct = len(green) / total * 100 if total else 0

        heat_label = ("🔥 시장 과열 주의 (GREEN 30%↑)" if green_pct >= 30
                      else "❄️ 시장 침체 구간 (GREEN 10%↓)" if green_pct < 10
                      else "⚖️ 시장 중립")
        st.markdown(
            f"**{st.session_state.get('scan_universe', '')} 스캔 결과** — "
            f"🟢 GREEN {len(green)}  🟡 YELLOW {len(yellow)}  🔴 RED {len(red)}  |  {heat_label}"
        )

        scan_tab_green, scan_tab_yellow, scan_tab_red = st.tabs([
            f"🟢 GREEN ({len(green)})", 
            f"🟡 YELLOW ({len(yellow)})", 
            f"🔴 RED ({len(red)})"
        ])

        import pandas as _pd

        with scan_tab_green:
            if green:
                green_df = _pd.DataFrame([{
                    "티커":    r["ticker"],
                    "점수":    r["entry_score"],
                    "현재가":  f"${r['price']:.2f}",
                    "RSI":     r["rsi"],
                    "52W위치": f"{r['w52_pct']:.0f}%",
                } for r in green])
                st.dataframe(green_df, use_container_width=True, hide_index=True)

                st.caption("티커를 클릭하면 즉시 AI 분석 대상(active_ticker)으로 설정되고 분석이 준비됩니다.")
                _gcols = st.columns(min(len(green), 8))
                for _gi, _gr in enumerate(green[:8]):
                    with _gcols[_gi]:
                        if st.button(_gr["ticker"], key=f"scan_green_{_gr['ticker']}", use_container_width=True):
                            st.session_state["active_ticker"] = _gr["ticker"]
                            st.toast(f"🎯 분석 대상을 {_gr['ticker']}로 설정했습니다! AI 분석 탭을 확인하세요.")
                            st.rerun()
            else:
                st.info("GREEN 등급 종목이 없습니다.")

        with scan_tab_yellow:
            if yellow:
                yellow_df = _pd.DataFrame([{
                    "티커":    r["ticker"],
                    "점수":    r["entry_score"],
                    "현재가":  f"${r['price']:.2f}",
                    "RSI":     r["rsi"],
                    "52W위치": f"{r['w52_pct']:.0f}%",
                } for r in yellow])
                st.dataframe(yellow_df, use_container_width=True, hide_index=True)

                st.caption("티커를 클릭하면 즉시 AI 분석 대상(active_ticker)으로 설정되고 분석이 준비됩니다.")
                _ycols = st.columns(min(len(yellow), 8))
                for _yi, _yr in enumerate(yellow[:8]):
                    with _ycols[_yi]:
                        if st.button(_yr["ticker"], key=f"scan_yellow_{_yr['ticker']}", use_container_width=True):
                            st.session_state["active_ticker"] = _yr["ticker"]
                            st.toast(f"🎯 분석 대상을 {_yr['ticker']}로 설정했습니다! AI 분석 탭을 확인하세요.")
                            st.rerun()
            else:
                st.info("YELLOW 등급 종목이 없습니다.")

        with scan_tab_red:
            if red:
                red_df = _pd.DataFrame([{
                    "티커":    r["ticker"],
                    "점수":    r["entry_score"],
                    "현재가":  f"${r['price']:.2f}",
                    "RSI":     r["rsi"],
                    "52W위치": f"{r['w52_pct']:.0f}%",
                } for r in red])
                st.dataframe(red_df, use_container_width=True, hide_index=True)

                st.caption("티커를 클릭하면 즉시 AI 분석 대상(active_ticker)으로 설정되고 분석이 준비됩니다.")
                _rcols = st.columns(min(len(red), 8))
                for _ri, _rr in enumerate(red[:8]):
                    with _rcols[_ri]:
                        if st.button(_rr["ticker"], key=f"scan_red_{_rr['ticker']}", use_container_width=True):
                            st.session_state["active_ticker"] = _rr["ticker"]
                            st.toast(f"🎯 분석 대상을 {_rr['ticker']}로 설정했습니다! AI 분석 탭을 확인하세요.")
                            st.rerun()
            else:
                st.info("RED 등급 종목이 없습니다.")
    else:
        st.info("스캔 대상을 선택하고 '🔭 스캔 시작'을 눌러주세요.")
