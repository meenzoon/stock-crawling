# stock_crawler

KOSPI / NASDAQ 시가총액 TOP-N 종목의 **일봉 OHLCV** 를 무료/비공식 외부 소스에서 수집해
종목별 CSV 로 저장하는 패키지입니다. 첫 실행 후에는 **마지막 거래일 다음날부터 증분 수집**
합니다.

CLI 진입점은 저장소 루트의 `main.py` → `stock_crawler.cli:app` 입니다.

---

## 모듈 구성

| 파일 | 역할 |
|---|---|
| `config.py` | `Market`(StrEnum), `CrawlConfig`(frozen dataclass), 데이터/티커/로그 경로 상수 |
| `tickers.py` | KOSPI(Naver) / NASDAQ(nasdaq.com) TOP-N 종목 해석, ETF 차집합 제외, 디스크 캐시 |
| `fetcher.py` | yfinance 심볼 변환(`{ticker}.KS` for KOSPI) 및 OHLCV 다운로드 |
| `storage.py` | 종목 CSV 경로 계산, 마지막 거래일 조회, upsert 저장 |
| `throttle.py` | 호출 간 최소 간격 + 분당 호출 수 제한 (`threading.Lock` 기반 thread-safe) |
| `collector.py` | 티커 해석 → 증분 시작일 계산 → throttle → 재시도 → 저장 오케스트레이터 |
| `scheduler.py` | APScheduler `BlockingScheduler` 로 cron/interval 반복 실행 |
| `cli.py` | Typer 명령 (`tickers`, `fetch`, `schedule`) |

---

## 데이터 흐름

```
resolve_tickers (tickers.py)
        │
        ▼
collect (collector.py)
   ├── last_recorded_date (storage.py)
   ├── Throttler.wait (throttle.py)
   ├── fetch_history → fetch_yfinance (fetcher.py)
   └── upsert (storage.py)
        │
        ▼
data/{market}/{ticker}.csv
```

`schedule_daily` / `schedule_interval` (scheduler.py) 가 `collect` 를 반복 호출합니다.

---

## 외부 데이터 소스

| 대상 | 엔드포인트 | 비고 |
|---|---|---|
| KOSPI TOP-N | `finance.naver.com/sise/sise_market_sum.naver` (HTML) | 인코딩 `euc-kr`, 종목 코드 6자리, 페이지당 50행 |
| KOSPI ETF | `finance.naver.com/api/sise/etfItemList.nhn` (JSON) | `exclude_etf` 차집합 필터링 |
| NASDAQ TOP-N | `api.nasdaq.com/api/screener/stocks` (JSON) | 비공식 API, 응답 스키마 변동 가능 |
| NASDAQ ETF | `api.nasdaq.com/api/screener/etf` (JSON) | `exclude_etf` 차집합 필터링 |
| OHLCV | yfinance `Ticker.history()` | KOSPI 는 `{ticker}.KS` 접미사 |

전부 인증 없는 무료 엔드포인트입니다. **429 / 일시 장애 / 응답 스키마 변경**을 항상 가정하세요.

---

## 데이터 레이아웃

```text
data/
├── _tickers/
│   ├── kospi_top200.csv          (또는 kospi_top200_no_etf.csv)
│   └── nasdaq_top200.csv         (또는 nasdaq_top200_no_etf.csv)
├── kospi/
│   └── 005930.csv
└── nasdaq/
    └── AAPL.csv
```

종목 CSV 스키마: `date,open,high,low,close,volume` (UTF-8, `index=False`,
`date` 오름차순).

---

## CLI

```bash
# TOP-N 티커 확인 + 캐시 갱신
uv run python main.py tickers --market kospi --top 200
uv run python main.py tickers --market nasdaq --top 200 --refresh

# ETF 제외
uv run python main.py tickers --market kospi --top 200 --exclude-etf

# 일봉 1회 수집 (첫 실행 후엔 증분)
uv run python main.py fetch --market kospi --top 200
uv run python main.py fetch --market nasdaq --top 200 --refresh-tickers

# 호출 제한 조정
uv run python main.py fetch --market nasdaq --top 200 --request-delay 0.3 --max-per-minute 30

# 정기 스케줄 (포그라운드 블로킹 프로세스)
uv run python main.py schedule --market kospi --top 200 --at 18:00 --timezone Asia/Seoul
uv run python main.py schedule --market nasdaq --top 200 --interval-hours 6 --run-now
```

검증 목적이라면 `--top 5` 같은 소량으로 실행하세요.

---

## 핵심 불변 조건

| 영역 | 반드시 지킬 것 |
|---|---|
| `throttle.py` | `Throttler.wait()` 의 `Lock` 기반 동시성 안전성 유지 |
| `fetcher.py` | KOSPI 는 yfinance 호출 전 `{ticker}.KS` 로 변환 |
| `storage.py` | 저장 시 `date` 정규화 → 중복 제거(`keep="last"`) → 오름차순 정렬 → `index=False` |
| `tickers.py` | 티커 캐시 파일명은 `CrawlConfig.market_tickers_file` 규칙 (`{market}_top{N}[_no_etf].csv`) |
| `collector.py` | 한 종목 실패가 전체 수집을 중단하지 않도록 `failures` 리스트에 누적 |

---

## 동작상 주의

- `collector._fetch_with_retry` 는 rate-limit(429) 류 오류에 더 긴 백오프(`min(2^n * 5, 120s)`)를 사용합니다. 그 외 오류는 `min(2^n, 10s)`.
- `Throttler` 의 지터에는 `random.uniform` 을 사용하며 보안 목적이 아니므로 `# noqa: S311` 가 붙어 있습니다. `secrets` 로 바꾸지 마세요.
- `scheduler.py` 는 `BlockingScheduler` 입니다. 데몬화는 systemd/launchd 등 외부에서 처리합니다.
- `data/` 산출물은 실행 결과물이며 사용자 요청 없이 대량 변경/삭제하지 마세요.

---

## 검증

```bash
uv run pytest tests/test_throttle.py tests/test_storage.py tests/test_config.py
uv run ruff check .
uv run ruff format --check .
```

네트워크 의존 명령(`tickers`, `fetch`)은 외부 서비스 상태에 따라 실패할 수 있으므로 단위
테스트로 우선 검증하세요.
