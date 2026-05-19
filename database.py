import sqlite3
import requests
import datetime
import streamlit as st

def init_db():
    """SQLite 테이블 생성 (최초 1회 실행)"""
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            ticker TEXT,
            current_price REAL,
            vix REAL,
            cnn_fg INTEGER,
            position TEXT,
            action_plan TEXT,
            psycho_state TEXT,
            report TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_to_sqlite(ticker, price, vix, fg, position, action, psycho, report):
    """통계 분석용: SQLite에 정량/정성 데이터 저장"""
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO logs (date, ticker, current_price, vix, cnn_fg, position, action_plan, psycho_state, report)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (now, ticker, price, vix, fg, position, action, psycho, report))
    conn.commit()
    conn.close()


# database.py의 get_recent_report 함수 수정
def get_recent_report(ticker):
    """특정 티커의 과거 리포트 기록을 DB에서 불러옴 (최신순으로 3개까지 가져와 분석에 활용)"""
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    # 최근 3개의 기록을 가져와 추세 변화를 읽을 수 있게 함
    c.execute("SELECT date, current_price, report FROM logs WHERE ticker=? ORDER BY date DESC LIMIT 3", (ticker,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return "최근 기록된 리포트 없음."
        
    memory_text = ""
    for idx, row in enumerate(rows):
        # 🚀 숫자(float)로 안전하게 변환하여 포맷팅 에러 완벽 차단
        try:
            price = float(row[1])
            price_text = f"${price:.2f}"
        except (ValueError, TypeError):
            price_text = f"${row[1]}"
            
        memory_text += f"\n[과거 기록 {idx+1} (작성일: {row[0]})]\n당시 주가: {price_text}\n{row[2][:500]}...\n"
    return memory_text

def save_to_notion(ticker, price, vix, fg, psycho, action, report):
    """심리 복기용: Notion DB에 마크다운 리포트 전송"""
    try:
        NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
        DATABASE_ID = st.secrets["NOTION_DATABASE_ID"]
    except KeyError:
        return False, "secrets.toml에 노션 API 키가 없습니다."

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    content_blocks = []
    for i in range(0, len(report), 1500):
        content_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": report[i:i+1500]}}]
            }
        })

    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "종목명": {"title": [{"text": {"content": ticker}}]},
            "날짜": {"date": {"start": datetime.datetime.now().strftime("%Y-%m-%d")}},
            "현재가": {"number": price},
            "VIX": {"number": float(vix)},
            "공포탐욕지수": {"number": int(fg)},
            "심리상태": {"rich_text": [{"text": {"content": psycho}}]},
            "매매계획": {"rich_text": [{"text": {"content": action}}]}
        },
        "children": content_blocks
    }
    
    res = requests.post(url, headers=headers, json=data)
    if res.status_code == 200:
        return True, "노션 저장 성공"
    else:
        return False, f"노션 에러: {res.text}"