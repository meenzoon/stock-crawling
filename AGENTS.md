# AGENTS.md

AI 에이전트가 이 레포지터리에서 작업할 때 참고하는 가이드입니다.

---

## 프로젝트 개요

KOSPI / NASDAQ 시가총액 TOP-N 종목의 **일봉 OHLCV** 데이터를 무료 소스에서 수집하는 크롤러 + 단기 매매 신호 분석기.

| 패키지 | 역할 |
|---|---|
| `stock_crawler/` | 티커 수집 → 일봉 OHLCV 다운로드 → CSV 저장 |
| `stock_analyzer/` | 저장된 CSV로 기술 지표 산출 → 매수/매도/관망 신호 생성 |
| `main.py` | `stock_crawler` CLI 진입점 |
| `main_analyze.py` | `stock_analyzer` CLI 진입점 |

---

## 환경 설정

```bash
# 의존성 설치 (Python 3.13+ 필요)
uv sync

# lint + format 검사
uv run ruff check .
uv run ruff format --check .
```

패키지 매니저는 **uv** 전용. `pip install` 사용 금지.

---

## 모듈 구조

### stock_crawler/

| 파일 | 역할 |
|---|---|
| `config.py` | 전역 상수 (데이터 경로, 기본값) |
| `tickers.py` | KOSPI(pykrx) / NASDAQ(nasdaq.com API) TOP-N 티커 수집 |
| `fetcher.py` | yfinance / pykrx로 OHLCV 다운로드, 증분 업데이트 로직 |
| `storage.py` | CSV 읽기·쓰기, 마지막 수집일 조회 |
| `throttle.py` | 호출 간격·분당 횟수 제한 (429 방지) |
| `collector.py` | fetcher + throttle 조합, 전체 종목 순회 |
| `scheduler.py` | apscheduler 기반 cron / interval 스케줄링 |
| `cli.py` | Typer CLI (`tickers`, `fetch`, `schedule` 커맨드) |

### stock_analyzer/

| 파일 | 역할 |
|---|---|
| `data.py` | CSV 로드, OHLCV 검증 |
| `indicators.py` | RSI, EMA, Bollinger Band, ATR, Volume spike, ROC 산출 |
| `strategies.py` | 개별 전략(`rsi`, `ema`, `bollinger`, `volume`) + `composite` |
| `scanner.py` | 시장 전체 종목 일괄 스캔 → 신호 CSV 저장 |
| `cli.py` | Typer CLI (`analyze`, `scan` 커맨드) |

---

## 데이터 레이아웃

```
data/
├── _tickers/
│   ├── kospi_top200.csv
│   └── nasdaq_top200.csv
├── kospi/
│   ├── 005930.csv          # date, open, high, low, close, volume
│   └── _signals/
│       └── 2026-05-10.csv
└── nasdaq/
    └── AAPL.csv
```

- 종목 CSV 컬럼: `date | open | high | low | close | volume`
- 신호 CSV 컬럼: `as_of_date | ticker | name | signal | score | reasons | ...`
- 파일이 이미 존재하면 마지막 날짜 이후만 **증분 추가**.

---

## 주요 실행 커맨드

```bash
# 티커 목록 확인
uv run python main.py tickers --market kospi --top 200

# 일봉 1회 수집
uv run python main.py fetch --market kospi --top 200
uv run python main.py fetch --market nasdaq --top 200

# 정기 스케줄 (포그라운드 블로킹)
uv run python main.py schedule --market kospi --top 200 --at 18:00 --timezone Asia/Seoul

# 단일 종목 신호 분석
uv run python main_analyze.py analyze 005930 --market kospi

# 시장 전체 스캔
uv run python main_analyze.py scan --market kospi --top 200 --show-top 20
```

---

## 코딩 규칙

- **lint**: ruff (`E`, `W`, `F`, `I`, `UP`, `B`, `C4`, `BLE`, `S`)
- **format**: ruff format (double quote, space indent, line-length 100)
- **보안 예외**: `random.uniform` 지터 억제는 `# noqa: S311` 사용 (`# nosec` 사용 금지)
- **주석**: 한국어 허용. `# WHY`가 자명하면 주석 생략.
- **타입**: 새 함수에는 타입 힌트 추가 권장.
- pre-commit hooks: `ruff check --fix`, `ruff format` (커밋 전 자동 실행)

---

## 변경 시 주의 사항

| 영역 | 주의점 |
|---|---|
| `throttle.py` | `Throttler`는 멀티스레드 환경에서 호출됨 (`threading.Lock` 보유) |
| `fetcher.py` | pykrx 호출 날짜 형식은 `YYYYMMDD`; yfinance는 `datetime` / ISO 문자열 |
| `storage.py` | CSV 인코딩 UTF-8, index 없이 저장 (`index=False`) |
| `tickers.py` | NASDAQ 스크리너는 비공식 API — 응답 스키마 변경 가능성 있음 |
| `strategies.py` | 신호 score 범위는 반드시 `-1.0 ~ +1.0` 유지 |

---

## 테스트

현재 공식 테스트 스위트 없음. 변경 후 아래로 동작 확인:

```bash
# lint 통과 확인
uv run ruff check .

# 실제 수집 소량 테스트 (상위 5종목)
uv run python main.py fetch --market kospi --top 5
uv run python main.py fetch --market nasdaq --top 5

# 신호 분석 동작 확인
uv run python main_analyze.py scan --market kospi --top 5 --show-top 5
```
