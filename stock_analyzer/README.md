# stock_analyzer

`stock_crawler` 가 저장한 종목별 OHLCV CSV 위에서 **단기(1일~1주일) 매매 신호**를 계산하는
패키지입니다. 단일 종목 분석(`analyze`)과 시장 전체 스캔(`scan`) 두 가지 모드를 제공합니다.

CLI 진입점은 저장소 루트의 `main_analyze.py` → `stock_analyzer.cli:app` 입니다.

신호는 계산 결과일 뿐 **투자 조언이 아닙니다.** 결과 텍스트나 사유 문구에 확정적 수익을
암시하는 표현을 넣지 마세요.

---

## 모듈 구성

| 파일 | 역할 |
|---|---|
| `data.py` | 저장된 OHLCV CSV 로드, 컬럼/정렬 정규화, `lookback_days` 슬라이싱 |
| `indicators.py` | RSI, EMA, Bollinger, ATR, ROC, Volume Spike 기술 지표 |
| `strategies.py` | `rsi` / `ema` / `bollinger` / `volume` / `composite` 5종 전략, `StrategyResult` |
| `scanner.py` | TOP-N 전 종목에 전략 적용, `|score|` 내림차순 정렬, 신호 CSV 저장 |
| `cli.py` | Typer 명령 (`analyze`, `scan`) |

`stock_crawler.config.Market`, `stock_crawler.config.CrawlConfig`,
`stock_crawler.storage.csv_path`, `stock_crawler.tickers.resolve_tickers` 를 재사용합니다.

---

## 데이터 흐름

```
data/{market}/{ticker}.csv
        │
        ▼
load_ohlcv (data.py)
        │
        ▼
run_strategy → STRATEGIES[name] (strategies.py)
        │       └─ indicators.py 의 RSI/EMA/Bollinger/ATR/ROC/Volume 사용
        ▼
StrategyResult(signal, score, reasons, indicators)
        │
        ▼ (scan 모드일 때)
scan (scanner.py) → data/{market}/_signals/{YYYY-MM-DD}.csv
```

---

## 전략 목록

| 키 | 함수 | 핵심 규칙 |
|---|---|---|
| `rsi` | `rsi_mean_reversion` | RSI ≤ oversold(30) → buy, ≥ overbought(70) → sell. 중립 구간은 약한 신호. |
| `ema` | `ema_crossover` | 단기 EMA(5) / 장기 EMA(20) 의 직전봉 교차 시 강한 신호(±0.8), 그 외엔 스프레드 × 20 스케일링. |
| `bollinger` | `bollinger_breakout` | 종가가 하단 ≤ 이탈 → buy, 상단 ≥ 돌파 → sell. 내부 구간은 %B 기반 약한 신호. |
| `volume` | `volume_breakout` | 거래량 ≥ MA(20) × 2.0 이고 종가 양봉 → buy, 음봉 → sell. |
| `composite` | `composite` | 위 4개 전략의 평균 점수. ATR(7)/ROC(5)/`stop_loss` 보조 지표 포함. `MIN_BARS=25` |

모든 전략 점수는 `-1.0 ≤ score ≤ 1.0` 범위를 유지합니다. 점수 → 시그널 임계는
`_signal_from_score(threshold=0.2)` 입니다.

---

## 신호 CSV 스키마

`data/{market}/_signals/{YYYY-MM-DD}.csv`:

```text
as_of_date, ticker, name, signal, score, reasons, <전략별 지표 컬럼들>
```

- `signal ∈ {buy, sell, hold}`
- `score` 는 소수 4자리 반올림
- `reasons` 는 `" | "` 로 join 된 문자열
- `composite` 전략은 `rsi`, `ema_fast`, `ema_slow`, `bb_upper/lower/mid`, `volume_ratio`, `roc1`, `atr7`, `roc5`, `stop_loss` 등 가능한 모든 보조 지표를 평탄화해 함께 저장합니다.

---

## CLI

```bash
# 단일 종목 분석
uv run python main_analyze.py analyze 005930 --market kospi --strategy composite
uv run python main_analyze.py analyze AAPL --market nasdaq --strategy rsi --lookback-days 90

# 시장 전체 스캔 (디스크에 신호 CSV 저장 + 상위 20개 출력)
uv run python main_analyze.py scan --market kospi --top 200 --strategy composite --show-top 20
uv run python main_analyze.py scan --market nasdaq --top 200 --strategy ema --exclude-etf

# 신호 CSV 저장 없이 결과만 보고 싶을 때
uv run python main_analyze.py scan --market kospi --top 50 --save false
```

`scan` 은 `stock_crawler.tickers.resolve_tickers` 를 캐시 모드(`refresh=False`)로 호출
하므로 **티커 캐시가 미리 만들어져 있어야** 합니다. 없으면 한 번
`uv run python main.py tickers --market <market>` 로 만들어 두세요.

---

## 핵심 불변 조건

| 영역 | 반드시 지킬 것 |
|---|---|
| `indicators.py` | 누적 윈도우가 채워지지 않은 앞부분은 `NaN` (`min_periods=period`). 임의로 0/평균 등으로 메우지 마세요. |
| `strategies.py` | 모든 전략의 `score` 는 `-1.0 ≤ score ≤ 1.0`. 데이터 부족은 `_insufficient()` 로 `hold` 반환. |
| `strategies.py` | `composite` 는 `_insufficient` 결과를 평균에서 제외 (전체가 부족하면 `hold`). |
| `scanner.py` | 결과는 `abs(score)` 내림차순 정렬. 종목별 실패는 잡아서 `hold` 로 대체하고 전체 흐름 유지. |
| `data.py` | 입력 CSV 가 없으면 빈 `DataFrame` 반환(예외 X). 호출자(`scan`/`analyze`)가 분기 처리. |

---

## 검증

```bash
uv run pytest tests/test_indicators.py tests/test_strategies.py tests/test_data.py
uv run ruff check .
uv run ruff format --check .
```

`scan` 을 외부 데이터와 함께 검증해야 할 때는 소량(`--top 5`)으로 실행하세요.
