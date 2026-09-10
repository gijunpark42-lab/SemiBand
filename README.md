# SemiBand v2 — self-weighting agent ensemble (paper)

여러 에이전트가 각자 종목 의견을 내고, 가중치로 합쳐 알파카 페이퍼 계좌($100K)에서 실제로 사고팔고,
5·10·20 거래일 뒤 SOXX 대비 성적으로 채점해서 누구 말을 더 들을지(가중치) 스스로 바꾼다.
LLM은 Claude Max 구독의 `claude -p`만 쓴다(API 키 없음). 유니버스는 earnings-ai 공급망 그래프의 미국 상장 종목(112개).

## 하루 한 바퀴 (`cycle.py`, 장 시작 5분 뒤)

1. `state/liquidate_pending`가 있으면 전부 청산(첫날 리셋).
2. 24시간 안에 우리 것(`sb2-` 접두사)이 아닌 주문이 보이면 **중단** — 다른 봇이 같은 계좌를 건드리는 중. `--force`로 무시.
3. 유니버스(`universe.py`) → 종가(`market.py`, yfinance).
4. 만기된 예측 채점 + 가중치 갱신(`score.py`, `ensemble.hedge_update`). 결과는 `state/ledger.sqlite`.
5. 에이전트 10명 실행(`agents/`). 정보 출처가 서로 다르게 역할을 나눴다.
   - 무료·규칙: `supply_chain`(지도: 세대 전환·캐파 매진·신선도) · `neighbors`(지도 한 칸 밖: 고객·공급사가 지금 뜨거운가) · `fundamentals`(성장·마진·밸류·목표주가) · `technical`(20/60일 모멘텀·추세·RSI) · `mean_reversion`(5일 과열 되돌림, technical의 반대 기질) · `events`(실적 발표 임박=리스크 / 직후=드리프트) · `risk`(변동성·낙폭 브레이크, 위험할 때만 발언)
   - Claude(상위 40종목만): `llm_supply`(공급망 리포트: 구조·딜·전환) · `llm_guidance`(자사 어닝콜 발언: 가이던스 모멘텀) · `llm_news`(3주 헤드라인: 촉매)
   - `moderator`는 투표 안 함. 주문 종목마다 합의/반대/결론/지켜볼 것 회의록을 씀.
6. 합산 → 종목별 확신도 → 목표 비중(`portfolio.py`: 상위 15, 종목당 10% 상한, 현금 한도 내) → 주문(`broker.py`).
7. 일지(`state/trades.json`)와 대시보드(`state/dashboard.json`)를 Vercel Blob에 올리고 `web/`이 보여준다.

## 실행

```
python cycle.py --dry-run --no-llm      # 무료 에이전트만, 주문 없음
python cycle.py --dry-run --tickers NVDA,AMD,MU
python cycle.py                         # 진짜 (장 열릴 때까지 기다렸다가 페이퍼 주문)
python liquidate.py --dry-run           # 청산 미리보기
python universe.py                      # 유니버스 새로고침
```

파이썬은 `C:\Users\calif\AppData\Local\Python\bin\python.exe`, `PYTHONUTF8=1`.
LLM 서버가 안 떠 있으면 `agents/llm.py`가 `dev\TradingAgents\local-claude\server.py`를 자동으로 띄운다.

매일 자동 실행(작업 스케줄러, 평일 06:35 PT = 09:35 ET):

```
schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 06:35 /TN SemiBand-Cycle /TR "cmd /c cd /d C:\Users\calif\Desktop\Trading && set PYTHONUTF8=1 && C:\Users\calif\AppData\Local\Python\bin\python.exe cycle.py >> state\run_daily.log 2>&1"
```

## 학습 규칙 (Hedge)

에이전트 i의 라운드 이득 = 새로 채점된 예측들의 평균( direction × confidence × 초과수익 × 20 ), [-1, 1]로 자름.
가중치 w_i ← w_i · exp(0.5 · 이득), 정규화, 최소 2%. 처음엔 열 명 다 10%.

## 규칙

- earnings-ai의 `chains/`, `graph/`에는 절대 쓰지 않는다. 읽기만.
- `config.PAPER = True`. 실계좌 전환은 없다.
- 결과는 연구용 페이퍼 트레이딩. 매수·매도 추천이 아니다.
- 커밋·푸시는 사용자가 한다.
