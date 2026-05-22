# Claude Code Skills & Sub-Agents — stock-crawling

이 프로젝트에서 Claude Code를 사용할 때 권장하는 내장 Skill, Sub-Agent, 그리고 추가하면 좋을 커스텀 Sub-Agent를 정리합니다.

## 프로젝트 특성 요약

`stock-crawling`은 KOSPI/NASDAQ TOP-N 일봉 OHLCV를 무료/비공식 외부 API에서 수집하고, 저장된 CSV로 단기 매매 신호를 계산하는 Python CLI 프로젝트입니다.

핵심 작업 특성:
- 외부 비공식 API 의존(Naver, nasdaq.com, yfinance) → 스키마 변경/429/일시 장애가 빈번
- CSV 계약(컬럼, 정렬, `index=False`, 증분 저장) 유지가 중요
- `throttle.py`는 `threading.Lock` 기반 동시성 안전성 유지 필수
- ruff `S` 룰(보안) 활성화, `random.uniform` 같은 비보안 난수에는 `# noqa: S311` 명시 필요
- `CLAUDE.md`가 "Simplicity First / Surgical Changes / Goal-Driven Execution"을 강하게 강조
- `AGENTS.md`에 리뷰 모드/기준이 명문화

---

## 1. 내장 Skill 우선 추천

### 강력 추천

- **`/simplify`**
  - `CLAUDE.md`의 "Simplicity First", "Surgical Changes" 원칙과 1:1 매핑됩니다.
  - 변경된 코드의 재사용/품질을 점검하고 과도한 추상화·사양 외 코드를 정리합니다.
  - 활용 시점: `collector.py`, `scanner.py`, `strategies.py`처럼 한 줄 수정이 주변 정리로 번지기 쉬운 파일을 건드린 직후.

- **`/review`**
  - `AGENTS.md`의 "리뷰 요청 시 기준"(버그/회귀/데이터 손상/누락 테스트 우선)에 그대로 부합합니다.
  - PR 만들기 전 self-review 단계에서 호출하면 효과적.

- **`/security-review`**
  - 외부 비공식 엔드포인트 파싱, `requests` 호출, ruff `S` 룰 활성화 환경과 잘 맞습니다.
  - 새 데이터 소스 추가나 `fetcher.py`/`tickers.py`의 HTTP 처리 변경 시 호출 권장.

- **`/fewer-permission-prompts`**
  - 이 프로젝트에서 반복되는 read-only 명령(`uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `git status --short`)을 `.claude/settings.json` 허용 목록에 자동 등록해 권한 프롬프트를 줄여줍니다.

### 상황별 추천

- **`/schedule`**
  - 외부 시장 마감 시각(KOSPI 18:00, NASDAQ 07:00 KST)에 맞춘 보조 작업 정기 실행에 사용 가능. 단, 운영용 스케줄은 이미 `scheduler.py`(apscheduler)에 있으므로 중복 운영하지 말고 "외부 API 회귀 감시" 같은 보조 용도로만 사용하는 것을 권장.

- **`/loop`**
  - 외부 응답 스키마 변동 감시, flaky 테스트 재현용 반복 실행에 활용.

### 추천하지 않음 (관련도 낮음)

- `/claude-api`, `/keybindings-help`, `/init`(이미 `CLAUDE.md` 존재), `/update-config`(필요할 때 단발성으로만)

---

## 2. 내장 Sub-Agent 활용 가이드

- **`Explore`** — 코드베이스가 `stock_crawler/`, `stock_analyzer/`, `tests/`로 모듈화되어 있어 "어디서 OHLCV를 정규화하나?", "신호 score 범위 검증은 어디서?" 같은 광범위 탐색에 효율적. `CLAUDE.md`의 "Think Before Coding"과 잘 맞음.

- **`Plan`** — `collector.py`처럼 throttle/재시도/저장이 얽힌 파일을 바꿀 때 영향 범위 파악과 단계 분해에 사용.

- **`general-purpose`** — 한 번에 탐색 + 편집이 필요한 다단계 리팩터링 시.

- **`claude-code-guide`** — Claude Code 자체 설정/hook/MCP 관련 질문 전담.

---

## 3. 만들면 유용할 커스텀 Sub-Agent (선택)

`.claude/agents/`에 추가하면 이 프로젝트의 재발 가능 이슈를 자동 감시할 수 있습니다. 모두 read-only + 테스트 실행만 하므로 `tools: Read, Grep, Bash` 정도 권한이면 충분합니다.

### 3-1. `csv-contract-checker`

- 트리거: `storage.py`, `scanner.py`, `data.py` 또는 `data/` 산출물 형식 관련 변경
- 점검 항목:
  - `date,open,high,low,close,volume` 컬럼 보존
  - 종목 CSV `date` 오름차순 정렬
  - 중복 거래일 처리(새 값 우선)
  - `index=False` 저장
  - 증분 시작일 계산 로직 유지
- 도구: Read, Grep, Bash(pytest 일부)

### 3-2. `external-api-resilience-reviewer`

- 트리거: `tickers.py`, `fetcher.py`, 외부 HTTP/JSON 파싱 변경
- 점검 항목:
  - 429/일시 장애 재시도
  - 응답 스키마 변경 방어
  - KOSPI `.KS` 접미사 변환
  - `euc-kr` 인코딩 처리
  - ETF 차집합 필터링
  - 예외를 조용히 삼켜 잘못된 데이터가 저장되지 않는지
- 도구: Read, Grep

### 3-3. `throttle-concurrency-reviewer`

- 트리거: `throttle.py` 또는 `collector.py`의 멀티스레드 경로 변경
- 점검 항목:
  - `threading.Lock` 보존
  - 분당 호출 수 / 호출 간격 계약 유지
  - 데드락/레이스 가능성
- 도구: Read, Grep

### 3-4. `signal-bounds-checker`

- 트리거: `strategies.py`, `indicators.py`, `scanner.py` 변경
- 점검 항목:
  - 모든 전략 점수가 `-1.0 <= score <= 1.0` 범위
  - 스캔 결과가 `abs(score)` 내림차순 정렬
  - 신호 CSV 컬럼 스키마(`as_of_date,ticker,name,signal,score,reasons,...`)
  - 투자 조언성 단정 문구 미포함
- 도구: Read, Grep, Bash(`uv run pytest tests/test_strategies.py tests/test_indicators.py`)

---

## 4. 도입 우선순위 제안

1. (즉시) `/fewer-permission-prompts`를 한 번 실행해 반복 명령을 허용 목록에 등록
2. (즉시) 일상 워크플로우에 `/simplify` → `/review` → 필요 시 `/security-review` 도입
3. (선택) 위 커스텀 Sub-Agent 4종 중 1~2개부터 `.claude/agents/`에 추가
4. (선택) `Explore` / `Plan` Sub-Agent는 기존 그대로 사용

---

## 5. 적용 후 검증

- `.claude/settings.json`, `.claude/agents/*.md` diff 확인
- `uv run pytest`, `uv run ruff check .`로 회귀 없음 확인
- 추가한 커스텀 에이전트는 실제 변경(PR) 1건에 적용해 출력 품질과 false-positive 비율 점검
