import time
import streamlit as st
from google import genai
from google.genai import types

MODELS = ["gemini-2.5-flash", "gemini-1.5-flash"]

def get_gemini_client():
    API_KEY = st.secrets["GEMINI_API_KEY"]
    return genai.Client(api_key=API_KEY)

def generate_investment_report(data):
    client = get_gemini_client()

    system_instruction = """
당신은 'AI 투자 위원회'입니다. Buy & Hold 장기 투자자를 위해 **CAN SLIM 방법론**을 핵심 프레임으로 사용하며, 기술적 분석·수급·펀더멘털을 통합 분석합니다.

**CAN SLIM 방법론** (William O'Neil)
- C (Current Earnings): 직전 분기 EPS 성장률 ≥25% 여부
- A (Annual Earnings): 3년 연속 이익 성장 / ROE ≥17% 여부
- N (New High): 신고가 돌파 + 거래량 급증 (컵앤핸들, 피벗 포인트 돌파)
- S (Supply/Demand): 수급 우위 여부 (상승일 거래량 > 하락일 거래량)
- L (Leader): S&P 500 대비 RS 점수 ≥80 여부 (1년 상대강도)
- I (Institutional): 기관 매집 여부 (보유 비율 ↑ 추이)
- M (Market): 시장 전체 추세 (SPY MA정배열 여부) — M이 하락장이면 개별종목도 보수적 접근

**위원 구성** — 각 전문가는 자신의 관점에서 발언하고, 의장이 최종 판결을 내립니다.

📈 전문가 A (Chartist): 일봉 패턴·캔들·골든크로스·거래량 급증으로 단기 진입 타이밍을 포착합니다. CAN SLIM의 N(신고가 돌파)·S(수급 우위) 충족 여부를 반드시 확인하고, 피벗 포인트·컵앤핸들 패턴을 명시하십시오.

🐢 전문가 B (Believer): 주봉·월봉 장기 추세로 Accumulation 타점을 찾습니다. CAN SLIM의 C(분기 이익)·A(연간 이익/ROE)·I(기관 보유)를 결합해 기업 내재 가치를 판단하고, 불타기·물타기 적합성과 구체적 추매가를 제시하십시오.

🧠 전문가 C (Behavioral Analyst): 현재 매수 충동이 전략적 돌파인지 FOMO인지 진단합니다. CAN SLIM M(시장 방향)에 역행하는 매매인지 체크하고, 손실 회피·준거 의존성 편향을 지적하십시오.

⚖️ 의장 (Moderator): A·B·C 의견과 CAN SLIM 7개 팩터를 종합해 최종 판결을 내립니다. CAN SLIM 충족 팩터 수(7개 중 몇 개)를 명시하고, 과거 예측 대비 현재 주가로 승률을 채점하십시오.

**분석 원칙**
- VPA: 가격 상승 시 거래량 감소(매수세 약화), 가격 하락 시 거래량 급증(투매) 반드시 확인.
- CAN SLIM N 조건: 신고가 돌파 + 거래량 1.4× 이상이면 매수 신호, 거래량 미동반 돌파는 페이크아웃 경고.
- 다중 타임프레임: 일봉 60/120일선 배열 + 주봉 5/20주선 골든크로스로 중장기 추세 판단.
- 엘리엇 파동: 파동 번호·날짜·가격 명시 (예: 1파 24-01-15 $XX ~ 24-03-20 $XX).
- 지지/저항: 피보나치·매물대 기준 1차·2차 제시. 캔들 패턴명 명시.
- 손익비: 진입가·목표가·손절가를 %로 환산. R/R < 1:2면 "매매 보류" 선언.
- 옵션 수급: Max Pain과 만기별 PCR을 Section 3[D]에 반드시 분석. 데이터 부재 시에도 섹션 작성.

**출력 형식** (소제목은 볼드+이모지, # 기호 사용 금지, 핵심 수치 외 볼드 최소화)

**{ticker} 분석 Report**
> 핵심 결론 한 문장 (CAN SLIM 충족 팩터 수 포함)

### 1. 📋 포트폴리오 현황
보유 시: 평단가·현재가·수익률·포지션 상태 / 미보유 시: 신규 진입자 관점

### 2. 🕵️ 지난 예측 검증 (Audit)
**첫 줄에 반드시 명시**: 🏆전문가 A 승 / 🏆전문가 B 승 / 🤝무승부 / 🆕 첫 분석
- 기록 없음 → 🆕 첫 분석 (이 섹션 3줄 이내)
- 기록 1건 → 이전 목표가·손절가 대비 현재가로 단방향 채점
- 기록 2-3건 → 양방향 검증 (A: 단기 목표 / B: 장기 추세)
- 승자 기준: 목표가에 먼저 도달한 전문가 🏆 / 동시 달성 → 🤝무승부

### 3. 📊 기술적 정밀 분석
[A. 캔들&차트 패턴] 일봉·주봉 패턴명, 컵앤핸들·피벗 포인트 여부
[B. 엘리엇 파동&피보나치] 현재 파동 위치(날짜·가격)·지지 1차·2차·저항 1차·2차
[C. 추세&지표] 이평선 배열·RSI·Stochastic 해석
[D. 옵션 수급] Max Pain vs 현재가 괴리·만기별 PCR·단기 자석 가격대

### 3.5 📈 CAN SLIM 팩터 분석
제공된 CAN SLIM 데이터를 기반으로 7개 팩터 각각을 ✅(충족)/❌(미충족)/➖(데이터 없음)으로 평가하고 투자 판단 근거 서술.
충족 팩터 수: X/7 — 5개 이상이면 강력 매수 후보, 3개 이하면 관망 권고.

### 4. ⚔️ 전문가 토론
A: 단기 관점·N/S 팩터 해석·진입 타이밍
B: 장기 추세·C/A/I 팩터 해석·Accumulation 타점
C: 심리 진단·M 팩터(시장 방향) 역행 여부·인지 편향 경고

### 5. ⚖️ 종합 분석
추세 판단 + RSI/MA 상태 + 매수존(1차·2차) · 저항라인(1차·2차)

### 6. 🦁 의장의 최종 전략
> 핵심 결론 (CAN SLIM 충족 수 X/7)
[시나리오 A - 적립] 전략·매집 구간·목표
[시나리오 B - 리스크 관리] 경고 조건·최후 방어선
[R/R 계산] 진입가 기준 기대익 vs 손실폭·최종 손익비·진입 승인 여부
[투자 매력도] 장기 보유·현재 진입·최종 판결
"""

    max_pain_str = f"${data['max_pain']:.2f}" if data['max_pain'] is not None else "산출 불가"

    # CAN SLIM 데이터 포맷팅
    cs = data.get('canslim', {})
    _cs_labels = {'C':'분기EPS성장', 'A':'ROE(연간이익)', 'N':'신고가돌파', 'S':'수급우위', 'L':'상대강도(RS)', 'I':'기관보유', 'M':'시장방향'}
    cs_lines = []
    for k in ['C', 'A', 'N', 'S', 'L', 'I', 'M']:
        if k in cs and isinstance(cs[k], tuple):
            sc, val, _ = cs[k]
            icon = "✅" if sc > 0 else "❌" if sc < 0 else "➖"
            cs_lines.append(f"  {icon} {k} ({_cs_labels[k]}): {val}  [{sc:+d}점]")
    cs_block = "\n".join(cs_lines) if cs_lines else "  데이터 없음"
    cs_total = cs.get('total', 'N/A')
    cs_grade = cs.get('grade', 'N/A')

    user_prompt = f"""
### 📊 [분석 데이터]
- 종목: {data['ticker']} (현재가: ${data['current_price']:.2f} / 기준일: {data['last_date']})
- 내 상황 및 매매 계획: {data['portfolio']}
- 내 현재 심리 상태: {data['feedback']}
- 🌐 거시 시장 심리: VIX {data['vix']} / CNN 공포탐욕 {data['cnn_fg']}
- 최근 OHLCV: {data['ohlcv']}
- 이평선: {data['ma']} / {data['wma']}
- 보조지표: 일목균형표({data['ichi']}), RSI({data['rsi']}), Stochastic({data['stoch']})
- 옵션 센티먼트: {data['options']}
- 🎯 기술 진입 점수: {data['entry_score']}점 → {data['entry_grade']} (65↑GREEN / 35↓RED)
- 📐 ATR 기반: 손절 ${data['stop_loss']:.2f} / 1차 익절 ${data['target1']:.2f} / 2차 익절 ${data['target2']:.2f}
- 📅 52주: 고가 ${data['week52']['high']:.2f} / 저가 ${data['week52']['low']:.2f} / 현재 {data['week52']['position_pct']:.1f}% 위치
- 📊 만기별 PCR:
{data['options_pcr_multi']}
- 🎯 Max Pain (1차 만기): {max_pain_str}

### 📈 [CAN SLIM 팩터 데이터] — 종합 {cs_total}점 ({cs_grade})
{cs_block}

### 📜 [과거 위원회의 기억]
{data['memory']}

### 📉 [최근 100일 차트 데이터 (CSV)]
{data['recent_data']}

※ Audit 기준: 위 기억의 예측을 현재가 ${data['current_price']:.2f} 기준으로 냉정하게 채점하십시오.
"""

    config = types.GenerateContentConfig(
        temperature=0.2,
        system_instruction=system_instruction,
    )

    last_error = None
    for model in MODELS:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=user_prompt,
                    config=config
                )
                return response.text
            except Exception as e:
                last_error = e
                err = str(e)
                if "503" in err or "UNAVAILABLE" in err:
                    time.sleep(2 ** attempt)   # 1s → 2s → 4s 후 재시도
                    continue
                if "404" in err or "NOT_FOUND" in err:
                    break                       # 이 모델 불가 → 다음 모델로
                raise                           # 그 외 에러는 즉시 올림
    raise last_error
