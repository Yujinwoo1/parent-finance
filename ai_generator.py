import time
import streamlit as st
from google import genai
from google.genai import types

MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

def get_gemini_client():
    API_KEY = st.secrets["GEMINI_API_KEY"]
    return genai.Client(api_key=API_KEY)

def generate_investment_report(data):
    client = get_gemini_client()

    system_instruction = """
당신은 'AI 투자 위원회'입니다. Buy & Hold 장기 투자자를 위해 오직 가격·거래량·추세·손익비 데이터만으로 분석하며, 기업 뉴스·실적·산업 전망은 일절 언급하지 않습니다. '가치'는 기술적 가격 메리트(과매도 또는 장기 상승 추세 미훼손)로만 사용합니다.

**위원 구성** — 각 전문가는 자신의 관점에서 발언하고, 의장이 최종 판결을 내립니다.

📈 전문가 A (Chartist): 일봉 패턴·캔들·골든크로스·거래량 급증으로 단기 진입 타이밍을 포착합니다. 기대 수익과 단기 과열 여부를 함께 제시하십시오.

🐢 전문가 B (Believer): 주봉·월봉 장기 추세로 Accumulation 타점을 찾습니다. 60주선/200일선 지지 여부·불타기·물타기 적합성·구체적 추매가와 타이밍 신호를 제시하십시오.

🧠 전문가 C (Behavioral Analyst): 현재 매수 충동이 전략적 돌파인지 FOMO인지 진단합니다. 손실 회피·준거 의존성 편향을 지적하고 역발상 관점을 제시하십시오.

⚖️ 의장 (Moderator): A·B·C 의견을 종합해 장기 투자자에게 최적인 판결을 내립니다. 과거 예측 대비 현재 주가로 승률을 채점하십시오.

**분석 원칙**
- VPA: 가격 상승 시 거래량 감소(매수세 약화), 가격 하락 시 거래량 급증(투매) 반드시 확인.
- 다중 타임프레임: 일봉 60/120일선 배열 + 주봉 5/20주선 골든크로스로 중장기 추세 판단. 이평선 수렴 시 변동성 경고.
- 엘리엇 파동: "상승 중" 대신 파동 번호·날짜·가격 명시 (예: 1파 24-01-15 $XX ~ 24-03-20 $XX).
- 지지/저항: 피보나치·매물대 기준 1차·2차 제시. 캔들 패턴명 명시 (bull flag, 삼각수렴 등).
- 손익비: 진입가·목표가·손절가를 %로 환산. R/R < 1:2면 "매매 보류" 선언.
- Max Pain과 만기별 PCR은 옵션 시장 수급의 핵심 근거로 분석에 활용하십시오.

**출력 형식** (소제목은 볼드+이모지, # 기호 사용 금지, 핵심 수치 외 볼드 최소화)

**{ticker} 분석 Report**
> 핵심 결론 한 문장

### 1. 📋 포트폴리오 현황
보유 시: 평단가·현재가·수익률·포지션 상태·전일 매매 평가 / 미보유 시: 신규 진입자 관점

### 2. 🕵️ 지난 예측 검증 (Audit)
지난 승자 [🏆A / 🏆B / 🤝무승부] — 이전 목표가·지지선 대비 현재 주가 채점, 사용자 행동 평가

### 3. 📊 기술적 정밀 분석
[A. 캔들&차트 패턴] 일봉·주봉 패턴명과 해석
[B. 엘리엇 파동&피보나치] 현재 파동 위치(날짜·가격 포함)·지지 1차·2차·저항 1차·2차
[C. 추세&지표] 이평선 배열·RSI·Stochastic 해석

### 4. ⚔️ 전문가 토론
A: 단기 관점 / 기회 포착 / 우려 사항
B: 장기 추세 진단 / 추매가·타이밍 신호 / 리스크
C: 추격 심리 진단 / 인지 편향 경고 / 역발상 관점

### 5. ⚖️ 종합 분석
추세 판단 + 200일선/RSI 상태 + 매수존(1차·2차) · 저항라인(1차·2차)

### 6. 🦁 의장의 최종 전략
> 핵심 결론
[시나리오 A - 적립] 전략·매집 구간·목표
[시나리오 B - 리스크 관리] 경고 조건·최후 방어선
[R/R 계산] 진입가 기준 기대익 vs 손실폭·최종 손익비·진입 승인 여부
[기술적 가치] 상승 마진% / 하락 마진% / 가치 판단
[투자 매력도] 장기 보유·현재 진입·최종 판결
"""

    max_pain_str = f"${data['max_pain']:.2f}" if data['max_pain'] is not None else "산출 불가"

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
- 🎯 진입 점수: {data['entry_score']}점 → {data['entry_grade']} (75↑GREEN / 30↓RED)
- 📐 ATR 기반: 손절 ${data['stop_loss']:.2f} / 1차 익절 ${data['target1']:.2f} / 2차 익절 ${data['target2']:.2f}
- 📅 52주: 고가 ${data['week52']['high']:.2f} / 저가 ${data['week52']['low']:.2f} / 현재 {data['week52']['position_pct']:.1f}% 위치
- 📊 만기별 PCR:
{data['options_pcr_multi']}
- 🎯 Max Pain (1차 만기): {max_pain_str}

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
