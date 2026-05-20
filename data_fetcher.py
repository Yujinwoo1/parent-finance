import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from ta.trend import SMAIndicator, IchimokuIndicator
from ta.trend import MACD as MACDIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from database import get_recent_report


def _calc_canslim_scores(info, df, close_price, week52_high, week52_low, spy_data):
    """
    CAN SLIM 7개 팩터 채점.
    반환: {'C':(score,value,desc), ..., 'total':int, 'grade':str}
    """
    f = {}

    # C — Current Quarterly Earnings (분기 EPS YoY 성장률)
    c_raw = info.get('earningsQuarterlyGrowth') or info.get('earningsGrowth')
    if c_raw is not None:
        p = c_raw * 100
        c_sc  = 15 if p >= 50 else 10 if p >= 25 else 3 if p >= 0 else -8
        c_val = f"{p:+.0f}% (YoY)"
    else:
        c_sc, c_val = 0, "N/A"
    f['C'] = (c_sc, c_val, "분기 EPS 성장률")

    # A — Annual Earnings / ROE
    roe = info.get('returnOnEquity')
    if roe is not None:
        p = roe * 100
        a_sc  = 12 if p >= 25 else 8 if p >= 17 else 3 if p >= 10 else -3
        a_val = f"ROE {p:.1f}%"
    else:
        a_sc, a_val = 0, "N/A"
    f['A'] = (a_sc, a_val, "자기자본이익률(ROE)")

    # N — New High Breakout + Volume
    latest    = df.iloc[-1]
    vol_avg_v = df['VOL_AVG20'].iloc[-1] if 'VOL_AVG20' in df.columns else float('nan')
    vol_r     = latest['Volume'] / float(vol_avg_v) if pd.notna(vol_avg_v) and float(vol_avg_v) > 0 else 1.0
    pct_hi    = close_price / week52_high * 100
    if pct_hi >= 98 and vol_r >= 1.4:
        n_sc = 14; n_val = f"신고가 돌파 (거래량 {vol_r:.1f}×)"
    elif pct_hi >= 95:
        n_sc = 5;  n_val = f"신고가 근접 ({pct_hi:.0f}%)"
    elif pct_hi <= 65:
        n_sc = -5; n_val = f"저점권 ({pct_hi:.0f}%)"
    else:
        n_sc = 0;  n_val = f"중간대 ({pct_hi:.0f}%)"
    f['N'] = (n_sc, n_val, "신고가 돌파")

    # S — Supply & Demand (20일 상승/하락 거래량 비율)
    rec20  = df.tail(20)
    up_vol = rec20[rec20['Close'] >= rec20['Open']]['Volume'].sum()
    dn_vol = rec20[rec20['Close'] <  rec20['Open']]['Volume'].sum()
    ud     = up_vol / dn_vol if dn_vol > 0 else 2.0
    if ud >= 1.5:   s_sc = 10; s_val = f"매수 우위 ({ud:.1f}×)"
    elif ud >= 1.0: s_sc = 3;  s_val = f"중립 ({ud:.1f}×)"
    else:           s_sc = -6; s_val = f"매도 우위 ({ud:.1f}×)"
    f['S'] = (s_sc, s_val, "상승/하락 거래량 비율 (20일)")

    # L — Leader vs Laggard (1년 상대강도 vs SPY)
    l_sc, l_val = 0, "N/A"
    if spy_data is not None and not spy_data.empty and len(df) >= 252:
        try:
            spy_ret = (spy_data['Close'].iloc[-1] / spy_data['Close'].iloc[0] - 1) * 100
            stk_ret = (close_price / df['Close'].iloc[-252] - 1) * 100
            rs      = stk_ret - spy_ret
            if rs >= 20:    l_sc = 15; l_val = f"RS {rs:+.0f}% (시장 대폭 초과)"
            elif rs >= 5:   l_sc = 8;  l_val = f"RS {rs:+.0f}% (시장 초과)"
            elif rs >= -5:  l_sc = 2;  l_val = f"RS {rs:+.0f}% (시장 유사)"
            else:           l_sc = -8; l_val = f"RS {rs:+.0f}% (시장 미달)"
        except Exception:
            pass
    f['L'] = (l_sc, l_val, "S&P 500 대비 1년 상대강도")

    # I — Institutional Sponsorship
    inst = info.get('institutionPercentHeld') or info.get('heldPercentInstitutions')
    if inst is not None:
        p     = inst * 100
        i_sc  = 10 if p >= 60 else 6 if p >= 40 else 2 if p >= 20 else -3
        i_val = f"{p:.0f}%"
    else:
        i_sc, i_val = 0, "N/A"
    f['I'] = (i_sc, i_val, "기관 보유 비율")

    # M — Market Direction (SPY MA 추세)
    m_sc, m_val = 0, "N/A"
    if spy_data is not None and not spy_data.empty and len(spy_data) >= 50:
        try:
            spy_c    = spy_data['Close'].iloc[-1]
            spy_ma50 = spy_data['Close'].rolling(50).mean().iloc[-1]
            spy_ma200 = spy_data['Close'].rolling(200).mean().iloc[-1] if len(spy_data) >= 200 else spy_ma50 * 0.995
            if spy_c > spy_ma50 > spy_ma200:
                m_sc = 10; m_val = "강세장 (SPY 정배열)"
            elif spy_c > spy_ma50:
                m_sc = 4;  m_val = "중립장 (SPY MA50 위)"
            elif spy_c < spy_ma50 < spy_ma200:
                m_sc = -10; m_val = "약세장 (SPY 역배열)"
            else:
                m_sc = -3; m_val = "조정 구간"
        except Exception:
            pass
    f['M'] = (m_sc, m_val, "시장 방향성 (SPY 추세)")

    # 총점 정규화: 최악(-43) ~ 최선(+86) → 0~100, 중립 50
    raw   = sum(v[0] for v in f.values())
    total = max(0, min(100, int(50 + raw * 0.58)))
    grade = "GREEN" if total >= 65 else "RED" if total < 35 else "YELLOW"
    f['total'] = total
    f['grade'] = grade
    return f


def _get_fear_greed():
    """CNN Fear & Greed Index — 라이브러리 없이 직접 HTTP 요청."""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/previous-close"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        fg = resp.json()["fear_and_greed"]
        return f"점수: {fg['score']:.1f}/100 (상태: {fg['rating']})"
    except Exception:
        return "데이터 수집 불가"


@st.cache_data(ttl=3600)
def _fetch_ticker_data(ticker_symbol):
    """
    시장 데이터 수집 및 지표 계산.
    ticker_symbol만 캐시 키 — portfolio_context·trading_feedback는 여기 포함하지 않음.
    """
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period="5y")

    if df.empty:
        raise ValueError("데이터를 불러오지 못했습니다. 티커명을 확인해주세요.")

    # --- Moving Averages ---
    df['MA5']   = SMAIndicator(close=df['Close'], window=5).sma_indicator()
    df['MA20']  = SMAIndicator(close=df['Close'], window=20).sma_indicator()
    df['MA50']  = SMAIndicator(close=df['Close'], window=50).sma_indicator()
    df['MA60']  = SMAIndicator(close=df['Close'], window=60).sma_indicator()
    df['MA200'] = SMAIndicator(close=df['Close'], window=200).sma_indicator()

    # --- Momentum ---
    df['RSI']     = RSIIndicator(close=df['Close'], window=14).rsi()
    stoch         = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3)
    df['STOCH_K'] = stoch.stoch()
    df['STOCH_D'] = stoch.stoch_signal()

    # --- Ichimoku ---
    ichi          = IchimokuIndicator(high=df['High'], low=df['Low'])
    df['ISA_9']   = ichi.ichimoku_a()
    df['ISB_26']  = ichi.ichimoku_b()

    # --- Volatility ---
    atr_ind         = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
    df['ATR']       = atr_ind.average_true_range()
    df['ATR_AVG20'] = df['ATR'].rolling(20).mean()
    bb              = BollingerBands(close=df['Close'], window=20, window_dev=2)
    df['BB_lower']  = bb.bollinger_lband()
    df['BB_upper']  = bb.bollinger_hband()

    # --- MACD ---
    macd_ind               = MACDIndicator(close=df['Close'])
    df['MACD_line']        = macd_ind.macd()
    df['MACD_signal_line'] = macd_ind.macd_signal()

    df['VOL_AVG20'] = df['Volume'].rolling(20).mean()

    # --- Weekly ---
    weekly_df = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'})
    weekly_df['WMA5']  = SMAIndicator(close=weekly_df['Close'], window=5).sma_indicator()
    weekly_df['WMA20'] = SMAIndicator(close=weekly_df['Close'], window=20).sma_indicator()
    weekly_df['WMA60'] = SMAIndicator(close=weekly_df['Close'], window=60).sma_indicator()

    latest        = df.iloc[-1]
    prev          = df.iloc[-2]
    latest_weekly = weekly_df.iloc[-1]
    last_date_str = df.index[-1].strftime('%Y-%m-%d')
    close_price   = latest['Close']

    recent_csv_str = df.tail(100)[['Open', 'High', 'Low', 'Close', 'Volume']].to_csv(date_format='%Y-%m-%d')

    rsi_val      = latest.get('RSI', 50)
    rsi_status   = "과매수" if pd.notna(rsi_val) and rsi_val >= 70 else "과매도" if pd.notna(rsi_val) and rsi_val <= 30 else "중립"
    stoch_k      = latest.get('STOCH_K', 50)
    stoch_d      = latest.get('STOCH_D', 50)
    stoch_status = "골든크로스" if pd.notna(stoch_k) and pd.notna(stoch_d) and stoch_k > stoch_d else "데드크로스"

    span_a, span_b = latest.get('ISA_9', 0), latest.get('ISB_26', 0)
    if pd.notna(span_a) and pd.notna(span_b):
        ichi_status = "상승 추세(구름대 위)" if close_price > max(span_a, span_b) else "하락 추세(구름대 아래)" if close_price < min(span_a, span_b) else "혼조세(구름대 내부)"
    else:
        ichi_status = "산출 불가"

    # --- Options: multi-expiry PCR + Max Pain + OI Heatmap ---
    oi_heatmap = None
    try:
        expirations = ticker.options
        pcr_list, opt0 = [], None
        for i, exp in enumerate(expirations[:3]):
            opt = ticker.option_chain(exp)
            if i == 0:
                opt0 = opt
            calls_oi = opt.calls['openInterest'].fillna(0).sum()
            puts_oi  = opt.puts['openInterest'].fillna(0).sum()
            pcr      = puts_oi / calls_oi if calls_oi > 0 else 0
            sentiment = "극단적 공포" if pcr >= 1.2 else "극단적 탐욕" if pcr <= 0.7 else "중립"
            pcr_list.append(f"{exp}: PCR {pcr:.2f} ({sentiment})")

        options_pcr_multi = "\n".join(pcr_list) if pcr_list else "데이터 없음"

        if opt0 is not None:
            pcr0   = opt0.puts['openInterest'].fillna(0).sum() / opt0.calls['openInterest'].fillna(0).sum() if opt0.calls['openInterest'].fillna(0).sum() > 0 else 0
            pcr0_s = "극단적 공포(반등 기회)" if pcr0 >= 1.2 else "극단적 탐욕(과열 주의)" if pcr0 <= 0.7 else "중립"
            options_context = f"최근 만기일 기준 Put/Call Ratio: {pcr0:.2f} ({pcr0_s})"

            calls_df = opt0.calls[['strike', 'openInterest']].fillna(0)
            puts_df  = opt0.puts[['strike', 'openInterest']].fillna(0)
            strikes  = sorted(set(calls_df['strike'].tolist() + puts_df['strike'].tolist()))
            min_pain, max_pain_price = float('inf'), close_price
            for s in strikes:
                cp = ((s - calls_df['strike']).clip(lower=0) * calls_df['openInterest']).sum()
                pp = ((puts_df['strike'] - s).clip(lower=0) * puts_df['openInterest']).sum()
                if cp + pp < min_pain:
                    min_pain, max_pain_price = cp + pp, s
            max_pain = round(float(max_pain_price), 2)

            # OI 히트맵: 현재가 ±25% 범위 내 행사가만 추출
            lo, hi   = close_price * 0.75, close_price * 1.25
            hm_c     = calls_df[(calls_df['strike'] >= lo) & (calls_df['strike'] <= hi)]
            hm_p     = puts_df[(puts_df['strike']  >= lo) & (puts_df['strike']  <= hi)]
            hm_stk   = sorted(set(hm_c['strike'].tolist() + hm_p['strike'].tolist()))
            if hm_stk:
                oi_heatmap = {
                    'strikes':  hm_stk,
                    'calls':    [float(hm_c[hm_c['strike'] == s]['openInterest'].sum()) for s in hm_stk],
                    'puts':     [float(hm_p[hm_p['strike'] == s]['openInterest'].sum()) for s in hm_stk],
                    'max_pain': max_pain,
                }
        else:
            options_context, max_pain = "옵션 데이터 없음", None
    except Exception as e:
        options_context  = f"수집 불가 ({type(e).__name__}: {str(e)[:80]})"
        options_pcr_multi = "수집 불가"
        max_pain          = None

    # --- VIX ---
    try:
        vix_current = yf.Ticker("^VIX").history(period="1d")['Close'].iloc[-1]
        if vix_current >= 30:   vix_status = "극단적 공포 (패닉 셀링 구간)"
        elif vix_current >= 20: vix_status = "공포 (경계 구간)"
        elif vix_current <= 15: vix_status = "탐욕 (안정 및 과열 우려)"
        else:                   vix_status = "중립"
        vix_context = f"{vix_current:.2f} ({vix_status})"
    except Exception:
        vix_context = "수집 불가"

    fg_context = _get_fear_greed()

    # --- 52-Week Position ---
    week52_high = float(df['Close'].tail(252).max())
    week52_low  = float(df['Close'].tail(252).min())
    w52_range   = week52_high - week52_low
    w52_pos     = round((close_price - week52_low) / w52_range * 100, 1) if w52_range > 0 else 50.0
    week52 = {'high': round(week52_high, 2), 'low': round(week52_low, 2), 'position_pct': w52_pos}

    # --- ATR Stop-Loss / Targets ---
    atr_v     = float(latest['ATR']) if pd.notna(latest.get('ATR')) else 0.0
    stop_loss = round(close_price - atr_v * 1.5, 2)
    target1   = round(close_price + atr_v * 2.0, 2)
    target2   = round(close_price + atr_v * 3.5, 2)

    # --- Entry Score (0–100) ---
    score = 50
    rsi_f = float(rsi_val) if pd.notna(rsi_val) else 50.0

    # RSI — 8단계 (과매도↑ / 과매수↓)
    if   rsi_f < 25:  score += 20
    elif rsi_f < 30:  score += 15
    elif rsi_f < 40:  score += 8
    elif rsi_f < 50:  score += 3
    elif rsi_f < 60:  score += 0
    elif rsi_f < 70:  score -= 5
    elif rsi_f < 80:  score -= 12
    else:             score -= 18

    # 볼린저 밴드 — 하단 가산 + 상단 감산
    bb_lower_v = latest.get('BB_lower', float('nan'))
    bb_upper_v = latest.get('BB_upper', float('nan'))
    if pd.notna(bb_lower_v) and pd.notna(bb_upper_v):
        bb_l, bb_h = float(bb_lower_v), float(bb_upper_v)
        if   close_price <= bb_l:         score += 12
        elif close_price <= bb_l * 1.015: score += 6
        elif close_price >= bb_h:         score -= 8
        elif close_price >= bb_h * 0.99:  score -= 4

    # MA 정배열/역배열 — 확장 범위 (+15 / -18)
    ma50_v  = latest.get('MA50',  float('nan'))
    ma200_v = latest.get('MA200', float('nan'))
    ma_full_up = False
    ma_full_dn = False
    if pd.notna(ma50_v) and pd.notna(ma200_v):
        ma50, ma200 = float(ma50_v), float(ma200_v)
        if   close_price > ma50 > ma200:  score += 15; ma_full_up = True
        elif close_price > ma50:          score += 6
        elif close_price < ma50 < ma200:  score -= 18; ma_full_dn = True
        else:                             score -= 6

    # MACD — 골든크로스 +10 / 네거티브 -6
    macd_c = latest.get('MACD_line',        float('nan'))
    sig_c  = latest.get('MACD_signal_line', float('nan'))
    macd_p = prev.get('MACD_line',          float('nan'))
    sig_p  = prev.get('MACD_signal_line',   float('nan'))
    macd_above = False
    macd_just_crossed = False
    if all(pd.notna(v) for v in [macd_c, sig_c, macd_p, sig_p]):
        mc, sc_v, mp, sp = float(macd_c), float(sig_c), float(macd_p), float(sig_p)
        macd_just_crossed = mc >= sc_v and mp < sp
        gap_macd  = sc_v - mc
        imminent  = mc < sc_v and 0 < gap_macd < abs(close_price * 0.003) and mc > mp
        macd_above = mc > sc_v
        if macd_just_crossed:   score += 10
        elif imminent:          score += 8
        elif macd_above:        score += 5
        else:                   score -= 6
        # 데드크로스 구간의 MACD 반등은 품질 할인
        if ma_full_dn and macd_just_crossed:
            score -= 6

    # 거래량 — 1.5× 중간 티어 추가
    vol_avg = latest.get('VOL_AVG20', float('nan'))
    if pd.notna(vol_avg) and float(vol_avg) > 0:
        vol_ratio = latest['Volume'] / float(vol_avg)
        if   vol_ratio >= 2.0:  score += 8
        elif vol_ratio >= 1.5:  score += 5
        elif vol_ratio >= 1.3:  score += 3

    # 52주 위치 — 저점 가산 강화 / 고점 감산 강화
    week52_low_cur = float(df['Close'].tail(252).min())
    w52_range_cur  = week52_high - week52_low_cur
    w52_pct = (close_price - week52_low_cur) / w52_range_cur * 100 if w52_range_cur > 0 else 50.0
    if   w52_pct <= 15:  score += 10
    elif w52_pct <= 30:  score += 5
    elif w52_pct >= 90:  score -= 8

    # ATR 저변동 안정성 보너스
    atr_cur   = latest.get('ATR',       float('nan'))
    atr_avg20 = latest.get('ATR_AVG20', float('nan'))
    if ma_full_up and pd.notna(atr_cur) and pd.notna(atr_avg20) and float(atr_cur) < float(atr_avg20):
        score += 5

    # 갭 상승 패널티 (5% 이상 갭업)
    prev_close = float(prev['Close'])
    if prev_close > 0 and (close_price - prev_close) / prev_close >= 0.05:
        score -= 8

    # 콤보 보너스 / 패널티
    if rsi_f <= 35 and pd.notna(bb_lower_v) and close_price <= float(bb_lower_v) * 1.015:
        score += 8   # 강한 과매도 시그널 (RSI + BB 동시)
    if rsi_f >= 70 and w52_pct >= 90:
        score -= 8   # 이중 과열 (RSI 과매수 + 52주 고점)
    if ma_full_up and macd_above and not macd_just_crossed and rsi_f < 65:
        score += 5   # 추세 품질 보너스 (정배열+MACD+비과열)

    entry_score = max(0, min(100, score))
    entry_grade = "GREEN" if entry_score >= 65 else "RED" if entry_score < 35 else "YELLOW"

    # --- CAN SLIM ---
    try:
        _info = ticker.info or {}
    except Exception:
        _info = {}
    try:
        _spy = yf.Ticker("SPY").history(period="1y")
    except Exception:
        _spy = None
    canslim = _calc_canslim_scores(_info, df, close_price, week52_high, week52_low, _spy)

    return {
        'ticker': ticker_symbol, 'current_price': close_price, 'last_date': last_date_str,
        'ohlcv': f"시가 {latest['Open']:.2f} / 고가 {latest['High']:.2f} / 저가 {latest['Low']:.2f} / 종가 {close_price:.2f} / 거래량 {int(latest['Volume'])}",
        'ma':  f"일봉: 5일({latest.get('MA5',0):.2f}), 20일({latest.get('MA20',0):.2f}), 60일({latest.get('MA60',0):.2f}), 200일({latest.get('MA200',0):.2f})",
        'wma': f"주봉: 5주({latest_weekly.get('WMA5',0):.2f}), 20주({latest_weekly.get('WMA20',0):.2f}), 60주({latest_weekly.get('WMA60',0):.2f})",
        'ichi': ichi_status, 'rsi': f"{rsi_val:.1f} ({rsi_status})", 'stoch': f"K: {stoch_k:.1f}, D: {stoch_d:.1f} ({stoch_status})",
        'options': options_context, 'recent_data': recent_csv_str,
        'vix': vix_context, 'cnn_fg': fg_context, 'chart_data': df,
        'entry_score': entry_score, 'entry_grade': entry_grade,
        'stop_loss': stop_loss, 'target1': target1, 'target2': target2,
        'week52': week52, 'options_pcr_multi': options_pcr_multi, 'max_pain': max_pain,
        'oi_heatmap': oi_heatmap,
        'canslim': canslim, 'canslim_score': canslim['total'],
    }


def _get_tradier_options(ticker_symbol, close_price, api_token):
    """Tradier API로 실시간 옵션 데이터 수집. TRADIER_TOKEN이 있을 때만 호출됨."""
    base    = "https://api.tradier.com/v1/markets/options"
    headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}

    resp       = requests.get(f"{base}/expirations", params={"symbol": ticker_symbol, "includeAllRoots": "true"}, headers=headers, timeout=10)
    expirations = resp.json().get("expirations", {}).get("date", [])
    if not expirations:
        return None

    pcr_list, opt0_calls, opt0_puts = [], None, None
    for i, exp in enumerate(expirations[:3]):
        resp    = requests.get(f"{base}/chains", params={"symbol": ticker_symbol, "expiration": exp, "greeks": "false"}, headers=headers, timeout=10)
        options = resp.json().get("options", {}).get("option", [])
        if not options:
            continue
        calls_oi = sum((o.get("open_interest") or 0) for o in options if o.get("option_type") == "call")
        puts_oi  = sum((o.get("open_interest") or 0) for o in options if o.get("option_type") == "put")
        pcr      = puts_oi / calls_oi if calls_oi > 0 else 0
        sentiment = "극단적 공포" if pcr >= 1.2 else "극단적 탐욕" if pcr <= 0.7 else "중립"
        pcr_list.append(f"{exp}: PCR {pcr:.2f} ({sentiment})")
        if i == 0:
            opt0_calls = [{"strike": o["strike"], "openInterest": o.get("open_interest") or 0} for o in options if o.get("option_type") == "call"]
            opt0_puts  = [{"strike": o["strike"], "openInterest": o.get("open_interest") or 0} for o in options if o.get("option_type") == "put"]

    if not pcr_list:
        return None

    options_pcr_multi = "\n".join(pcr_list)
    options_context, max_pain, oi_heatmap = "옵션 데이터 없음", None, None

    if opt0_calls and opt0_puts:
        calls_total = sum(c["openInterest"] for c in opt0_calls)
        puts_total  = sum(p["openInterest"] for p in opt0_puts)
        pcr0   = puts_total / calls_total if calls_total > 0 else 0
        pcr0_s = "극단적 공포(반등 기회)" if pcr0 >= 1.2 else "극단적 탐욕(과열 주의)" if pcr0 <= 0.7 else "중립"
        options_context = f"최근 만기일 기준 Put/Call Ratio: {pcr0:.2f} ({pcr0_s}) [Tradier 실시간]"

        calls_df = pd.DataFrame(opt0_calls)
        puts_df  = pd.DataFrame(opt0_puts)
        strikes  = sorted(set(calls_df['strike'].tolist() + puts_df['strike'].tolist()))
        min_pain, max_pain_price = float('inf'), close_price
        for s in strikes:
            cp = ((s - calls_df['strike']).clip(lower=0) * calls_df['openInterest']).sum()
            pp = ((puts_df['strike'] - s).clip(lower=0) * puts_df['openInterest']).sum()
            if cp + pp < min_pain:
                min_pain, max_pain_price = cp + pp, s
        max_pain = round(float(max_pain_price), 2)

        lo, hi  = close_price * 0.75, close_price * 1.25
        hm_c    = calls_df[(calls_df['strike'] >= lo) & (calls_df['strike'] <= hi)]
        hm_p    = puts_df[(puts_df['strike']  >= lo) & (puts_df['strike']  <= hi)]
        hm_stk  = sorted(set(hm_c['strike'].tolist() + hm_p['strike'].tolist()))
        if hm_stk:
            oi_heatmap = {
                'strikes':  hm_stk,
                'calls':    [float(hm_c[hm_c['strike'] == s]['openInterest'].sum()) for s in hm_stk],
                'puts':     [float(hm_p[hm_p['strike'] == s]['openInterest'].sum()) for s in hm_stk],
                'max_pain': max_pain,
            }

    return {'options_context': options_context, 'options_pcr_multi': options_pcr_multi,
            'max_pain': max_pain, 'oi_heatmap': oi_heatmap}


def prepare_investment_data(ticker_symbol, portfolio_context="", trading_feedback=""):
    """캐시된 시장 데이터에 사용자 컨텍스트·DB 기억을 합쳐 반환."""
    data              = _fetch_ticker_data(ticker_symbol).copy()
    data['portfolio'] = portfolio_context
    data['feedback']  = trading_feedback
    data['memory']    = get_recent_report(ticker_symbol)   # 항상 최신값

    # TRADIER_TOKEN이 있으면 옵션 데이터를 실시간으로 교체
    try:
        tradier_token = st.secrets.get("TRADIER_TOKEN")
        if tradier_token:
            td = _get_tradier_options(ticker_symbol, data['current_price'], tradier_token)
            if td:
                data['options']           = td['options_context']
                data['options_pcr_multi'] = td['options_pcr_multi']
                data['max_pain']          = td['max_pain']
                data['oi_heatmap']        = td['oi_heatmap']
    except Exception:
        pass

    return data
