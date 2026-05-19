import streamlit as st
import yfinance as yf
import pandas as pd
from ta.trend import SMAIndicator, IchimokuIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
import fear_and_greed
from database import get_recent_report

@st.cache_data(ttl=3600)
def prepare_investment_data(ticker_symbol, portfolio_context="", trading_feedback=""):
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period="5y") 
    
    if df.empty:
        raise ValueError("데이터를 불러오지 못했습니다. 티커명을 확인해주세요.")

    df['MA5'] = SMAIndicator(close=df['Close'], window=5).sma_indicator()
    df['MA20'] = SMAIndicator(close=df['Close'], window=20).sma_indicator()
    df['MA60'] = SMAIndicator(close=df['Close'], window=60).sma_indicator()
    df['MA200'] = SMAIndicator(close=df['Close'], window=200).sma_indicator()
    
    df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
    stoch = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3)
    df['STOCH_K'] = stoch.stoch()
    df['STOCH_D'] = stoch.stoch_signal()

    ichi = IchimokuIndicator(high=df['High'], low=df['Low'])
    df['ISA_9'] = ichi.ichimoku_a()
    df['ISB_26'] = ichi.ichimoku_b()

    weekly_df = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'})
    weekly_df['WMA5'] = SMAIndicator(close=weekly_df['Close'], window=5).sma_indicator()
    weekly_df['WMA20'] = SMAIndicator(close=weekly_df['Close'], window=20).sma_indicator()
    weekly_df['WMA60'] = SMAIndicator(close=weekly_df['Close'], window=60).sma_indicator()

    latest = df.iloc[-1]
    latest_weekly = weekly_df.iloc[-1]
    last_date_str = df.index[-1].strftime('%Y-%m-%d')
    close_price = latest['Close']

    recent_csv_str = df.tail(100)[['Open', 'High', 'Low', 'Close', 'Volume']].to_csv(date_format='%Y-%m-%d')

    rsi_val = latest.get('RSI', 50)
    rsi_status = "과매수" if pd.notna(rsi_val) and rsi_val >= 70 else "과매도" if pd.notna(rsi_val) and rsi_val <= 30 else "중립"
    stoch_k = latest.get('STOCH_K', 50)
    stoch_d = latest.get('STOCH_D', 50)
    stoch_status = "골든크로스" if pd.notna(stoch_k) and pd.notna(stoch_d) and stoch_k > stoch_d else "데드크로스"

    span_a, span_b = latest.get('ISA_9', 0), latest.get('ISB_26', 0)
    if pd.notna(span_a) and pd.notna(span_b):
        ichi_status = "상승 추세(구름대 위)" if close_price > max(span_a, span_b) else "하락 추세(구름대 아래)" if close_price < min(span_a, span_b) else "혼조세(구름대 내부)"
    else:
        ichi_status = "산출 불가"

    try:
        expirations = ticker.options
        if expirations:
            opt = ticker.option_chain(expirations[0])
            pcr = opt.puts['openInterest'].sum() / opt.calls['openInterest'].sum() if opt.calls['openInterest'].sum() > 0 else 0
            pcr_sentiment = "극단적 공포(반등 기회)" if pcr >= 1.2 else "극단적 탐욕(과열 주의)" if pcr <= 0.7 else "중립"
            options_context = f"최근 만기일 기준 Put/Call Ratio: {pcr:.2f} ({pcr_sentiment})"
        else:
            options_context = "옵션 데이터 없음"
    except:
        options_context = "수집 불가"

    try:
        vix_df = yf.Ticker("^VIX").history(period="1d")
        vix_current = vix_df['Close'].iloc[-1]
        if vix_current >= 30: vix_status = "극단적 공포 (패닉 셀링 구간)"
        elif vix_current >= 20: vix_status = "공포 (경계 구간)"
        elif vix_current <= 15: vix_status = "탐욕 (안정 및 과열 우려)"
        else: vix_status = "중립"
        vix_context = f"{vix_current:.2f} ({vix_status})"
    except:
        vix_context = "수집 불가"

    try:
        fg = fear_and_greed.get()
        fg_score = fg.value
        fg_desc = fg.description
        fg_context = f"점수: {fg_score:.1f}/100 (상태: {fg_desc})"
    except:
        fg_context = "데이터 수집 지연 (CNN 서버 불안정)"

    # 데이터베이스에서 최근 기록 가져오기
    past_memory = get_recent_report(ticker_symbol)

    return {
        'ticker': ticker_symbol, 'current_price': close_price, 'last_date': last_date_str,
        'portfolio': portfolio_context, 'feedback': trading_feedback,
        'ohlcv': f"시가 {latest['Open']:.2f} / 고가 {latest['High']:.2f} / 저가 {latest['Low']:.2f} / 종가 {close_price:.2f} / 거래량 {int(latest['Volume'])}",
        'ma': f"일봉: 5일({latest.get('MA5',0):.2f}), 20일({latest.get('MA20',0):.2f}), 60일({latest.get('MA60',0):.2f}), 200일({latest.get('MA200',0):.2f})",
        'wma': f"주봉: 5주({latest_weekly.get('WMA5',0):.2f}), 20주({latest_weekly.get('WMA20',0):.2f}), 60주({latest_weekly.get('WMA60',0):.2f})",
        'ichi': ichi_status, 'rsi': f"{rsi_val:.1f} ({rsi_status})", 'stoch': f"K: {stoch_k:.1f}, D: {stoch_d:.1f} ({stoch_status})",
        'options': options_context, 'memory': past_memory, 'recent_data': recent_csv_str ,'vix': vix_context, 'cnn_fg': fg_context,

        'chart_data': df  # <-- 🚀 [이 부분 추가] 차트 시각화를 위한 원본 데이터프레임 전달
    }