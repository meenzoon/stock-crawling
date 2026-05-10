# CLAUDE.md

이 저장소는 KOSPI / NASDAQ 시가총액 TOP-N 종목의 일봉 OHLCV 데이터를 무료 소스에서 수집해 CSV로 저장하는 Python CLI 프로젝트입니다. Python 3.13+와 `uv`를 기준으로 개발합니다.

## 핵심 명령

```bash
uv sync
uv run python main.py --help
uv run python main.py tickers --market kospi --top 200
uv run python main.py fetch --market kospi --top 200
uv run python main.py fetch --market kospi --top 200 --request-delay 0.3 --max-per-minute 30
uv run python main.py schedule --market kospi --top 200 --at 18:00 --timezone Asia/Seoul
uv run python main_analyze.py analyze 005930 --market kospi
uv run python main_analyze.py scan --market kospi --top 200 --strategy composite
```

품질 검사:

```bash
uv run ruff check .
uv run ruff format --check .
uv run bandit -r stock_crawler/ stock_analyzer/ -c pyproject.toml
```

현재 별도 테스트 프레임워크는 설정되어 있지 않습니다. 기능 변경 시에는 가능한 작은 단위의 테스트를 추가하거나, 최소한 관련 CLI 명령을 `--top` 값을 작게 지정해 수동 검증하세요.

## 프로젝트 구조

- `main.py`: 수집기 CLI 엔트리포인트. `stock_crawler.cli.app`을 실행합니다.
- `main_analyze.py`: 분석기 CLI 엔트리포인트. `stock_analyzer.cli.app`을 실행합니다.
- `stock_crawler/cli.py`: Typer 기반 명령 정의. `fetch`, `tickers`, `schedule` 명령을 제공합니다.
- `stock_crawler/config.py`: `Market`, `CrawlConfig`, 데이터/티커/로그 경로 상수, throttle 기본값.
- `stock_crawler/tickers.py`: TOP-N 티커 해석 및 `data/_tickers/{market}_top{N}.csv` 캐시. KOSPI는 Naver Finance 시가총액 페이지, NASDAQ은 nasdaq.com 공개 screener API를 사용합니다.
- `stock_crawler/fetcher.py`: `yfinance`를 통한 일봉 OHLCV 다운로드. KOSPI 티커는 Yahoo Finance용 `.KS` 접미사를 붙입니다.
- `stock_crawler/throttle.py`: 호출 간 최소 간격, 분당 최대 호출 수, 지터를 강제하는 `Throttler`. `collector`에서 yfinance 호출 직전마다 `wait()`을 호출합니다.
- `stock_crawler/storage.py`: 종목별 CSV 경로 계산, 마지막 저장일 조회, 신규 데이터 upsert.
- `stock_crawler/collector.py`: 티커 해석, 증분 시작일 계산, throttle, 재시도(429에서는 더 긴 backoff), 저장을 묶는 수집 오케스트레이션.
- `stock_crawler/scheduler.py`: APScheduler 기반 일별/간격 실행. 포그라운드 blocking scheduler입니다.
- `stock_analyzer/`: 1일~1주일 horizon 단기 매매 신호 생성 패키지.
  - `data.py`: 저장된 CSV 로드(`stock_crawler.storage.csv_path` 재사용).
  - `indicators.py`: RSI(7), EMA, Bollinger(10, 2σ), ATR(7), ROC, volume spike (pandas로 직접 구현).
  - `strategies.py`: RSI 평균회귀, EMA 크로스오버, Bollinger 돌파, 거래량 돌파, composite 전략. `StrategyResult(signal, score, reasons, indicators)` 반환.
  - `scanner.py`: 시장 전체 종목에 전략 실행 → `data/{market}/_signals/{YYYY-MM-DD}.csv` 저장.
  - `cli.py`: `analyze` (단일 종목), `scan` (전체) 명령.
- `data/`: 실행 산출물. 티커 캐시, 종목별 OHLCV CSV, 일자별 signal CSV(`{market}/_signals/`).

## 데이터 규칙

종목 CSV는 `data/{market}/{ticker}.csv`에 저장합니다. 기본 컬럼은 다음 형태를 유지하세요.

```text
date,open,high,low,close,volume
```

- `date`는 `YYYY-MM-DD` 형식의 거래일입니다.
- `storage.upsert()`는 날짜를 normalize하고 같은 날짜는 마지막 값을 유지합니다.
- 증분 수집은 기존 CSV의 마지막 `date` 다음 날부터 시작합니다.
- 티커 캐시는 `data/_tickers/`에 저장하며, 재산정이 필요할 때만 `--refresh` 또는 `--refresh-tickers`를 사용합니다.
- 분석 신호는 `data/{market}/_signals/{YYYY-MM-DD}.csv`에 저장합니다. 핵심 컬럼은 `as_of_date,ticker,name,signal,score,reasons` 이며 그 뒤에 전략별 지표 컬럼이 붙습니다. 향후 N일 forward-return 백테스트가 가능하도록 이 스키마는 깨지 않게 유지하세요.

## 개발 지침

- 패키지/툴 관리는 `uv`를 우선 사용하세요.
- Python 스타일은 `pyproject.toml`의 Ruff 설정을 따릅니다. 줄 길이는 100자, 문자열 따옴표는 double quote입니다.
- 새 코드에서는 `CrawlConfig`의 경로 속성(`market_data_dir`, `market_tickers_file`)을 활용하고 저장 경로를 하드코딩하지 마세요.
- 수집 대상 시장은 `Market` enum을 통해 다루세요. 시장 문자열 비교를 곳곳에 흩뿌리지 않는 편이 좋습니다.
- 무료/비공식 데이터 소스는 응답 형식 변경과 일시 실패가 잦을 수 있습니다. 네트워크 호출 변경 시 timeout, header, 예외 처리, 재시도 동작을 함께 검토하세요.
- 한 종목 실패가 전체 수집을 중단하지 않도록 `collector.collect()`의 실패 누적 방식과 요약 반환 형태를 유지하세요.
- CSV 저장 로직을 변경할 때는 기존 파일과 신규 데이터 병합, 중복 날짜 제거, 날짜 정렬이 깨지지 않는지 확인하세요.
- 스케줄러는 장기 실행 foreground 프로세스입니다. 백그라운드 서비스화는 이 저장소 밖의 실행 환경 책임으로 보고, CLI 동작을 단순하게 유지하세요.

## 검증 체크리스트

변경 후 영향 범위에 따라 아래를 실행하세요.

```bash
uv run ruff check .
uv run ruff format --check .
uv run bandit -r stock_crawler/ stock_analyzer/ -c pyproject.toml
uv run python main.py tickers --market kospi --top 3
uv run python main.py fetch --market kospi --top 3
uv run python main_analyze.py scan --market kospi --top 3 --strategy composite
```

NASDAQ 관련 변경은 네트워크와 외부 API 상태에 영향을 받습니다. 실패 시 응답 구조 변경인지, 일시적 차단인지, 로컬 코드 문제인지 구분해서 확인하세요.
