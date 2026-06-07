# AGENTS.md

이 문서는 AI 에이전트가 이 레포지터리에서 작업할 때 따라야 하는 프로젝트별 가이드입니다.
코드를 바꾸기 전에 먼저 이 파일과 `README.md`, `pyproject.toml`을 함께 확인하세요.

---

## 프로젝트 개요

KOSPI / NASDAQ 시가총액 TOP-N 종목의 **일봉 OHLCV** 데이터를 무료 소스에서 수집하고,
저장된 CSV를 기반으로 단기 매매 신호를 계산하는 Python CLI 프로젝트입니다.

| 경로 | 역할 |
|---|---|
| `stock_crawler/` | 티커 수집, 일봉 OHLCV 다운로드, 증분 저장, 스케줄링 |
| `stock_analyzer/` | 저장된 OHLCV CSV 로드, 기술 지표 계산, 매수/매도/관망 신호 생성 |
| `stock_crawler/__main__.py` | `python -m stock_crawler` 진입점 (`stock_crawler.cli:app`) |
| `stock_analyzer/__main__.py` | `python -m stock_analyzer` 진입점 (`stock_analyzer.cli:app`) |
| `tests/` | 순수 로직 중심 단위 테스트 |

---

## 기술 스택과 실행 원칙

- Python **3.13+** 프로젝트입니다.
- 패키지 매니저는 **uv 전용**입니다. `pip install`을 사용하지 마세요.
- 린트/포맷은 **ruff**를 사용합니다.
- CLI는 **Typer**, 데이터 처리는 **pandas**, HTTP는 **requests**, OHLCV 다운로드는
  **yfinance**를 사용합니다.
- 외부 데이터 소스는 무료/비공식 엔드포인트입니다. 응답 스키마 변경, 429, 일시 장애 가능성을
  항상 고려하세요.

기본 개발 명령:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

---

## 데이터 소스

| 대상 | 구현 | 주의점 |
|---|---|---|
| KOSPI TOP-N | Naver Finance 시가총액 HTML 스크래핑 | 페이지 인코딩은 `euc-kr`, 종목 코드는 6자리 |
| KOSPI ETF 목록 | Naver ETF JSON 엔드포인트 | `--exclude-etf`에서 차집합 필터링 |
| NASDAQ TOP-N | nasdaq.com screener JSON API | 비공식 API라 응답 구조 변경 가능 |
| NASDAQ ETF 목록 | nasdaq.com ETF screener JSON API | `--exclude-etf`에서 차집합 필터링 |
| OHLCV | yfinance `Ticker.history()` | KOSPI는 Yahoo 심볼에 `.KS` 접미사 사용 |

KOSPI 일봉은 현재 pykrx가 아니라 yfinance를 통해 수집합니다. pykrx 기준 날짜 형식 같은
가정을 새 코드에 들여오지 마세요.

---

## 모듈 구조

### `stock_crawler/`

최상위에는 공유 모듈과 진입점만 두고, 역할이 또렷한 모듈은 하위 패키지로 묶는다.

| 파일 | 역할 |
|---|---|
| `config.py` | `Market`, `CrawlConfig`, 데이터/티커/로그 경로 상수 |
| `storage.py` | 종목 CSV 경로 계산, 마지막 수집일 조회, upsert 저장 |
| `cli.py` | `tickers`, `fetch`, `schedule` CLI |
| `sources/fetcher.py` | yfinance 심볼 변환과 OHLCV 다운로드 |
| `sources/tickers.py` | KOSPI/NASDAQ TOP-N 티커 수집 및 캐시, ETF 제외 처리 |
| `pipeline/collector.py` | 티커 해석, 증분 시작일 계산, throttle, 재시도, 저장 오케스트레이션 |
| `pipeline/scheduler.py` | apscheduler 기반 cron/interval 스케줄링 |
| `pipeline/throttle.py` | 호출 간격/분당 호출 수 제한. 멀티스레드 안전성을 유지해야 함 |

### `stock_analyzer/`

| 파일 | 역할 |
|---|---|
| `data.py` | CSV 로드 및 OHLCV 컬럼 검증 |
| `scanner.py` | 시장 전체 스캔, 신호 CSV 저장 |
| `cli.py` | `analyze`, `scan` CLI |
| `signals/indicators.py` | RSI, EMA, Bollinger Band, ATR, Volume spike, ROC 계산 |
| `signals/strategies.py` | `rsi`, `ema`, `bollinger`, `volume`, `composite` 전략 |

---

## 데이터 레이아웃과 CSV 계약

```text
data/
├── _tickers/
│   ├── kospi_top200.csv
│   ├── kospi_top200_no_etf.csv
│   ├── nasdaq_top200.csv
│   └── nasdaq_top200_no_etf.csv
├── kospi/
│   ├── 005930.csv
│   └── _signals/
│       └── 2026-05-10.csv
└── nasdaq/
    ├── AAPL.csv
    └── _signals/
        └── 2026-05-10.csv
```

종목 CSV:

```text
date,open,high,low,close,volume
```

신호 CSV:

```text
as_of_date,ticker,name,signal,score,reasons,...
```

데이터 저장 규칙:

- CSV는 UTF-8, `index=False`로 저장합니다.
- 종목 CSV는 `date` 기준 오름차순이어야 합니다.
- 같은 거래일이 중복되면 새로 받은 값이 우선합니다.
- 이미 저장된 파일이 있으면 마지막 거래일 다음 날부터만 증분 수집합니다.
- `data/` 산출물은 실행 결과물입니다. 사용자 요청 없이 대량 변경하거나 삭제하지 마세요.

---

## 주요 CLI

```bash
# TOP-N 티커 확인 및 캐시
uv run python -m stock_crawler tickers --market kospi --top 200
uv run python -m stock_crawler tickers --market nasdaq --top 200

# ETF 제외 TOP-N
uv run python -m stock_crawler tickers --market kospi --top 200 --exclude-etf

# 일봉 1회 수집
uv run python -m stock_crawler fetch --market kospi --top 200
uv run python -m stock_crawler fetch --market nasdaq --top 200

# 티커 캐시를 새로 받고 수집
uv run python -m stock_crawler fetch --market kospi --top 200 --refresh-tickers

# 호출 제한 조정
uv run python -m stock_crawler fetch --market nasdaq --top 200 --request-delay 0.3 --max-per-minute 30

# 정기 스케줄. 포그라운드 블로킹 프로세스
uv run python -m stock_crawler schedule --market kospi --top 200 --at 18:00 --timezone Asia/Seoul
uv run python -m stock_crawler schedule --market nasdaq --top 200 --at 07:00 --timezone Asia/Seoul

# 단일 종목 신호 분석
uv run python -m stock_analyzer analyze 005930 --market kospi --strategy composite

# 시장 전체 스캔
uv run python -m stock_analyzer scan --market kospi --top 200 --strategy composite --show-top 20
```

네트워크를 사용하는 명령(`tickers`, `fetch`, `scan` 중 티커 캐시가 없을 때)은 실행 시간이 길거나
외부 서비스 상태에 따라 실패할 수 있습니다. 코드 변경 검증에는 우선 단위 테스트를 사용하고,
실제 수집은 필요한 경우 소량(`--top 5`)으로 제한하세요.

---

## 변경 원칙

- 기존 공개 CLI 옵션, CSV 컬럼명, 데이터 경로 계약을 깨지 마세요.
- 새 기능은 가능한 한 `CrawlConfig` 또는 기존 CLI 옵션 패턴에 맞춥니다.
- 새 함수에는 타입 힌트를 추가하세요.
- 불필요한 추상화나 대규모 리팩터링을 피하고, 요청 범위에 직접 연결되는 파일만 수정하세요.
- 외부 API 응답 파싱 코드는 방어적으로 작성하되, 예외를 조용히 삼켜 잘못된 데이터를 저장하지 마세요.
- 금융 신호 로직은 투자 조언이 아니라 계산 결과입니다. 문구를 추가할 때 확정적 수익 표현을 넣지 마세요.
- 날짜/타임존을 다룰 때는 시장 휴장일과 한국/미국 시차를 고려하세요.

---

## 핵심 불변 조건

| 영역 | 반드시 지킬 것 |
|---|---|
| `throttle.py` | `Throttler.wait()`의 `threading.Lock` 기반 동시성 안전성을 유지 |
| `fetcher.py` | KOSPI는 yfinance 호출 전 `{ticker}.KS`로 변환 |
| `storage.py` | 저장 시 `date` 정규화, 날짜 중복 제거, 오름차순 정렬, `index=False` 유지 |
| `tickers.py` | 티커 캐시는 `CrawlConfig.market_tickers_file` 규칙을 사용 |
| `collector.py` | 한 종목 실패가 전체 수집을 중단하지 않도록 실패 목록에 누적 |
| `strategies.py` | 모든 전략 점수는 `-1.0 <= score <= 1.0` 범위 유지 |
| `scanner.py` | 스캔 결과는 `abs(score)` 내림차순 정렬 유지 |

---

## 코딩 스타일

- ruff 설정은 `pyproject.toml`을 기준으로 합니다.
- 선택된 lint 규칙: `E`, `W`, `F`, `I`, `UP`, `B`, `C4`, `BLE`, `S`
- 전역 ignore: `B008` (Typer `Option()` 기본값 패턴)
- 테스트 파일 ignore: `S101` (`assert` 허용)
- 포맷: double quote, space indent, line length 100
- `random.uniform` 등 비보안 지터 목적의 난수 사용에는 `# noqa: S311`을 사용하세요.
  `# nosec`는 사용하지 마세요.
- 주석은 한국어 또는 영어 모두 가능하지만, 코드만으로 명확하면 생략하세요.

---

## 테스트와 검증

일반 코드 변경 후 기본 검증:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

테스트는 소스와 같은 구조로 `tests/stock_crawler/`·`tests/stock_analyzer/`로 나뉜다.
공유 픽스처(`make_ohlcv`)는 `tests/conftest.py`에 두어 양쪽 모두에서 쓸 수 있다.

변경 범위별 추가 검증:

```bash
# 수집기 / 분석기 전체
uv run pytest tests/stock_crawler
uv run pytest tests/stock_analyzer

# 저장/CSV 로직
uv run pytest tests/stock_crawler/test_storage.py tests/stock_analyzer/test_data.py

# throttle 변경
uv run pytest tests/stock_crawler/test_throttle.py

# 지표/전략 변경
uv run pytest tests/stock_analyzer/test_indicators.py tests/stock_analyzer/test_strategies.py

# 설정/경로 변경
uv run pytest tests/stock_crawler/test_config.py
```

외부 연동까지 확인해야 할 때만 소량으로 실행:

```bash
uv run python -m stock_crawler fetch --market kospi --top 5
uv run python -m stock_crawler fetch --market nasdaq --top 5
uv run python -m stock_analyzer scan --market kospi --top 5 --show-top 5
```

네트워크 제한이나 외부 서비스 장애로 실행하지 못한 검증은 최종 응답에 명확히 남기세요.

---

## 에이전트 작업 절차

1. `git status --short`로 사용자 변경 사항을 먼저 확인합니다.
2. 관련 파일을 읽고 현재 구현과 문서/요청이 맞는지 확인합니다.
3. 변경 범위를 작게 정하고, 공개 계약(CLI, CSV, 경로, 전략 점수)을 유지합니다.
4. 코드 변경 시 테스트를 우선 추가하거나 기존 테스트를 갱신합니다.
5. 가능한 검증 명령을 실행합니다.
6. 최종 응답에는 변경한 파일, 검증 결과, 실행하지 못한 검증이 있으면 그 이유를 짧게 적습니다.

사용자 변경 사항을 되돌리지 마세요. unrelated 변경이 보이면 그대로 두고, 같은 파일에서 충돌할 때만
현재 내용을 읽고 그 위에 맞춰 작업하세요.

---

## 리뷰 요청 시 기준

사용자가 "리뷰"를 요청하면 코드 리뷰 모드로 답변하세요.

- 버그, 회귀 위험, 데이터 손상 가능성, 누락된 테스트를 우선순위로 봅니다.
- 발견 사항을 심각도 순으로 먼저 제시하고, 파일/라인을 함께 적습니다.
- 문제가 없으면 "발견된 주요 이슈 없음"이라고 명확히 말하고 남은 리스크를 적습니다.
- 스타일 취향이나 불필요한 리팩터링 제안은 핵심 이슈 뒤로 미룹니다.
