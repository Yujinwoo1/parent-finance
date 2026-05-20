import datetime
import requests
import streamlit as st


def _headers():
    return {
        "Authorization": f"Bearer {st.secrets['NOTION_TOKEN']}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def _reports_db():
    return st.secrets["NOTION_DATABASE_ID"]


def _favorites_db():
    return st.secrets["NOTION_FAVORITES_DB_ID"]


@st.cache_data(ttl=600)
def get_recent_report(ticker):
    """Notion 리포트 DB에서 최근 3개 리포트 조회."""
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{_reports_db()}/query",
            headers=_headers(),
            json={
                "filter": {"property": "종목명", "title": {"equals": ticker}},
                "sorts": [{"property": "날짜", "direction": "descending"}],
                "page_size": 3,
            },
            timeout=10,
        )
        pages = res.json().get("results", [])
        if not pages:
            return "최근 기록된 리포트 없음."

        memory_text = ""
        for idx, page in enumerate(pages):
            props     = page["properties"]
            date_obj  = (props.get("날짜") or {}).get("date") or {}
            date_str  = date_obj.get("start", "날짜 없음")
            price     = (props.get("현재가") or {}).get("number") or 0
            price_txt = f"${float(price):.2f}"

            blk_res = requests.get(
                f"https://api.notion.com/v1/blocks/{page['id']}/children",
                headers=_headers(),
                timeout=10,
            )
            report_text = ""
            for block in blk_res.json().get("results", [])[:5]:
                if block.get("type") == "paragraph":
                    for t in block["paragraph"].get("rich_text", []):
                        report_text += t.get("plain_text", "")

            memory_text += (
                f"\n[과거 기록 {idx+1} (작성일: {date_str})]\n"
                f"당시 주가: {price_txt}\n{report_text[:500]}...\n"
            )
        return memory_text
    except Exception as e:
        return f"최근 기록 조회 실패: {e}"


def _find_today_report(ticker):
    """오늘 날짜 + 같은 티커 리포트 페이지 ID 반환 (없으면 None)."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{_reports_db()}/query",
            headers=_headers(),
            json={
                "filter": {
                    "and": [
                        {"property": "종목명", "title":  {"equals": ticker}},
                        {"property": "날짜",   "date":   {"equals": today}},
                    ]
                },
                "page_size": 1,
            },
            timeout=10,
        )
        results = res.json().get("results", [])
        return results[0]["id"] if results else None
    except Exception:
        return None


def _replace_page_blocks(page_id, properties, content_blocks):
    """기존 페이지 속성 업데이트 + 블록 전체 교체."""
    # 1) 기존 블록 삭제
    blk_res = requests.get(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=_headers(), timeout=10
    )
    for blk in blk_res.json().get("results", []):
        try:
            requests.delete(
                f"https://api.notion.com/v1/blocks/{blk['id']}",
                headers=_headers(), timeout=5,
            )
        except Exception:
            pass
    # 2) 속성 업데이트
    requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=_headers(), json={"properties": properties}, timeout=10,
    )
    # 3) 새 블록 추가
    return requests.patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=_headers(), json={"children": content_blocks}, timeout=15,
    )


def save_to_notion(ticker, price, vix, fg, psycho, action, report,
                   audit_winner=None, verdict=None):
    try:
        content_blocks = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": report[i : i + 1500]}}]
                },
            }
            for i in range(0, len(report), 1500)
        ]
        properties = {
            "종목명":       {"title": [{"text": {"content": ticker}}]},
            "날짜":         {"date": {"start": datetime.datetime.now().strftime("%Y-%m-%d")}},
            "현재가":       {"number": float(price)},
            "VIX":          {"number": float(vix)},
            "공포탐욕지수": {"number": int(fg)},
            "심리상태":     {"rich_text": [{"text": {"content": psycho}}]},
            "매매계획":     {"rich_text": [{"text": {"content": action}}]},
        }
        if audit_winner:
            properties["audit_winner"] = {"rich_text": [{"text": {"content": audit_winner}}]}
        if verdict:
            properties["verdict"] = {"rich_text": [{"text": {"content": verdict}}]}

        # ── 오늘 같은 티커 리포트가 이미 있으면 업데이트, 없으면 생성 ──
        existing_id = _find_today_report(ticker)
        if existing_id:
            res = _replace_page_blocks(existing_id, properties, content_blocks)
            ok  = res.status_code == 200
            msg = "노션 리포트 업데이트 성공" if ok else f"노션 업데이트 에러: {res.text[:200]}"
            return ok, msg

        payload = {
            "parent": {"database_id": _reports_db()},
            "properties": properties,
            "children": content_blocks,
        }
        res = requests.post("https://api.notion.com/v1/pages", headers=_headers(),
                            json=payload, timeout=15)
        if res.status_code != 200 and (audit_winner or verdict):
            for k in ("audit_winner", "verdict"):
                payload["properties"].pop(k, None)
            res = requests.post("https://api.notion.com/v1/pages", headers=_headers(),
                                json=payload, timeout=15)

        return (True, "노션 저장 성공") if res.status_code == 200 else (False, f"노션 에러: {res.text[:200]}")
    except Exception as e:
        return False, f"노션 저장 실패: {e}"


@st.cache_data(ttl=300)
def get_all_reports(limit=200):
    """Notion 리포트 DB 전체 조회 (백테스트용 — 속성만, 블록 미조회)."""
    try:
        all_pages, cursor = [], None
        while len(all_pages) < limit:
            payload = {
                "page_size": min(100, limit - len(all_pages)),
                "sorts": [{"property": "날짜", "direction": "descending"}],
            }
            if cursor:
                payload["start_cursor"] = cursor
            res  = requests.post(
                f"https://api.notion.com/v1/databases/{_reports_db()}/query",
                headers=_headers(), json=payload, timeout=15,
            )
            if res.status_code != 200:
                break
            data  = res.json()
            pages = data.get("results", [])
            all_pages.extend(pages)
            if not data.get("has_more") or not pages:
                break
            cursor = data.get("next_cursor")

        reports = []
        for page in all_pages:
            props = page["properties"]
            tickers = (props.get("종목명") or {}).get("title", [])
            ticker  = tickers[0]["plain_text"] if tickers else ""
            if not ticker:
                continue
            date_obj = (props.get("날짜") or {}).get("date") or {}
            date_str = date_obj.get("start", "")
            if not date_str:
                continue
            price   = (props.get("현재가") or {}).get("number") or 0
            verdict = ((props.get("verdict") or {}).get("rich_text") or [{}])[0].get("plain_text")
            winner  = ((props.get("audit_winner") or {}).get("rich_text") or [{}])[0].get("plain_text")
            reports.append({
                "ticker":  ticker,
                "date":    date_str,
                "price":   float(price),
                "verdict": verdict,
                "winner":  winner,
            })
        return reports
    except Exception:
        return []


def get_audit_stats(ticker=None):
    """Notion 리포트 DB에서 audit_winner 통계 집계."""
    try:
        payload = {"page_size": 100}
        if ticker:
            payload["filter"] = {"property": "종목명", "title": {"equals": ticker}}
        res = requests.post(
            f"https://api.notion.com/v1/databases/{_reports_db()}/query",
            headers=_headers(),
            json=payload,
            timeout=10,
        )
        stats = {"A": 0, "B": 0, "무승부": 0}
        for page in res.json().get("results", []):
            winner_list = (page["properties"].get("audit_winner") or {}).get("rich_text", [])
            if winner_list:
                w = winner_list[0].get("plain_text", "")
                if w in stats:
                    stats[w] += 1
        stats["total"] = sum(stats.values())
        return stats
    except Exception:
        return {"A": 0, "B": 0, "무승부": 0, "total": 0}


@st.cache_data(ttl=60)
def get_favorites():
    """Notion 즐겨찾기 DB에서 전체 종목 조회."""
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{_favorites_db()}/query",
            headers=_headers(),
            json={
                "sorts": [{"property": "added_date", "direction": "descending"}],
                "page_size": 100,
            },
            timeout=10,
        )
        tickers = []
        for page in res.json().get("results", []):
            title_list = (page["properties"].get("ticker") or {}).get("title", [])
            if title_list:
                tickers.append(title_list[0]["plain_text"])
        return tickers
    except Exception:
        return []


def add_favorite(ticker):
    """Notion 즐겨찾기 DB에 종목 추가 (중복 제외)."""
    if ticker in get_favorites():
        return
    try:
        requests.post(
            "https://api.notion.com/v1/pages",
            headers=_headers(),
            json={
                "parent": {"database_id": _favorites_db()},
                "properties": {
                    "ticker":     {"title": [{"text": {"content": ticker}}]},
                    "added_date": {"date": {"start": datetime.datetime.now().strftime("%Y-%m-%d")}},
                },
            },
            timeout=10,
        )
        get_favorites.clear()
    except Exception:
        pass


def remove_favorite(ticker):
    """Notion 즐겨찾기 DB에서 종목 삭제 (페이지 아카이브)."""
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{_favorites_db()}/query",
            headers=_headers(),
            json={"filter": {"property": "ticker", "title": {"equals": ticker}}},
            timeout=10,
        )
        for page in res.json().get("results", []):
            requests.patch(
                f"https://api.notion.com/v1/pages/{page['id']}",
                headers=_headers(),
                json={"archived": True},
                timeout=10,
            )
        get_favorites.clear()
    except Exception:
        pass
