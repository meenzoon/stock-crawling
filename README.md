# stock-crawling

KOSPI / NASDAQ 시가총액 TOP-N 종목의 **일봉 OHLCV** 데이터를 무료 소스에서 수집하고,
저장된 CSV를 기반으로 단기 매매 신호를 계산하는 Python CLI 프로젝트입니다.

## 주요 기능

- **TOP-N 티커 수집**: KOSPI는 Naver Finance 시가총액 페이지, NASDAQ은 nasdaq.com
  screener API를 사용합니다.
- **ETF 제외 옵션**: `--exclude-etf`로 ETF 목록을 별도로 받아 TOP-N 산정에서 제외합니다.
- **OHLCV 수집**: yfinance `Ticker.history()`를 사용합니다. KOSPI 종목은 Yahoo Finance
  규칙에 맞춰 `.KS` 접미사를 붙여 호출합니다.
- **증분 저장**: 종목별 CSV의 마지막 거래일 다음 날부터만 추가 수집합니다.
- **호출 제한**: 요청 간 최소 간격과 분당 호출 수 제한으로 429 가능성을 줄입니다.
- **스케줄링**: apscheduler로 매일 지정 시각 또는 N시간 간격 수집을 실행합니다.
- **신호 분석**: RSI, EMA, Bollinger Band, ATR, 거래량 스파이크, ROC 기반 단기 신호를
  생성합니다.

## 설치

Python 3.13+와 [uv](https://github.com/astral-sh/uv)가 필요합니다.

```bash
uv sync
```

패키지 관리는 uv만 사용합니다.

## 빠른 시작

```bash
# KOSPI TOP 200 티커 확인 및 캐시
uv run python -m stock_crawler tickers --market kospi --top 200

# KOSPI TOP 200 일봉 수집
uv run python -m stock_crawler fetch --market kospi --top 200

# 수집된 CSV로 단일 종목 신호 분석
uv run python -m stock_analyzer analyze 005930 --market kospi --strategy composite

# 시장 전체 스캔
uv run python -m stock_analyzer scan --market kospi --top 200 --show-top 20
```

## 티커 수집

```bash
uv run python -m stock_crawler tickers --market kospi --top 200
uv run python -m stock_crawler tickers --market nasdaq --top 200
```

티커 목록은 `data/_tickers/{market}_top{N}.csv`에 캐시됩니다. ETF 제외 옵션을 사용하면
`data/_tickers/{market}_top{N}_no_etf.csv`로 별도 캐시됩니다.

```bash
# 캐시 무시 후 다시 수집
uv run python -m stock_crawler tickers --market kospi --top 200 --refresh

# ETF 제외
uv run python -m stock_crawler tickers --market kospi --top 200 --exclude-etf
uv run python -m stock_crawler tickers --market nasdaq --top 200 --exclude-etf
```

## OHLCV 수집

```bash
# KOSPI 시총 상위 200개
uv run python -m stock_crawler fetch --market kospi --top 200

# NASDAQ 시총 상위 200개
uv run python -m stock_crawler fetch --market nasdaq --top 200
```

수집 동작:

- 첫 실행은 종목별 전체 이력(`period="max"`)을 받습니다.
- 이후 실행은 저장된 CSV의 마지막 거래일 다음 날부터 증분 업데이트합니다.
- 티커 목록을 다시 계산하려면 `--refresh-tickers`를 사용합니다.
- ETF를 제외한 universe를 사용하려면 `--exclude-etf`를 사용합니다.

```bash
uv run python -m stock_crawler fetch --market kospi --top 200 --refresh-tickers
uv run python -m stock_crawler fetch --market nasdaq --top 200 --exclude-etf
```

### 호출 제한

yfinance / Yahoo Finance는 짧은 시간에 호출이 몰리면 429 또는 rate limit 오류를 낼 수
있습니다. 수집기는 요청 간 최소 대기 시간과 60초 슬라이딩 윈도우 상한을 함께 적용합니다.

```bash
uv run python -m stock_crawler fetch --market nasdaq --top 200 \
    --request-delay 0.3 \
    --max-per-minute 30
```

- `--request-delay`: yfinance 호출 사이 최소 대기 시간(초). 기본값은 `0.3`입니다.
- `--max-per-minute`: 최근 60초 동안 허용할 최대 호출 수. 기본값은 `30`이며, `0`이면
  분당 상한을 끕니다.
- 재시도 전에도 같은 throttle이 적용됩니다.
- `429`, `Too Many Requests`, `rate limit` 계열 오류는 더 긴 백오프로 재시도합니다.

## 스케줄링

스케줄러는 포그라운드에서 블로킹 실행됩니다. 장기 실행이 필요하면 `tmux`, `launchd`,
`systemd`, OS cron 같은 실행 환경과 함께 사용하세요.

```bash
# 매일 18:00 Asia/Seoul에 KOSPI 수집
uv run python -m stock_crawler schedule --market kospi --top 200 --at 18:00 --timezone Asia/Seoul

# 매일 07:00 Asia/Seoul에 NASDAQ 수집
uv run python -m stock_crawler schedule --market nasdaq --top 200 --at 07:00 --timezone Asia/Seoul

# 24시간 간격으로 실행
uv run python -m stock_crawler schedule --market kospi --top 200 --interval-hours 24

# 시작 전에 즉시 한 번 실행
uv run python -m stock_crawler schedule --market kospi --top 200 --at 18:00 --run-now
```

## 단기 매매 신호 분석

분석기는 `data/{market}/{ticker}.csv`에 저장된 OHLCV를 읽어 1일~1주일 정도의 단기
horizon에 맞춘 신호를 계산합니다. 결과는 투자 조언이 아니라 기술 지표 기반 계산 결과입니다.

사용 가능한 전략:

| 전략 | 설명 |
|---|---|
| `rsi` | RSI(7) 평균회귀 |
| `ema` | EMA(5) / EMA(20) 크로스오버 |
| `bollinger` | Bollinger Band(10, 2σ) 상하단 돌파/회귀 |
| `volume` | 거래량 스파이크와 1일 ROC 결합 |
| `composite` | 위 4개 전략 평균. 기본값 |

```bash
# 단일 종목 분석
uv run python -m stock_analyzer analyze 005930 --market kospi --strategy composite
uv run python -m stock_analyzer analyze AAPL --market nasdaq --strategy ema

# 최근 120개 거래일만 사용
uv run python -m stock_analyzer analyze 005930 --market kospi --lookback-days 120

# 시장 전체 스캔 후 data/{market}/_signals/{YYYY-MM-DD}.csv 저장
uv run python -m stock_analyzer scan --market kospi --top 200 --strategy composite --show-top 20

# 저장 없이 콘솔 출력만
uv run python -m stock_analyzer scan --market nasdaq --top 100 --no-save --show-top 20
```

신호 점수는 `-1.0`에서 `+1.0` 범위입니다.

- `buy`: 점수가 양의 임계값 이상
- `sell`: 점수가 음의 임계값 이하
- `hold`: 신호가 약하거나 데이터가 부족한 경우

## 데이터 레이아웃

```text
data/
├── _tickers/
│   ├── kospi_top200.csv
│   ├── kospi_top200_no_etf.csv
│   ├── nasdaq_top200.csv
│   └── nasdaq_top200_no_etf.csv
├── kospi/
│   ├── 005930.csv
│   ├── 000660.csv
│   └── _signals/
│       └── 2026-05-10.csv
└── nasdaq/
    ├── AAPL.csv
    ├── MSFT.csv
    └── _signals/
        └── 2026-05-10.csv
```

종목 CSV 컬럼:

| 컬럼 | 설명 |
|---|---|
| `date` | 거래일 (`YYYY-MM-DD`) |
| `open` | 시가 |
| `high` | 고가 |
| `low` | 저가 |
| `close` | 종가. yfinance 비조정가 |
| `volume` | 거래량 |

신호 CSV 주요 컬럼:

| 컬럼 | 설명 |
|---|---|
| `as_of_date` | 신호 산출일 (`YYYY-MM-DD`) |
| `ticker` | 종목 코드 |
| `name` | 종목명 |
| `signal` | `buy`, `sell`, `hold` |
| `score` | `-1.0`부터 `+1.0` 사이 점수 |
| `reasons` | 전략별 판단 근거 |
| 그 외 | `rsi`, `ema_fast`, `ema_slow`, `bb_*`, `volume_ratio`, `roc1`, `atr7`, `roc5`, `stop_loss` 등 |

저장 규칙:

- CSV는 index 없이 저장됩니다.
- 종목 CSV는 `date` 기준 오름차순으로 정렬됩니다.
- 같은 날짜가 중복되면 새로 받은 값이 우선합니다.
- KOSPI와 NASDAQ 모두 yfinance `auto_adjust=False`를 사용하므로 배당/액분 보정이 필요하면
  별도 조정 단계가 필요합니다.

## 개발 / 테스트

핵심 순수 로직에 대한 단위 테스트가 `tests/`에 있으며, 소스 패키지와 같은 구조로
`tests/stock_crawler/`(수집기)와 `tests/stock_analyzer/`(분석기)로 나뉩니다.

```bash
# 전체 테스트
uv run pytest

# 린트 / 포맷 검사
uv run ruff check .
uv run ruff format --check .
```

변경 범위별 빠른 확인:

```bash
# 수집기 관련 변경
uv run pytest tests/stock_crawler

# 분석기 관련 변경
uv run pytest tests/stock_analyzer

# 특정 모듈만
uv run pytest tests/stock_analyzer/test_indicators.py tests/stock_analyzer/test_strategies.py
```

외부 데이터 연동까지 확인해야 할 때는 소량으로 실행하세요.

```bash
uv run python -m stock_crawler fetch --market kospi --top 5
uv run python -m stock_crawler fetch --market nasdaq --top 5
uv run python -m stock_analyzer scan --market kospi --top 5 --show-top 5
```

## 참고 / 한계

- 모든 데이터 소스는 무료이며 로그인이나 API 키가 필요 없습니다.
- Yahoo Finance, Naver Finance, nasdaq.com screener는 공식 보장 API가 아니므로 일시 차단,
  응답 구조 변경, 데이터 누락이 발생할 수 있습니다.
- 실패한 종목은 수집 결과 요약에 기록되며, 다음 실행에서 다시 시도할 수 있습니다.
- 한국 종목 코드는 6자리 숫자(예: `005930`), NASDAQ 종목은 알파벳 심볼(예: `AAPL`)로
  저장됩니다.
- `stock_analyzer`의 신호는 기술 지표 계산 결과이며, 매매 성과를 보장하지 않습니다.
