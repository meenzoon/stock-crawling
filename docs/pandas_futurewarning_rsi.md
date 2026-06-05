# pandas FutureWarning 제거: RSI 계산

## 배경

`stock_analyzer.signals.indicators.rsi()`는 RSI 계산 중 손실 평균(`avg_loss`)이 0인 구간을
분모에서 제외하기 위해 `avg_loss.replace(0.0, pd.NA)`를 사용하고 있었습니다.

이 방식은 float 기반 `Series`에 `pd.NA`를 섞어 object dtype 경로를 만들 수 있고,
이후 `fillna()` 호출에서 pandas의 silent downcasting 관련 `FutureWarning`을 발생시켰습니다.

## 변경 내용

분모에서 0을 제외하는 처리를 `replace(0.0, pd.NA)` 대신
`mask(avg_loss == 0.0)`로 변경했습니다.

```python
rs = avg_gain / avg_loss.mask(avg_loss == 0.0)
```

`mask()`는 해당 위치를 pandas/numpy의 float 결측값으로 처리하므로 기존 RSI 계산 의미를
유지하면서 object dtype 변환 경로를 피합니다.

## 동작 유지

기존 테스트가 검증하던 RSI 동작은 그대로 유지됩니다.

- 상승 추세의 post-warmup RSI는 100입니다.
- 하락 추세의 post-warmup RSI는 0입니다.
- RSI 결과 길이는 입력 길이와 같습니다.
- RSI 값은 0부터 100 사이에 머뭅니다.

## 회귀 방지

`tests/test_indicators.py`에 `test_rsi_does_not_emit_futurewarning`를 추가해
RSI 계산 중 `FutureWarning`이 다시 발생하면 테스트가 실패하도록 했습니다.
