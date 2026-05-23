# 🏛️ AI 투자 위원회 분석 시스템

CAN SLIM 방법론 기반 AI 주식 분석 대시보드.  
Gemini AI가 차티스트·장기투자자·행동심리학자 3명의 전문가로 토론해 BUY / HOLD / SELL 판결을 내립니다.

---

## 주요 기능

| 탭 | 기능 |
|---|---|
| 📊 AI 분석 | 티커 입력 → CAN SLIM + 기술 진입점수 + AI 위원회 토론 리포트 |
| 🔬 백테스트 | 과거 AI 판결(BUY/HOLD/SELL) 대비 실제 수익률 검증 |
| 🔭 시장 스캐너 | Nasdaq-100 / S&P 500 전 종목 기술 진입점수 일괄 스캔 |

**부가 기능**
- 즐겨찾기 GREEN 신호 → 텔레그램 자동 알림 (장 09:00~16:00 ET만)
- Notion 매매일지 자동 백업
- OI 히트맵 + Max Pain + 만기별 PCR 옵션 수급 분석

---

## 로컬 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. secrets 설정

`.streamlit/secrets.toml` 파일을 아래 양식으로 작성:

```toml
GEMINI_API_KEY      = "AIza..."          # Google AI Studio에서 발급
NOTION_TOKEN        = "secret_..."       # Notion Integration Token
NOTION_DATABASE_ID  = "xxxxxxxx..."      # Notion DB 페이지 ID

# 선택 사항
TELEGRAM_BOT_TOKEN  = "123456:ABC..."    # BotFather에서 발급
TELEGRAM_CHAT_ID    = "-100..."          # 텔레그램 채팅 ID
TRADIER_TOKEN       = "..."              # Tradier 실시간 옵션 (없으면 yfinance 사용)
```

> `secrets.toml`은 `.gitignore`에 포함돼 있어 깃헙에 올라가지 않습니다.

### 3. 앱 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속.

---

## Claude Code 사용법

이 프로젝트는 **Claude Code** (Anthropic CLI)로 개발/유지보수합니다.

### 설치

```bash
npm install -g @anthropic/claude-code
```

### 기본 사용

```bash
# 프로젝트 폴더에서 실행
cd /path/to/parent-finance
claude
```

### 자주 쓰는 명령

| 명령 | 설명 |
|---|---|
| `claude` | 대화형 세션 시작 |
| `claude "질문이나 작업 지시"` | 한 줄 실행 후 종료 |
| `claude --continue` | 이전 대화 이어서 |
| `/help` | 세션 내 도움말 |
| `/model opusplan` | 계획 단계엔 Opus, 실행엔 Sonnet 자동 전환 |
| `! git status` | `!` 접두어로 터미널 명령을 세션 안에서 실행 |

### 깃헙 푸시하는 법

Claude Code 세션 안에서 자연어로 요청하면 됩니다:

```
커밋하고 깃헙에 푸시해줘
```

또는 직접 터미널에서:

```bash
# 변경 파일 스테이징
git add app.py notifier.py ai_generator.py

# 커밋
git commit -m "feat: 텔레그램 장중 필터 + 리포트 대시보드"

# 푸시
git push origin main
```

Claude Code에게 "커밋 메시지 작성해줘" 라고 하면 변경 내용을 읽고 적절한 메시지를 제안합니다.

### 유용한 Claude Code 작업 예시

```
# 버그 수정 요청
notifier.py에서 텔레그램이 주말에도 전송되는 버그 고쳐줘

# 기능 추가 요청
즐겨찾기 화면에 손절가도 같이 보여줘

# 코드 리뷰
현재 브랜치 변경사항 리뷰해줘

# 파일 탐색
entry_score 계산 로직이 어디에 있어?

# PR 생성
현재 브랜치로 PR 만들어줘
```

### 슬래시 커맨드 (세션 내)

| 커맨드 | 설명 |
|---|---|
| `/run` | 앱 실행해서 동작 확인 |
| `/review` | 현재 변경사항 코드 리뷰 |
| `/model` | 사용 모델 변경 |
| `/clear` | 컨텍스트 초기화 |

---

## 파일 구조

```
parent-finance/
├── app.py              # Streamlit 메인 UI (탭 3개)
├── data_fetcher.py     # yfinance 데이터 수집 + 지표 계산 + CAN SLIM 채점
├── ai_generator.py     # Gemini API 호출 + 위원회 시스템 프롬프트
├── notifier.py         # 텔레그램 알림 (장중 필터 포함)
├── database.py         # SQLite 로컬 DB + Notion API
├── requirements.txt
└── .streamlit/
    ├── config.toml
    └── secrets.toml    # ← 깃헙에 올리면 안 됨
```

---

## 환경변수 발급 방법

### Gemini API Key
1. [Google AI Studio](https://aistudio.google.com) 접속
2. "Get API key" → 새 키 생성

### Notion Token + Database ID
1. [Notion Integrations](https://www.notion.so/my-integrations) → New integration 생성
2. 매매일지로 쓸 Notion 데이터베이스 페이지 열기
3. 우측 상단 `···` → Connections → 생성한 integration 연결
4. 페이지 URL에서 `notion.so/xxxxxxxx...` 부분이 Database ID

### Telegram Bot
1. 텔레그램에서 `@BotFather` 검색 → `/newbot`
2. 발급된 토큰을 `TELEGRAM_BOT_TOKEN`에 입력
3. 봇과 대화 시작 후 `https://api.telegram.org/bot{TOKEN}/getUpdates` 에서 `chat.id` 확인
