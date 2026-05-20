import re
from datetime import datetime
from zoneinfo import ZoneInfo
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from database import (save_to_notion, add_favorite, get_favorites, remove_favorite, get_audit_stats)
from data_fetcher import prepare_investment_data, _fetch_ticker_data
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

if 'ticker_input' not in st.session_state:
    st.session_state['ticker_input'] = 'TSLA'

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
        # 종목 추가 검색창
        new_ticker = st.text_input(
            "티커 추가", placeholder="TSLA, AAPL...",
            key="_fav_add_input", label_visibility="collapsed"
        )
        if st.button("+ 추가", key="_fav_add_btn", use_container_width=True):
            sym = new_ticker.strip().upper()
            if sym:
                with st.spinner(f"{sym} 확인 중..."):
                    try:
                        import yfinance as yf
                        info = yf.Ticker(sym).fast_info
                        if not info.last_price:
                            raise ValueError("가격 없음")
                        add_favorite(sym)
                        st.success(f"{sym} 추가됨")
                        st.rerun()
                    except Exception:
                        st.error(f"존재하지 않는 티커: {sym}")

        st.divider()

        # 즐겨찾기 목록 + 신호 스캔
        favorites = get_favorites()
        if not favorites:
            st.caption("아직 추가된 종목이 없습니다.")
        else:
            fav_scan = []
            for fav in favorites:
                try:
                    td    = _fetch_ticker_data(fav)
                    score = td['entry_score']
                    grade = td['entry_grade']
                    price = td['current_price']
                    rsi_v = float(td['rsi'].split('(')[0].strip())
                    icon  = '🟢' if grade == 'GREEN' else '🔴' if grade == 'RED' else '🟡'
                    fav_scan.append({
                        'ticker': fav, 'price': price, 'entry_score': score,
                        'entry_grade': grade, 'rsi': rsi_v,
                        'stop_loss': td['stop_loss'], 'target1': td['target1'],
                    })
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        if st.button(
                            f"{icon} {fav}  {score}점  ${price:.1f}",
                            key=f"fav_{fav}", use_container_width=True
                        ):
                            st.session_state['ticker_input'] = fav
                            st.rerun()
                    with c2:
                        if st.button("✕", key=f"del_{fav}"):
                            remove_favorite(fav)
                            st.rerun()
                except Exception:
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.caption(f"⚪ {fav} (로드 실패)")
                    with c2:
                        if st.button("✕", key=f"del_{fav}"):
                            remove_favorite(fav)
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
# 4. 헤더 + 즐겨찾기 바
# ---------------------------------------------------------
st.title("🏛️ AI 투자 위원회 분석 시스템")
st.markdown("객관적 지표와 행동 심리 분석을 통해 **오늘의 BUY / HOLD / SELL 전략**을 확인하세요.")
st.divider()

# 즐겨찾기 바 — 데스크탑: 최대 6개 가로 배열 / 모바일: CSS로 세로 스택
_favs_main = get_favorites()
if _favs_main:
    st.caption("⭐ 즐겨찾기")
    _fcols = st.columns(min(len(_favs_main), 6))
    for _i, _fav in enumerate(_favs_main[:6]):
        with _fcols[_i]:
            if st.button(_fav, key=f"mfav_{_fav}", use_container_width=True):
                st.session_state['ticker_input'] = _fav
                st.rerun()

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
        key='ticker_input'
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

            notion_success, notion_msg = save_to_notion(
                TARGET_TICKER, investment_data['current_price'],
                vix_input, fg_input, psycho_state, action_plan, final_report, audit_winner
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

        # ── 빠른 진단 — 게이지 + R/R 메트릭 (항상 전체 너비) ──────────
        st.markdown("### 📊 빠른 진단")

        entry_color = "#2ECC71" if investment_data['entry_grade'] == "GREEN" \
                 else "#E74C3C" if investment_data['entry_grade'] == "RED" \
                 else "#F39C12"
        cs         = investment_data.get('canslim', {})
        cs_total   = cs.get('total', 50)
        cs_grade   = cs.get('grade', 'YELLOW')
        cs_color   = "#2ECC71" if cs_grade == "GREEN" else "#E74C3C" if cs_grade == "RED" else "#F39C12"
        rsi_num    = float(investment_data['rsi'].split('(')[0].strip())
        rsi_color  = "#E74C3C" if rsi_num >= 70 else "#2ECC71" if rsi_num <= 30 else "#3498DB"

        fig_gauges = make_subplots(
            rows=1, cols=3,
            specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]],
            column_widths=[0.34, 0.33, 0.33]
        )
        fig_gauges.add_trace(go.Indicator(
            mode="gauge+number",
            value=investment_data['entry_score'],
            title={"text": "기술 진입 점수"},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar":  {"color": entry_color, "thickness": 0.25},
                "steps": [
                    {"range": [0, 35],   "color": "#FADBD8"},
                    {"range": [35, 65],  "color": "#FEF9E7"},
                    {"range": [65, 100], "color": "#D5F5E3"},
                ],
                "threshold": {"line": {"color": "gray", "width": 2},
                              "thickness": 0.75, "value": investment_data['entry_score']},
            }
        ), row=1, col=1)
        fig_gauges.add_trace(go.Indicator(
            mode="gauge+number",
            value=cs_total,
            title={"text": "CAN SLIM 점수"},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar":  {"color": cs_color, "thickness": 0.25},
                "steps": [
                    {"range": [0, 35],   "color": "#FADBD8"},
                    {"range": [35, 65],  "color": "#FEF9E7"},
                    {"range": [65, 100], "color": "#D5F5E3"},
                ],
                "threshold": {"line": {"color": "gray", "width": 2},
                              "thickness": 0.75, "value": cs_total},
            }
        ), row=1, col=2)
        fig_gauges.add_trace(go.Indicator(
            mode="gauge+number",
            value=rsi_num,
            title={"text": "RSI (14)"},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar":  {"color": rsi_color, "thickness": 0.25},
                "steps": [
                    {"range": [0, 30],  "color": "#D5F5E3"},
                    {"range": [30, 70], "color": "#EBF5FB"},
                    {"range": [70, 100],"color": "#FADBD8"},
                ],
                "threshold": {"line": {"color": "gray", "width": 2},
                              "thickness": 0.75, "value": rsi_num},
            }
        ), row=1, col=3)
        fig_gauges.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10),
                                  paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_gauges, use_container_width=True)

        # ── CAN SLIM 점수카드 ──────────────────────────────────────────────
        if cs and 'C' in cs:
            _cs_meta = {
                'C': 'Current EPS (분기 성장)',
                'A': 'Annual EPS (ROE)',
                'N': 'New High (신고가)',
                'S': 'Supply/Demand (수급)',
                'L': 'Leader (상대강도)',
                'I': 'Institutional (기관)',
                'M': 'Market (시장 방향)',
            }
            ok_cnt = sum(1 for k in 'CANSLIM' if k in cs and isinstance(cs[k], tuple) and cs[k][0] > 0)
            with st.expander(
                f"📈 CAN SLIM 점수카드  — {ok_cnt}/7 충족  |  {cs_total}점 ({cs_grade})",
                expanded=True
            ):
                rows_data = []
                for k in 'CANSLIM':
                    if k not in cs or not isinstance(cs[k], tuple):
                        continue
                    sc, val, _ = cs[k]
                    icon = "✅" if sc > 0 else "❌" if sc < 0 else "➖"
                    rows_data.append({
                        "팩터":   f"{icon} **{k}**",
                        "항목":   _cs_meta[k],
                        "값":     val,
                        "점수":   f"{sc:+d}",
                    })
                import pandas as _pd
                st.dataframe(
                    _pd.DataFrame(rows_data),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "팩터": st.column_config.TextColumn(width="small"),
                        "점수": st.column_config.TextColumn(width="small"),
                    }
                )

        cur  = investment_data['current_price']
        risk = cur - investment_data['stop_loss']
        rwd1 = investment_data['target1'] - cur
        rwd2 = investment_data['target2'] - cur
        rr1  = rwd1 / risk if risk > 0 else 0
        rr2  = rwd2 / risk if risk > 0 else 0

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("🛡️ 손절가 (ATR×1.5)",
                   f"${investment_data['stop_loss']:.2f}",
                   f"-{risk/cur*100:.1f}%", delta_color="inverse")
        mc2.metric("🎯 1차 익절 (ATR×2.0)",
                   f"${investment_data['target1']:.2f}",
                   f"+{rwd1/cur*100:.1f}%  ·  1:{rr1:.1f}")
        mc3.metric("🚀 2차 익절 (ATR×3.5)",
                   f"${investment_data['target2']:.2f}",
                   f"+{rwd2/cur*100:.1f}%  ·  1:{rr2:.1f}")
        rr_label = "✅ 진입 승인 (R/R ≥ 1:2)" if rr1 >= 2 else "⛔ 진입 보류 (R/R < 1:2)"
        st.caption(f"1차 손익비 기준: {rr_label}")

        # OI 히트맵 — 전체 너비
        oi_data = investment_data.get('oi_heatmap')
        if oi_data and oi_data.get('strikes'):
            st.markdown("##### 📊 옵션 OI 분포 (현재가 ±25%)")
            fig_oi = go.Figure()
            fig_oi.add_trace(go.Bar(x=oi_data['strikes'], y=oi_data['calls'],
                                    name='Call OI', marker_color='rgba(46,204,113,0.7)'))
            fig_oi.add_trace(go.Bar(x=oi_data['strikes'], y=oi_data['puts'],
                                    name='Put OI', marker_color='rgba(231,76,60,0.7)'))
            fig_oi.add_vline(x=cur, line_dash="dash", line_color="#3498DB",
                             annotation_text=f"현재가 ${cur:.2f}",
                             annotation_position="top left")
            if oi_data.get('max_pain'):
                fig_oi.add_vline(x=oi_data['max_pain'], line_dash="dot", line_color="orange",
                                 annotation_text=f"Max Pain ${oi_data['max_pain']:.2f}",
                                 annotation_position="top right")
            fig_oi.update_layout(barmode='group', height=260,
                                  margin=dict(l=0, r=0, t=35, b=0),
                                  legend=dict(orientation='h', yanchor='bottom', y=1.02))
            st.plotly_chart(fig_oi, use_container_width=True)

        st.divider()

        # ── 차트(60%) + 리포트(40%) 나란히 — 모바일에서 CSS로 세로 스택 ──
        chart_col, report_col = st.columns([6, 4])

        with chart_col:
            # .price-chart 클래스 div로 감싸 CSS 모바일 높이 타깃팅
            st.markdown('<div class="price-chart">', unsafe_allow_html=True)
            df_chart = investment_data['chart_data'].tail(120)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                vertical_spacing=0.03, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(
                x=df_chart.index, open=df_chart['Open'], high=df_chart['High'],
                low=df_chart['Low'], close=df_chart['Close'], name='Price'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA20'],
                                     line=dict(color='orange', width=1.5), name='20일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA60'],
                                     line=dict(color='green', width=1.5), name='60일선'), row=1, col=1)
            fig.add_trace(go.Bar(x=df_chart.index, y=df_chart['Volume'],
                                 name='Volume', marker_color='rgba(100,150,250,0.5)'), row=2, col=1)
            fig.update_layout(title=f"{TARGET_TICKER} 최근 6개월",
                              xaxis_rangeslider_visible=False,
                              height=500, margin=dict(l=0, r=0, t=40, b=0))
            fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with report_col:
            with st.container(border=True):
                st.markdown(final_report)

            with st.expander("🔍 옵션 데이터 수집 확인 (AI에 전달된 원본값)"):
                st.markdown("**1차 만기 PCR:**")
                st.code(investment_data.get('options', 'KEY_MISSING'))
                st.markdown("**만기별 PCR (3개):**")
                st.code(investment_data.get('options_pcr_multi', 'KEY_MISSING'))
                mp = investment_data.get('max_pain')
                st.markdown(f"**Max Pain:** {'${:.2f}'.format(mp) if mp else '산출 불가 (None)'}")
                hm = investment_data.get('oi_heatmap')
                st.markdown(f"**OI 히트맵 데이터:** {'행사가 {}개 로드됨'.format(len(hm['strikes'])) if hm else '없음'}")
                st.caption("에러 메시지가 표시되면 해당 종목의 옵션 체인이 yfinance에서 조회 불가인 것입니다.")

    except Exception as e:
        st.error(f"실행 중 오류가 발생했습니다: {e}")
