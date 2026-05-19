import sqlite3
import requests
import datetime
import streamlit as st

def init_db():
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, ticker TEXT, current_price REAL,
            vix REAL, cnn_fg INTEGER,
            position TEXT, action_plan TEXT, psycho_state TEXT,
            report TEXT, audit_winner TEXT
        )
    ''')
    # 기존 DB에 audit_winner 컬럼 없으면 추가
    try:
        c.execute("ALTER TABLE logs ADD COLUMN audit_winner TEXT")
    except Exception:
        pass
    c.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            ticker TEXT PRIMARY KEY,
            added_at TEXT
        )
    ''')
    conn.commit()
    conn.close()


def save_to_sqlite(ticker, price, vix, fg, position, action, psycho, report, audit_winner=None):
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO logs (date, ticker, current_price, vix, cnn_fg,
                          position, action_plan, psycho_state, report, audit_winner)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (now, ticker, price, vix, fg, position, action, psycho, report, audit_winner))
    conn.commit()
    conn.close()


def get_recent_report(ticker):
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    c.execute("SELECT date, current_price, report FROM logs WHERE ticker=? ORDER BY date DESC LIMIT 3", (ticker,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return "최근 기록된 리포트 없음."

    memory_text = ""
    for idx, row in enumerate(rows):
        try:
            price_text = f"${float(row[1]):.2f}"
        except (ValueError, TypeError):
            price_text = f"${row[1]}"
        memory_text += f"\n[과거 기록 {idx+1} (작성일: {row[0]})]\n당시 주가: {price_text}\n{row[2][:500]}...\n"
    return memory_text


def get_audit_stats(ticker=None):
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    if ticker:
        c.execute("SELECT audit_winner, COUNT(*) FROM logs WHERE ticker=? AND audit_winner IS NOT NULL GROUP BY audit_winner", (ticker,))
    else:
        c.execute("SELECT audit_winner, COUNT(*) FROM logs WHERE audit_winner IS NOT NULL GROUP BY audit_winner")
    rows = c.fetchall()
    conn.close()

    stats = {'A': 0, 'B': 0, '무승부': 0}
    for winner, count in rows:
        if winner in stats:
            stats[winner] = count
    stats['total'] = sum(stats.values())
    return stats


def save_favorite(ticker):
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR IGNORE INTO favorites (ticker, added_at) VALUES (?, ?)", (ticker, now))
    conn.commit()
    conn.close()


def get_favorites():
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    c.execute("SELECT ticker FROM favorites ORDER BY added_at DESC")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def remove_favorite(ticker):
    conn = sqlite3.connect("investment_logs.db")
    c = conn.cursor()
    c.execute("DELETE FROM favorites WHERE ticker=?", (ticker,))
    conn.commit()
    conn.close()


def save_to_notion(ticker, price, vix, fg, psycho, action, report):
    try:
        NOTION_TOKEN  = st.secrets["NOTION_TOKEN"]
        DATABASE_ID   = st.secrets["NOTION_DATABASE_ID"]
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
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": report[i:i+1500]}}]}
        })

    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "종목명":     {"title": [{"text": {"content": ticker}}]},
            "날짜":       {"date": {"start": datetime.datetime.now().strftime("%Y-%m-%d")}},
            "현재가":     {"number": price},
            "VIX":        {"number": float(vix)},
            "공포탐욕지수": {"number": int(fg)},
            "심리상태":   {"rich_text": [{"text": {"content": psycho}}]},
            "매매계획":   {"rich_text": [{"text": {"content": action}}]}
        },
        "children": content_blocks
    }

    res = requests.post(url, headers=headers, json=data)
    if res.status_code == 200:
        return True, "노션 저장 성공"
    else:
        return False, f"노션 에러: {res.text}"
