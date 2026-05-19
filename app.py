import plotly.graph_objects as go
from plotly.subplots import make_subplots

import streamlit as st

# 분리된 모듈 임포트
from database import init_db, save_to_sqlite, save_to_notion
from data_fetcher import prepare_investment_data
from ai_generator import generate_investment_report

# ---------------------------------------------------------
# 1. 페이지 설정 및 UI 숨기기
# ---------------------------------------------------------
st.set_page_config(page_title="AI 투자 위원회", layout="centered")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 헤더 크기 및 본문 최적화 */
    h1 { font-size: 24px !important; font-weight: 700 !important; margin-bottom: 10px !important; }
    h2 { font-size: 20px !important; font-weight: 700 !important; margin-top: 20px !important; }
    h3 { font-size: 17px !important; font-weight: 700 !important; }
    .stMarkdown p, .stMarkdown li {
        font-size: 15px !important;
        line-height: 1.7 !important;
        letter-spacing: -0.01em !important;
    }
    strong { font-weight: 600 !important; color: #1E1E1E; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. 초기 세팅 (DB 생성)
# ---------------------------------------------------------
init_db()

# ---------------------------------------------------------
# 3. 웹 메인 화면 (UI 구성)
# ---------------------------------------------------------
st.title("🏛️ AI 투자 위원회 분석 시스템")
st.markdown("객관적 지표와 행동 심리 분석을 통해 **오늘의 BUY / HOLD / SELL 전략**을 확인하세요.")

st.divider()

# 사용자 입력 폼
with st.form("analysis_form"):
    TARGET_TICKER = st.text_input("▶️ 분석할 기업의 티커 (예: TSLA, AAPL)", value="TSLA")
    
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
# 4. 폼 제출 시 실행 로직
# ---------------------------------------------------------
if submitted:
    TARGET_TICKER = TARGET_TICKER.strip().upper() if TARGET_TICKER else "TSLA"
    
    if "보유 중" in position:
        MY_CONTEXT = f"현재 주식을 보유 중(평단가: ${avg_price:.2f}, 비중: {weight}%)입니다. \n나의 오늘 매매 계획은 '{action_plan}' 입니다."
    else: 
        MY_CONTEXT = f"현재 주식을 보유하고 있지 않습니다. \n나의 오늘 매매 계획은 '{action_plan}' 입니다."
        
    MY_FEEDBACK = psycho_state
    
    if vix_input > 0 or fg_input > 0:
        macro_text = f"\n\n[🌐 거시 시장 심리 데이터]\n"
        if vix_input > 0: macro_text += f"- VIX 지수: {vix_input}\n"
        if fg_input > 0: macro_text += f"- CNN 공포탐욕지수: {fg_input}\n"
        MY_CONTEXT += macro_text
        MY_FEEDBACK += " \n**(특별 지시: 전문가 C는 방금 제공된 '거시 시장 심리 데이터'의 수치와 나의 '현재 심리/매매 계획'을 직접적으로 비교 분석하여, 내가 군중 심리에 휩쓸린 것인지 역발상 투자인지 날카롭게 비판해 주세요.)**"

    try:
        with st.spinner(f"[{TARGET_TICKER}] 데이터를 분석하고 위원회 토론을 진행 중입니다..."):
            # 1. 데이터 수집
            investment_data = prepare_investment_data(TARGET_TICKER, MY_CONTEXT, MY_FEEDBACK)
            
            # 2. AI 리포트 생성
            final_report = generate_investment_report(investment_data)
            
            # 3. DB 및 Notion 저장
            save_to_sqlite(TARGET_TICKER, investment_data['current_price'], vix_input, fg_input, position, action_plan, psycho_state, final_report)
            notion_success, notion_msg = save_to_notion(TARGET_TICKER, investment_data['current_price'], vix_input, fg_input, psycho_state, action_plan, final_report)
        
        # 4. 결과 출력
        st.success("분석이 완료되었습니다!")
        if notion_success:
            st.info("✅ 노션 매매일지에 리포트가 성공적으로 백업되었습니다.")
        else:
            st.warning(f"⚠️ 노션 백업 건너뜀 (사유: {notion_msg}) - 먼저 secrets.toml을 설정해주세요.")

        # 🚀 [여기서부터 새로 추가된 차트 그리기 로직]
        df_chart = investment_data['chart_data'].tail(120) # 최근 120일(약 6개월) 데이터만 표시
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
        
        # 1. 캔들 차트
        fig.add_trace(go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], 
                                     low=df_chart['Low'], close=df_chart['Close'], name='Price'), row=1, col=1)
        # 2. 이동평균선 추가 (20일, 60일)
        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA20'], line=dict(color='orange', width=1.5), name='20일선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA60'], line=dict(color='green', width=1.5), name='60일선'), row=1, col=1)
        
        # 3. 거래량 바 차트
        fig.add_trace(go.Bar(x=df_chart.index, y=df_chart['Volume'], name='Volume', marker_color='rgba(100, 150, 250, 0.5)'), row=2, col=1)
        
        fig.update_layout(title=f"{TARGET_TICKER} 최근 6개월 차트 및 거래량", xaxis_rangeslider_visible=False, height=500, margin=dict(l=0, r=0, t=40, b=0))

        # 🚀 [여기 한 줄을 추가해 주세요!] 주말(토요일~월요일 새벽) 구간을 차트에서 숨김
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        
        # 차트를 스트림릿 화면에 출력
        st.plotly_chart(fig, use_container_width=True)
        # 🚀 [차트 그리기 로직 끝]
       
        st.divider()
        with st.container(border=True):
            st.markdown(final_report)
            
    except Exception as e:
        st.error(f"실행 중 오류가 발생했습니다: {e}")