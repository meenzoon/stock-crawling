# stock-crawling

KOSPI / NASDAQ 시가총액 TOP-N 종목의 **일봉 OHLCV** 데이터를 무료 소스에서 받아오는
백테스팅용 데이터 크롤러입니다.

- **KOSPI**: [`pykrx`](https://github.com/sharebook-kr/pykrx) (KRX 공식 데이터, 1995년~현재)
- **NASDAQ**: [`yfinance`](https://github.com/ranaroussi/yfinance) (Yahoo Finance, 상장 이래 전 기간 `period="max"`)
- **TOP-N 선정**: KOSPI는 `pykrx`의 시가총액 랭킹, NASDAQ는 nasdaq.com 공개 스크리너 API
- **저장**: 종목별 CSV (`data/{market}/{ticker}.csv`), 다음 실행 시 마지막 날짜 이후만 증분 수집
- **스케줄링**: `apscheduler`로 매일 정해진 시각(cron) 또는 N시간 간격(interval) 실행

## 1. 설치

Python 3.11+ / [uv](https://github.com/astral-sh/uv) 가 필요합니다.

```bash
uv sync
```

## 2. 사용법

### 2-1. TOP-N 티커 확인

```bash
uv run python main.py tickers --market kospi  --top 200
uv run python main.py tickers --market nasdaq --top 200
```

티커 목록은 `data/_tickers/{market}_top{N}.csv`에 캐시됩니다. 다시 산출하려면
`--refresh` 옵션을 붙이세요.

### 2-2. 과거 일봉 수집 (1회 실행)

```bash
# KOSPI 시총 200 종목, pykrx로 1995년부터 전체 일봉 수집
uv run python main.py fetch --market kospi --top 200

# NASDAQ 시총 200 종목, yfinance로 상장 이래 전 기간 수집
uv run python main.py fetch --market nasdaq --top 200
```

- 첫 실행: 종목당 전체 히스토리(`period="max"` 또는 1995-05-01 ~ 오늘)를 받아옵니다.
- 두 번째 실행 이후: CSV 마지막 날짜 다음 날부터만 받아 **증분 업데이트**합니다.
- 이미 수집한 종목 목록을 다시 산정하고 싶으면 `--refresh-tickers`를 붙이세요.

### 2-3. 정기 수집 스케줄링

매일 18:00에 KOSPI 시총 200 일봉을 수집:

```bash
uv run python main.py schedule --market kospi --top 200 --at 18:00 --timezone Asia/Seoul
```

미국장 마감 후(한국시간 다음날 아침 6시쯤) NASDAQ 수집:

```bash
uv run python main.py schedule --market nasdaq --top 200 --at 07:00 --timezone Asia/Seoul
```

N시간 간격으로 실행하고 싶다면:

```bash
uv run python main.py schedule --market kospi --interval-hours 24
```

스케줄러는 **포그라운드 블로킹 프로세스**입니다. 실서비스로는 `nohup`, `tmux`,
`launchd`(macOS), `systemd`, 또는 OS 크론에 `fetch` 명령을 등록해 쓰는 것도 좋습니다.
즉시 한 번 실행한 뒤 스케줄링을 시작하려면 `--run-now`를 추가하세요.

### 2-4. 옵션 전체 보기

```bash
uv run python main.py --help
uv run python main.py fetch --help
uv run python main.py schedule --help
```

## 3. 출력 데이터 형식

```
data/
├── _tickers/
│   ├── kospi_top200.csv
│   └── nasdaq_top200.csv
├── kospi/
│   ├── 005930.csv      # 삼성전자
│   ├── 000660.csv      # SK하이닉스
│   └── ...
└── nasdaq/
    ├── AAPL.csv
    ├── MSFT.csv
    └── ...
```

각 종목 CSV 컬럼:

| 컬럼   | 설명                                      |
|--------|-------------------------------------------|
| date   | 거래일 (YYYY-MM-DD)                       |
| open   | 시가                                      |
| high   | 고가                                      |
| low    | 저가                                      |
| close  | 종가 (yfinance는 비조정가, KRX는 종가)    |
| volume | 거래량                                    |

> NASDAQ은 비조정가(`auto_adjust=False`)로 받습니다. 백테스팅에서 배당/액분 보정이
> 필요하면 별도 조정 단계(`yfinance`의 `Adj Close` 또는 외부 라이브러리)를 추가하세요.

## 4. 참고 / 한계

- 모든 데이터 소스는 **무료**이며, 로그인이나 API 키가 필요 없습니다.
- 야후 파이낸스, NASDAQ 스크리너는 비공식 API이므로 일시적 차단/응답 변경이 있을
  수 있습니다. 실패한 종목은 콘솔에 출력되며 다음 실행 시 자동 재시도됩니다.
- 한국 종목 코드는 6자리 숫자(예: `005930`), 미국은 알파벳 심볼(예: `AAPL`)
  형태로 저장됩니다.
- KOSPI 일봉은 KRX 데이터를 그대로 사용하므로, 액면분할/감자 등 corporate
  action이 가격 시계열에 그대로 반영됩니다.
