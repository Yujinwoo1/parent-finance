import re
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from database import (init_db, save_to_sqlite, save_to_notion,
                      save_favorite, get_favorites, remove_favorite, get_audit_stats)
from data_fetcher import prepare_investment_data
from ai_generator import generate_investment_report

# ---------------------------------------------------------
# 1. 페이지 설정 및 스타일
# ---------------------------------------------------------
st.set_page_config(page_title="AI 투자 위원회", layout="centered")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    h1 { font-size: 24px !important; font-weight: 700 !important; margin-bottom: 10px !important; }
    h2 { font-size: 20px !important; font-weight: 700 !important; margin-top: 20px !important; }
    h3 { font-size: 17px !important; font-weight: 700 !important; }
    .stMarkdown p, .stMarkdown li {
        font-size: 15px !important;
        line-height: 1.7 !important;
        letter-spacing: -0.01em !important;
    }
    strong { font-weight: 600 !important; color: #1E1E1E; }
    /* 모바일 최적화 */
    @media (max-width: 640px) {
        .main .block-container { padding: 0.8rem 0.6rem !important; max-width: 100% !important; }
        div[role="radiogroup"] { flex-direction: column !important; gap: 6px !important; }
        div[role="radiogroup"] label { white-space: normal !important; line-height: 1.5 !important; }
        h1 { font-size: 20px !important; }
        .stButton > button { min-height: 2.5rem !important; }
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. 초기화
# ---------------------------------------------------------
init_db()

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
# 3. 사이드바: 즐겨찾기 + 예측 적중률
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### ⭐ 즐겨찾기")
    favorites = get_favorites()
    if not favorites:
        st.caption("분석 후 종목을 추가해보세요.")
    for fav in favorites:
        c1, c2 = st.columns([5, 1])
        with c1:
            if st.button(fav, key=f"fav_{fav}", use_container_width=True):
                st.session_state['ticker_input'] = fav
                st.rerun()
        with c2:
            if st.button("✕", key=f"del_{fav}"):
                remove_favorite(fav)
                st.rerun()

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
        if total > 0:
            st.progress(stats['A'] / total, text=f"A 누적 승률 {a_pct:.0f}%")

# ---------------------------------------------------------
# 4. 메인 화면
# ---------------------------------------------------------
st.title("🏛️ AI 투자 위원회 분석 시스템")
st.markdown("객관적 지표와 행동 심리 분석을 통해 **오늘의 BUY / HOLD / SELL 전략**을 확인하세요.")
st.divider()

with st.form("analysis_form"):
    TARGET_TICKER = st.text_input(
        "▶️ 분석할 기업의 티커 (예: TSLA, AAPL)",
        key='ticker_input'
    )

    st.markdown("### 💼 나의 포트폴리오 상태")
    position = st.radio(
        "현재 포지션이 어떻게 되시나요?",
        ["✅ 이미 보유 중 (추매/매도 고민)", "👀 미보유 (신규 진입 대기)"],
        horizontal=True
    )

    col1, col2 = st.columns(2)
    with col1:
        avg_price = st.number_input("내 평단가 ($) - 미보유시 0", min_value=0.0, value=0.0, step=10.0)
    with col2:
        weight = st.slider("포트폴리오 내 비중 (%)", 0, 100, 10)

    st.markdown("### 🎯 오늘 나의 매매 계획 (충동)")
    action_plan = st.radio(
        "솔직히 지금 당장 어떻게 하고 싶으신가요?",
        ["🛒 당장 매수하고 싶다 (신규진입/추매)", "🛑 당장 매도하고 싶다 (익절/손절)", "🧘 그냥 가만히 있고 싶다 (관망/홀딩)"],
        horizontal=True
    )

    st.markdown("### 🧠 현재 나의 심리 상태")
    psycho_state = st.selectbox(
        "가장 가까운 속마음을 골라주세요:",
        [
            "수익 중인데 언제 떨어질지 몰라 초조함 (익절 타이밍 고민)",
            "손실 중이라 불안하고 본전이 오면 팔고 싶음 (손실 회피)",
            "주가가 너무 올라서 지금 안 사면 벼락거지 될 것 같음 (FOMO)",
            "크게 물려있지만 언젠가 오를 거라 믿고 어플 삭제함 (비자발적 장기투자)",
            "원칙에 따라 기계적으로 분할 매수/매도 접근 중 (이성적 상태)",
            "아직 별생각 없음 (단순 관망)"
        ]
    )

    with st.expander("📊 [선택 사항] 오늘의 거시 시장 심리 지수 입력"):
        st.info("매일 쓰지 않는다면 비워두셔도 됩니다. 수치를 입력하면 '전문가 C'가 군중 심리와 나의 심리를 비교하는 정밀 분석을 추가합니다.")
        macro_col1, macro_col2 = st.columns(2)
        with macro_col1:
            vix_input = st.number_input("VIX 변동성 지수 (입력 시에만 분석)", min_value=0.0, value=0.0, step=1.0)
        with macro_col2:
            fg_input = st.number_input("CNN 공포탐욕지수 (0~100)", min_value=0, max_value=100, value=0, step=1)

    submitted = st.form_submit_button("🚀 나의 매매 계획 진단받기", use_container_width=True)

# ---------------------------------------------------------
# 5. 제출 후 실행 로직
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

            save_to_sqlite(TARGET_TICKER, investment_data['current_price'],
                           vix_input, fg_input, position, action_plan, psycho_state,
                           final_report, audit_winner)
            notion_success, notion_msg = save_to_notion(
                TARGET_TICKER, investment_data['current_price'],
                vix_input, fg_input, psycho_state, action_plan, final_report
            )

        st.success("분석이 완료되었습니다!")
        if notion_success:
            st.info("✅ 노션 매매일지에 리포트가 성공적으로 백업되었습니다.")
        else:
            st.warning(f"⚠️ 노션 백업 건너뜀 (사유: {notion_msg})")

        # 즐겨찾기 추가
        current_favs = get_favorites()
        if TARGET_TICKER not in current_favs:
            if st.button(f"⭐ {TARGET_TICKER} 즐겨찾기에 추가", use_container_width=False):
                save_favorite(TARGET_TICKER)
                st.rerun()

        # ── 빠른 진단 시각화 ──────────────────────────────────
        st.markdown("### 📊 빠른 진단")

        # 진입 점수 + RSI 게이지 (나란히)
        entry_color = "#2ECC71" if investment_data['entry_grade'] == "GREEN" \
                 else "#E74C3C" if investment_data['entry_grade'] == "RED" \
                 else "#F39C12"

        rsi_num   = float(investment_data['rsi'].split('(')[0].strip())
        rsi_color = "#E74C3C" if rsi_num >= 70 else "#2ECC71" if rsi_num <= 30 else "#3498DB"

        fig_gauges = make_subplots(
            rows=1, cols=2,
            specs=[[{"type": "indicator"}, {"type": "indicator"}]],
            column_widths=[0.5, 0.5]
        )
        fig_gauges.add_trace(go.Indicator(
            mode="gauge+number",
            value=investment_data['entry_score'],
            title={"text": "진입 점수"},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar":  {"color": entry_color, "thickness": 0.25},
                "steps": [
                    {"range": [0, 30],  "color": "#FADBD8"},
                    {"range": [30, 75], "color": "#FEF9E7"},
                    {"range": [75, 100],"color": "#D5F5E3"},
                ],
                "threshold": {"line": {"color": "gray", "width": 2},
                              "thickness": 0.75, "value": investment_data['entry_score']},
            }
        ), row=1, col=1)
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
        ), row=1, col=2)
        fig_gauges.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10),
                                  paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_gauges, use_container_width=True)

        # 손익비 (R/R) 메트릭
        cur   = investment_data['current_price']
        risk  = cur - investment_data['stop_loss']
        rwd1  = investment_data['target1'] - cur
        rwd2  = investment_data['target2'] - cur
        rr1   = rwd1 / risk if risk > 0 else 0
        rr2   = rwd2 / risk if risk > 0 else 0

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("🛡️ 손절가 (ATR×1.5)",
                   f"${investment_data['stop_loss']:.2f}",
                   f"-{risk/cur*100:.1f}%", delta_color="inverse")
        mc2.metric("🎯 1차 익절 (ATR×2.0)",
                   f"${investment_data['target1']:.2f}",
                   f"+{rwd1/cur*100:.1f}%  ·  손익비 1:{rr1:.1f}")
        mc3.metric("🚀 2차 익절 (ATR×3.5)",
                   f"${investment_data['target2']:.2f}",
                   f"+{rwd2/cur*100:.1f}%  ·  손익비 1:{rr2:.1f}")

        rr_label = "✅ 진입 승인 (R/R ≥ 1:2)" if rr1 >= 2 else "⛔ 진입 보류 (R/R < 1:2)"
        st.caption(f"1차 손익비 기준: {rr_label}")
        st.divider()
        # ── 시각화 끝 ─────────────────────────────────────────

        # 차트
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

        st.divider()
        with st.container(border=True):
            st.markdown(final_report)

        # 옵션 데이터 원본 확인 (수집 실패 여부 진단용)
        with st.expander("🔍 옵션 데이터 수집 확인 (AI에 전달된 원본값)"):
            st.markdown("**1차 만기 PCR:**")
            st.code(investment_data.get('options', 'KEY_MISSING'))
            st.markdown("**만기별 PCR (3개):**")
            st.code(investment_data.get('options_pcr_multi', 'KEY_MISSING'))
            mp = investment_data.get('max_pain')
            st.markdown(f"**Max Pain:** {'${:.2f}'.format(mp) if mp else '산출 불가 (None)'}")
            st.caption("'수집 불가' 표시 시 해당 종목의 옵션 데이터가 yfinance에서 조회 안 되는 것입니다.")

    except Exception as e:
        st.error(f"실행 중 오류가 발생했습니다: {e}")
