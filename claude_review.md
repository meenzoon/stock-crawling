# 코드 리뷰 — stock_crawler / stock_analyzer

> 작성: 2026-05-29 · 대상: 현재 `main` 브랜치 전체 소스
> 방법: 전체 모듈 정독 + 의심 항목 실제 동작 검증(false positive 제거)

## 요약

이번 세션에서 "한 종목/한 파일의 실패가 전체 실행을 중단시키면 안 된다"는 계약을 기준으로
수집기 쪽 경계(collector 종목 단위 try, fetcher OHLCV 컬럼 검증, tickers 캐시 컬럼 검증)를
연달아 보강했다. 같은 관점으로 **분석기(stock_analyzer) 읽기 경계**를 점검한 결과,
수집기에서 이미 고친 것과 **동일한 부류의 버그**가 분석기 적재 경로에 남아 있다.

| # | 심각도 | 위치 | 한 줄 요약 |
|---|--------|------|-----------|
| 1 | Medium | `stock_analyzer/data.py:48-53` | `load_ohlcv` 가 문서화된 계약을 어기고 손상 CSV 에서 예외 전파 → scan 전체 중단 |
| 2 | Low | `stock_analyzer/scanner.py:115-118`, `cli.py:110` | 빈 universe 일 때 `sort_values("score")` / `["signal"]` 가 KeyError |

---

## Finding 1 — (Medium) `load_ohlcv` 가 계약을 위반해 손상 CSV 에서 예외를 던짐

**위치:** `stock_analyzer/data.py:48-53` · **영향 경로:** `stock_analyzer/scanner.py:104`

`load_ohlcv` 의 docstring 은 다음과 같이 명시한다.

> *"파일이 없거나 **읽을 수 없으면** 빈 DataFrame 을 반환한다(예외를 던지지 않는다)."*

그러나 구현은 `not p.exists()`(파일 없음)만 막고, 실제 읽기는 보호하지 않는다.

```python
df = pd.read_csv(p, parse_dates=["date"])
```

`date` 컬럼이 없는 손상 CSV 면 다음이 발생한다(pandas 2.3.3 에서 재현 확인):

```
ValueError: Missing column provided to 'parse_dates': 'date'
```

깨진 CSV·파싱 오류도 동일하게 전파된다. 그리고 `scanner.scan` 은 이 호출을
**종목 단위 try 블록 밖**(`scanner.py:104`)에서 수행하며, try 는 `run_strategy` 만 감싼다.
따라서 **한 종목의 CSV 가 손상되면 scan 전체가 중단**된다.

> 비교: `stock_crawler/storage.py:44-48` 의 `last_recorded_date` 는 이미 읽기를 try/except 로
> 감싸 실패 시 graceful 하게 처리한다. 읽기 경계 처리가 **수집기 ↔ 분석기 간 비대칭**이다.

**권장 수정** — `last_recorded_date` 패턴을 그대로 따른다.

```python
try:
    df = pd.read_csv(p, parse_dates=["date"])
except Exception as e:  # noqa: BLE001
    log.warning("Could not read %s, treating as empty: %s", p, e)
    return pd.DataFrame()
```

손상 파일은 빈 프레임 → `scanner.scan` 의 기존 `df.empty` 분기(`scanner.py:105`)에서
`hold / "no data"` 로 자연스럽게 격하되어 전체 scan 이 계속된다.

---

## Finding 2 — (Low) 빈 universe 일 때 scan/CLI 가 KeyError 로 죽음

**위치:** `stock_analyzer/scanner.py:115-118`, `stock_analyzer/cli.py:110`

`universe` 가 비면 루프가 돌지 않아 `rows == []` 이고, `pd.DataFrame([])` 는 **컬럼이 없는**
빈 프레임이다. 이어지는 정렬에서 죽는다(재현 확인).

```
result_df.sort_values("score", ...)   # KeyError: 'score'
result_df["signal"].value_counts()    # cli.py:110, 동일 원인
```

현실에서 `resolve_tickers` 는 보통 비어있지 않은 결과를 반환(없으면 `RuntimeError`)하므로
발생 확률은 낮지만, 방어가 한 줄이면 충분하다.

**권장 수정** — 정렬 전 빈 프레임 가드.

```python
result_df = pd.DataFrame(rows)
if not result_df.empty:
    result_df = result_df.sort_values(
        "score", key=lambda s: s.abs(), ascending=False
    ).reset_index(drop=True)
```

`cli.py` 의 counts 집계도 `... if not result_df.empty else {}` 로 보호.

---

## 점검했으나 문제 아님 (false positive 제거)

- **`tickers.py:238` `pd.Timestamp.utcnow()`** — pandas 2.3.3 에서 `-W all` 로 확인한 결과
  deprecation 경고를 내지 않으며 기능상 정상. 변경 불필요.
- collector 종목 단위 try, fetcher OHLCV 컬럼 검증, tickers 캐시 컬럼 검증,
  RSI flat 구간 50 처리, storage `date` 컬럼 명시적 에러 — **이번 세션에서 이미 수정 완료**.
- `Throttler`(lock + 슬라이딩 윈도우), `scheduler._run`(예외 격리) — 이상 없음.

---

## 권장 적용 범위

| # | 파일 | 변경 |
|---|------|------|
| 1 | `stock_analyzer/data.py` | `pd.read_csv` 를 try/except 로 감싸 실패 시 빈 프레임 반환 |
| 2 | `stock_analyzer/scanner.py`, `stock_analyzer/cli.py` | 빈 결과 프레임 가드(정렬·counts) |

## 검증 방법

1. `tests/test_data.py` 에 회귀 테스트 추가
   - `date` 컬럼 없는 손상 CSV → `load_ohlcv` 가 예외 없이 빈 DataFrame 반환
   - (선택) 빈 universe → `scan` 이 KeyError 없이 빈 프레임 반환
2. `uv run pytest -q` 전체 통과
3. `uv run pre-commit run --all-files` (Ruff lint/format) 통과

> Finding 2 는 Low 라 원하면 제외 가능. Finding 1 만 적용해도 무방하다.
