"""
텔레그램 매수 신호 알림 모듈

텔레그램 봇 설정 방법:
1. 텔레그램 앱에서 @BotFather 검색
2. /newbot 명령어 입력 → 봇 이름과 username 설정
3. BotFather가 발급한 BOT_TOKEN을 secrets.toml의 TELEGRAM_BOT_TOKEN에 입력
4. 새 봇과 대화 시작 (봇 username 검색 → Start 버튼 클릭)
5. 브라우저에서 https://api.telegram.org/bot{BOT_TOKEN}/getUpdates 접속
6. "chat" → "id" 값을 secrets.toml의 TELEGRAM_CHAT_ID에 입력
"""

import datetime
import requests
import streamlit as st
from zoneinfo import ZoneInfo


def _is_market_window() -> bool:
    """장 시작 30분 전(09:00 ET) ~ 장 마감(16:00 ET), 평일만 허용."""
    et_now = datetime.datetime.now(ZoneInfo("America/New_York"))
    et_min = et_now.hour * 60 + et_now.minute
    return et_now.weekday() < 5 and 540 <= et_min < 960  # 09:00~16:00


def _send_message(text: str) -> bool:
    """텔레그램 메시지 전송."""
    try:
        token   = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        res = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        return res.status_code == 200
    except Exception:
        return False


def _is_notified_recently(ticker: str) -> bool:
    """session_state로 24시간 내 동일 종목 중복 알림 여부 확인."""
    last = st.session_state.get(f"_tg_notified_{ticker}")
    if last is None:
        return False
    return (datetime.datetime.now() - last).total_seconds() < 86400


def _mark_notified(ticker: str):
    st.session_state[f"_tg_notified_{ticker}"] = datetime.datetime.now()


def check_and_notify_favorites(favorites_data: list):
    """
    즐겨찾기 스캔 결과를 받아 GREEN 종목에 텔레그램 알림 발송.

    favorites_data 항목 형식:
        {
            'ticker':      str,
            'price':       float,
            'entry_score': int,
            'entry_grade': str,   # 'GREEN' | 'YELLOW' | 'RED'
            'rsi':         float,
            'stop_loss':   float,
            'target1':     float,
        }

    - GREEN(75점↑) 종목만 알림 발송
    - 동일 종목은 24시간 내 재발송 방지 (session_state 기반)
    - TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID가 없으면 조용히 스킵
    """
    try:
        st.secrets["TELEGRAM_BOT_TOKEN"]
        st.secrets["TELEGRAM_CHAT_ID"]
    except KeyError:
        return

    if not _is_market_window():
        return

    for item in favorites_data:
        if item.get("entry_grade") != "GREEN":
            continue
        ticker = item["ticker"]
        if _is_notified_recently(ticker):
            continue

        rsi_val   = item.get("rsi", 0)
        rsi_label = " (과매도)" if rsi_val <= 30 else ""
        msg = (
            f"🟢 [{ticker}] 매수 신호 포착!\n"
            f"진입점수: {item['entry_score']}점 (GREEN)\n"
            f"현재가: ${item['price']:.2f}\n"
            f"RSI: {rsi_val:.1f}{rsi_label}\n"
            f"손절가: ${item['stop_loss']:.2f} / 목표가: ${item['target1']:.2f}"
        )

        if _send_message(msg):
            _mark_notified(ticker)
