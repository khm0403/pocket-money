# 3단계 설계서: search / summary / budget set

## 1. 목표

- 옵션 방식 명령 `search`, `summary`, `budget set` 을 기존 구조(서비스 로직은 `services.py` 의 `LedgerService`, 파서·핸들러는 `cli.py`, 핸들러마다 `@handle_errors`) 위에 추가해 끝까지 동작시킨다.
- search 와 summary 는 거래 파일을 `iter_transactions()` 제너레이터로 한 건씩 읽는다. summary 는 월 합계와 카테고리별 합계만 누적한다. search 는 최신순 정렬 때문에 **조건에 맞은 거래만** 메모리에 모으며, 이 한계를 3.3에 적는다.
- import, export, README 는 이번 단계에서 만들지 않고 명령으로 등록하지도 않는다(4단계).

## 2. 대상 요구사항

| REQUIREMENTS.md 항목 | 이번 단계 충족 범위 |
| --- | --- |
| 0장 모든 명령에 `--help`, 옵션은 `--` 형식 | `search`, `summary`, `budget`, `budget set` |
| 1장 입력 검증 (날짜 / 금액 / type / 미등록 category) | search `--from/--to/--type/--category`, summary `--month`, budget set `--month/--amount` (오류 메시지 방식) |
| 2장 budgets.jsonl 영구 저장, 원자적 교체 | budget set (1단계 `BudgetStore.set` 사용) |
| 3장 #3 search | 전체 |
| 3장 #4 summary | 전체 |
| 3장 #5 budget set, summary 의 사용률(%)·초과 경고 | 전체 |
| 3장 "최신순" 정의 | search 정렬 |
| 4장 제너레이터 | search 는 제너레이터 파이프라인 + 매칭 결과만 정렬, summary 는 한 건씩 누적 |
| 4장 데코레이터, 예외 처리, 종료 코드 | 새 핸들러 3개에 `@handle_errors`. 2단계 규칙(stdout/stderr, 0/1/2) 그대로 |
| 4장 타입 힌트, 모듈화 | 새 함수·클래스 전부. 계층 규칙은 2단계와 같음 |

PDF 근거: 2장 3·4·5번(search / summary / budget), 4장 1번(search·summary 는 옵션 인자 방식 허용), 7번(search), 8번(summary), 9번(budget), 8장 budget+summary 화면 예시.

## 3. 파일/모듈 설계

### 3.0 공통 결정 (이번 단계에서 고정)

2단계 설계서 3.0 표는 모두 그대로 적용한다. 특히 **(검토 반영)** 행: 모든 새 파서는 `add_help=False` + `_with_help(...)` 로 `--help` 만 붙이고(`-h` 는 사용법 오류 2), `allow_abbrev=False`(`--cat`, `--mon` 은 오류 2), 새 중간 파서 `budget` 의 하위 파서에는 `metavar="{set}"` 을 준다. `--data-dir` 는 **말단 명령 뒤**에만 붙는다(`search`, `summary`, `budget set` 에 부모 파서로 붙이고, 중간 파서 `budget` 에는 붙이지 않는다).

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 입력 방식 | 세 명령 모두 옵션 방식. 대화형 입력 없음 | ← PDF 4장 1번(search, summary 옵션 허용), 3장 #5 `budget set --month --amount` |
| 옵션 값 타입 | argparse `type` 을 쓰지 않고 문자열로 받는다(`default=None`). 검증은 서비스가 `ValidationError` 로 해서 `[오류]/[힌트]` + 종료 코드 1로 통일 (2단계 `--limit` 과 같음) | ← 4장 예외 처리 |
| 필수 옵션 | `summary --month`, `budget set --month`, `budget set --amount` 는 `required=True`. 없으면 argparse 사용법 오류(2) | ← PDF 4장 8번 "summary --month YYYY-MM 입력을 받아", 9번 `budget set --month YYYY-MM --amount <금액>` |
| search 결과 순서 | 최신순: date 내림차순, 같은 날짜면 id 숫자 내림차순 (2단계 `_recency_key` 재사용) | ← 3장 #3, 3장 "최신순" 정의 |
| search 출력 형식 | list 와 같은 `_format_tx` (`id \| date \| type \| category \| amount \| memo`). 결과 없음: `조건에 맞는 거래가 없습니다.` | ← 3장 #3 "조건 일치 목록", PDF 8장 list 예시 |
| search 조건 결합 | 주어진 조건을 모두 만족(AND) | ← 3장 #3 "조합 가능" |
| search 조건 없음 | `ValidationError`(종료 코드 1). 조건 없이 전체를 모아 정렬하면 3.3의 메모리 한계가 "파일 전체"가 되기 때문 (총괄 확인 필요 #1) | ← 4장 제너레이터(전체 로드 금지), 3장 #3 "조건 일치 목록" |
| `--from` / `--to` | `YYYY-MM-DD` 실제 날짜(`validate_date`). **양 끝 포함**. 하나만 줘도 된다. `--from` > `--to` 는 따로 검사하지 않는다(AND 조건이라 결과 없음) (총괄 확인 필요 #2) | ← 3장 #3, 1장 입력 검증 #1, 3장 #10 export 의 `--from YYYY-MM-DD --to YYYY-MM-DD` 표기 |
| `--category` | `validate_category` 재사용: 앞뒤 공백 제거, 등록된 이름과 정확히 같아야 함(대소문자 구분). 미등록이면 오류(1) (총괄 확인 필요 #3) | ← 1장 입력 검증 #4 |
| `--type` | `validate_type` (income/expense, 대소문자 구분) | ← 1장 입력 검증 #3 |
| `--q` | 앞뒤 공백 제거 후 **메모에 부분 문자열로 포함**(`q in tx.memo`), **대소문자 구분**. 공백만/빈 값은 오류(1) (총괄 확인 필요 #4) | ← 3장 #3 "메모 키워드" |
| `--tag` | 앞뒤 공백 제거 후 **거래 태그 목록 중 하나와 정확히 일치**(`tag in tx.tags`), 대소문자 구분, 태그 하나만 받음(쉼표를 나누지 않음). 빈 값은 오류(1) (총괄 확인 필요 #4) | ← 3장 #3 `--tag`, 1장 tags |
| `summary --top` 기본값 | **3** (`DEFAULT_SUMMARY_TOP`). 1 이상의 정수만 허용, 상한 없음. 검증 문구 형식은 `--limit` 과 같음 | ← 3장 #4 `--top N`, PDF 8장 예시 `--top 3` |
| summary 대상 거래 | `date` 가 `"{month}-"` 로 시작하는 거래(해당 월의 income·expense 전부) | ← 3장 #4 |
| 사용률 | `지출 / 예산 × 100`, **소수 첫째 자리까지, 반올림(0.05 → 0.1 올림)**. float 를 쓰지 않고 정수 계산 (`6.25` → `6.3`. float `:.1f` 는 `6.2` 가 되어 반올림이 아님) | ← 3장 #5 "사용률(%)", PDF 8장 `사용률 43.0%` |
| 예산 초과 | `총 지출 > 예산` 일 때만 초과. 정확히 100.0% 는 초과 아님. 초과 시 예산 줄 바로 다음에 `[경고] 예산을 초과했습니다` (stdout, 종료 코드 0) (총괄 확인 필요 #6) | ← 3장 #5 "초과 경고", PDF 4장 9번 |
| TOP N 동점 | 금액 내림차순, 금액이 같으면 **카테고리 이름 오름차순**(파이썬 문자열 비교) | ← 3장 #4 (순서 규칙을 고정해야 출력이 결정적) |
| 금액 표기 | 천 단위 구분 없이 정수 + `원` (`3000000원`). 음수 잔액은 `-12000원` | ← PDF 8장 예시 |
| help 문구 | 한국어 한 줄. **`%` 문자를 쓰지 않는다**(argparse 가 help 를 `%` 포맷으로 처리해 3.14 는 `add_argument` 에서, 3.10 은 `--help` 때 `ValueError` 가 난다. "사용률(%)" 대신 "사용률") | ← 0장 `--help` |
| 명령 등록 순서 | 최상위: `add, list, search, summary, budget, update, delete, category`. 최상위 `metavar="{add,list,search,summary,budget,update,delete,category}"` | ← 0장, PDF 2장 기능 순서 |

### 3.1 변경하지 않는 파일

`models.py`, `storage.py`, `decorators.py`, `__main__.py`, `__init__.py` 는 **수정하지 않는다**. 필요한 재료는 이미 있다: `validate_date`, `validate_month`, `validate_type`, `parse_amount`(models), `TransactionRepository.iter_transactions`, `BudgetStore.get/set`(storage), `handle_errors`, `EXIT_OK`(decorators). 6.2 S0 에서 해시로 확인한다.

### 3.2 `budget_app/services.py` — [서비스] (추가·변경)

import 추가: `from collections.abc import Iterator`, models 에서 `validate_month`. (`dataclasses`, `heapq` 는 이미 import 되어 있다.) `print`/`input` 은 쓰지 않는다.

#### 모듈 상수 / 함수

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `DEFAULT_SUMMARY_TOP: int = 3` | summary `--top` 기본값 | ← 3장 #4, PDF 8장 `--top 3` |
| `def _parse_positive_option(value: str, option: str, example: str) -> int` | `strip` 후 `_POSITIVE_INT_RE.fullmatch`(검토 반영: `_LIMIT_RE` 에서 이름 변경) 통과 + 1 이상이면 `int` 반환. 아니면 `ValidationError(cause=f"{option} 값이 올바르지 않습니다: {value!r}", hint=f"{option} 에는 1 이상의 정수를 입력하세요 (예: {option} {example})")` | ← 3장 #2 `--limit N`, #4 `--top N` |
| `def parse_limit(value: str) -> int` (변경) | `return _parse_positive_option(value, "--limit", "20")`. **오류 문구는 2단계와 글자 하나까지 같다** | ← 3장 #2 |
| `def parse_top(value: str) -> int` | `return _parse_positive_option(value, "--top", "3")`. `"0"`, `"-1"`, `"abc"`, `"1.5"`, `""` 거부 | ← 3장 #4 `--top N` |
| `def _required_text(value: str, option: str, hint: str) -> str` | `strip` 한 값을 반환. 비었으면 `ValidationError(cause=f"{option} 값이 비어 있습니다", hint=hint)` | ← 3장 #3 `--q`, `--tag` |
| `def _top_key(item: tuple[str, int]) -> tuple[int, str]` | `(-금액, 카테고리명)`. `heapq.nsmallest` 의 key 로 써서 금액 내림차순, 동점이면 이름 오름차순 | ← 3장 #4 TOP N |
| `def _usage_rate_text(expense: int, budget: int) -> str` | `tenths = (expense * 1000 + budget // 2) // budget` (검토 반영: 같은 결과, 설명하기 쉬운 식) (= `expense*1000/budget` 를 반올림한 정수, 0.1% 단위) → `f"{tenths // 10}.{tenths % 10}"`. 예: (215000, 500000) → `"43.0"`, (1, 16) → `"6.3"`, (2, 3) → `"66.7"`, (0, 5) → `"0.0"`, (215000, 200000) → `"107.5"`. `budget` 은 저장소가 1 이상을 보장한다 | ← 3장 #5 사용률(%) |

#### `@dataclasses.dataclass(frozen=True) class SearchFilter`

search 조건 묶음. 검증을 마친(정규화된) 값만 담는다. ← 3장 #3

```python
date_from: str | None = None
date_to: str | None = None
category: str | None = None
tx_type: str | None = None
q: str | None = None
tag: str | None = None
```

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def matches(self, tx: Transaction) -> bool` | `None` 이 아닌 조건을 모두 만족하면 `True`: `tx.date >= date_from`, `tx.date <= date_to`(YYYY-MM-DD 문자열 비교 = 날짜 비교), `tx.category == category`, `tx.type == tx_type`, `q in tx.memo`, `tag in tx.tags` | ← 3장 #3 조합 가능(AND) |

#### `@dataclasses.dataclass(frozen=True) class MonthlySummary`

summary 결과. CLI 는 이 값을 글자로 바꾸기만 한다(계산은 서비스). ← 3장 #4, #5, REQUIREMENTS 6장 "services.py: 요약 계산, 예산 사용률"

```python
month: str                              # 정규화된 YYYY-MM
top: int                                # 요청한 N (헤더 "지출 TOP {top}" 에 사용)
tx_count: int                           # 해당 월 거래 수. 0 이면 "데이터 없음"
total_income: int
total_expense: int
balance: int                            # total_income - total_expense
budget: int | None                      # 예산이 없으면 None
usage_rate: str | None                  # "43.0" (예산이 없으면 None)
over_budget: bool                       # budget 이 있고 total_expense > budget
top_expenses: list[tuple[str, int]]     # (카테고리, 지출 합계), 최대 top 개, 정렬 완료
```

#### `class LedgerService` (추가 메서드)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def __init__(...)` (주석만 변경) | 코드는 그대로. "이번 단계 명령에서는 쓰지 않지만" 주석을 budget/summary 가 쓴다는 내용으로 고친다 | ← 2장 파일 3개 |
| `def search_transactions(self, *, date_from: str \| None, date_to: str \| None, category: str \| None, type_: str \| None, q: str \| None, tag: str \| None) -> list[Transaction]` | 아래 "search 처리 순서" | ← 3장 #3 |
| `def _iter_matches(self, flt: SearchFilter) -> Iterator[Transaction]` | **제너레이터.** `for tx in self.transactions.iter_transactions():` 에서 `flt.matches(tx)` 인 것만 `yield`. 거래를 모으지 않는다 | ← 3장 #3 스트리밍, 4장 제너레이터 |
| `def _iter_month(self, month: str) -> Iterator[Transaction]` | **제너레이터.** `prefix = month + "-"`; `for tx in self.transactions.iter_transactions():` 에서 `tx.date.startswith(prefix)` 인 것만 `yield` | ← 3장 #4, 4장 제너레이터 |
| `def summarize_month(self, month: str, top: int) -> MonthlySummary` | 아래 "summary 처리 순서" | ← 3장 #4, #5 |
| `def set_budget(self, month: str, amount: str) -> tuple[str, int]` | `m = validate_month(month)`, `a = parse_amount(amount)` (둘 다 통과해야 저장) → `self.budgets.set(m, a)` → `(m, a)` 반환. 같은 월은 1단계 `BudgetStore.set` 이 덮어쓴다(원자적 교체) | ← 3장 #5, 2장 원자적 교체 |

**search 처리 순서** ← 3장 #3

1. 여섯 값이 모두 `None` 이면 `ValidationError(cause="검색 조건이 없습니다", hint="--from, --to, --category, --type, --q, --tag 중 하나 이상을 지정하세요 (최근 거래는 list 로 확인하세요)")`. 파일은 읽지 않는다.
2. 주어진 값만 검증·정리해 `SearchFilter` 를 만든다: `date_from`/`date_to` → `validate_date`, `category` → `self.validate_category`, `type_` → `validate_type`, `q` → `_required_text(q, "--q", "메모에서 찾을 글자를 한 글자 이상 입력하세요 (예: --q 점심)")`, `tag` → `_required_text(tag, "--tag", "찾을 태그 하나를 입력하세요 (예: --tag meal)")`. 하나라도 틀리면 해당 `ValidationError` 가 그대로 나간다(거래 파일을 읽기 전).
3. `return sorted(self._iter_matches(flt), key=_recency_key, reverse=True)`. `_recency_key` 는 거래마다 유일하므로 순서가 결정적이다.

**summary 처리 순서** ← 3장 #4, #5

1. `m = validate_month(month)` (`top` 은 CLI 가 `parse_top` 으로 검증한 값).
2. `budget = self.budgets.get(m)`.
3. `tx_count = income = expense = 0`, `by_category: dict[str, int] = {}` 를 두고 `for tx in self._iter_month(m):` 로 **한 건씩 누적**한다: `tx_count += 1`; income 이면 `income += tx.amount`; expense 면 `expense += tx.amount`, `by_category[tx.category] = by_category.get(tx.category, 0) + tx.amount`. 거래 객체는 보관하지 않는다(메모리는 카테고리 수에만 비례).
4. `top_expenses = heapq.nsmallest(top, by_category.items(), key=_top_key)`.
5. `usage_rate = None if budget is None else _usage_rate_text(expense, budget)`, `over_budget = budget is not None and expense > budget`.
6. `MonthlySummary(...)` 반환. 거래가 0건이어도 예외가 아니다(`tx_count == 0`).

### 3.3 search 스트리밍 설계와 한계

**파이프라인**

```
transactions.jsonl ─(_iter_lines: 한 줄씩)─▶ iter_transactions(): Transaction 1건씩
    ─▶ _iter_matches(flt): 조건에 맞는 것만 1건씩 yield
    ─▶ sorted(..., key=_recency_key, reverse=True): 매칭된 거래만 리스트로 모아 정렬
    ─▶ CLI: _format_tx 로 한 줄씩 출력
```

- 파일 읽기와 조건 필터는 제너레이터라 파일 전체가 메모리에 올라가지 않는다. 조건에 맞지 않은 거래는 읽자마자 버려진다.
- **한계**: `--limit` 이 없고(PDF 에 없음, 추가 금지) 결과는 최신순이어야 한다. 파일은 날짜순이 아니므로(과거 날짜도 add 가능, 파일은 입력 순) 가장 최신 매칭 거래가 파일 마지막 줄일 수 있다. 따라서 첫 줄을 출력하기 전에 매칭 결과를 **모두** 알아야 하고, 메모리 사용량은 **매칭 결과 수 M 에 비례**한다(파일 전체 거래 수 N 과는 무관). 실측(Python 3.14, tracemalloc): 매칭 10건이면 1만 건 파일과 10만 건 파일 모두 약 0.18MB, 매칭 약 3.3만 건이면 약 24MB(매칭 1건당 약 0.7KB). 조건이 넓어 거의 모든 거래가 맞으면 사실상 전체 로드와 같아진다. 조건 없는 search 를 오류로 막는 이유다(3.0).
- 시간: 파일 1회 순회 O(N) + 정렬 O(M log M).

**검토한 다른 표준 라이브러리 방법 (채택하지 않음, 참고용)**

| 방법 | 메모리 | 시간·복잡도 | 채택하지 않은 이유 |
| --- | --- | --- | --- |
| `heapq.nlargest(len, ...)` / `bisect.insort` | O(M) | nlargest 는 n 이 크면 내부적으로 sorted 와 같음, insort 는 O(M²) | 이득 없음 |
| 1차 순회에서 `(키, 파일 바이트 오프셋)` 만 모으고 정렬한 뒤 `seek` 으로 줄을 다시 읽기 | O(M) (건당 약 0.1KB 로 작아짐) | 저장소에 바이너리 모드 오프셋 읽기 추가 필요(텍스트 모드 `for` 중에는 `tell()` 불가), 무작위 읽기 | 1단계 저장소 변경 필요, 여전히 O(M) |
| K 건씩 반복: `heapq.nlargest(K, 매칭)` 출력 → 다음 순회에서 "마지막 키보다 작은 것" 중 다시 K 건 | O(K) 고정 | 파일을 ⌈M/K⌉ 번 다시 읽음. 10만 건 파일·매칭 3.3만 건·K=1000 이면 34회 순회(수십 초) | 시간이 매칭 수에 비례해 폭증 |
| 외부 정렬: K 건씩 정렬해 `tempfile` 임시 파일(run)로 쓰고 `heapq.merge` 로 병합 출력 | O(K) 고정 | O(N + M log M), 임시 파일 쓰기·정리 필요 | 메모리를 고정해야 할 때의 정석이지만, 이 과제 규모에 비해 코드·실패 경로(임시 파일 정리)가 크게 늘어난다 |

결론: 요구사항(`--limit` 없음 + 최신순)에서는 "매칭 결과만 모아 정렬"이 가장 단순하다. 메모리를 매칭 수와 무관하게 고정해야 한다면 외부 정렬(`tempfile` + `heapq.merge`)이 표준 라이브러리 안의 방법이다(총괄 확인 필요 #5).

**2단계 정적 검사 (h) "전체 정렬 금지"의 3단계 적용**

2단계 (h) 는 `services.py`/`cli.py` 에 `sorted(` 가 한 번도 없어야 했다. 3단계부터는 다음으로 바꾼다(6.2 S8 에서 AST 로 검사).

1. 거래 전체를 모으는 코드 금지: `list(`/`tuple(`/`set(`/`sorted(` 의 첫 인자가 `iter_transactions()` 호출이면 실패, `iter_transactions()` 를 순회하는 리스트·집합·딕셔너리 컴프리헨션도 실패. `.sort(` 금지.
2. `sorted(` 는 `services.py` 전체에서 **정확히 1회**, 첫 인자가 `self._iter_matches(...)` 인 경우만 허용(= search 의 매칭 결과 정렬). `cli.py` 에는 `sorted`/`sort`/`nlargest`/`nsmallest` 가 없어야 한다.
3. `_iter_matches`, `_iter_month` 는 `iter_transactions()` 를 `for` 로 순회하는 제너레이터(`yield` 포함)여야 한다.
4. `summarize_month` 는 `_iter_month(...)` 를 `for` 로 순회하며 누적해야 한다(거래를 모으지 않음). TOP N 은 카테고리 합계(카테고리 수만큼 작음)에 `heapq.nsmallest` 를 쓴다.
5. `recent_transactions`(list) 의 `heapq.nlargest` 는 그대로 있어야 한다.

### 3.4 `budget_app/cli.py` — [CLI] (추가·변경)

import 추가: services 에서 `DEFAULT_SUMMARY_TOP`, `MonthlySummary`, `parse_top`. **`storage` 는 여전히 import 하지 않는다.**

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `@handle_errors def _cmd_search(args: argparse.Namespace) -> int` | `service = LedgerService(args.data_dir)` → `txs = service.search_transactions(date_from=args.date_from, date_to=args.date_to, category=args.category, type_=args.type, q=args.q, tag=args.tag)` → 각 거래를 `_format_tx` 로 출력. 없으면 `조건에 맞는 거래가 없습니다.` 출력. `EXIT_OK` | ← 3장 #3 |
| `def _summary_lines(s: MonthlySummary) -> list[str]` | 아래 "summary 출력 형식"대로 줄 목록을 만든다 | ← 3장 #4, #5, PDF 8장 예시 |
| `@handle_errors def _cmd_summary(args: argparse.Namespace) -> int` | `top = DEFAULT_SUMMARY_TOP if args.top is None else parse_top(args.top)` → `service = LedgerService(args.data_dir)` → `service.summarize_month(args.month, top)` → `_summary_lines` 의 각 줄 출력. `EXIT_OK` | ← 3장 #4 |
| `@handle_errors def _cmd_budget_set(args: argparse.Namespace) -> int` | `month, amount = service.set_budget(args.month, args.amount)` → `[저장 완료] {month} 예산 {amount}원` 출력. `EXIT_OK` | ← 3장 #5, PDF 8장 `[저장 완료] 2024-01 예산 500000원` |

- `LedgerService(...)` 는 반드시 데코레이터가 적용된 핸들러 안에서 만든다(2단계와 같음).

**summary 출력 형식** (모두 stdout) ← 3장 #4, #5, PDF 8장

해당 월 거래가 있을 때:

```
총 수입: 3000000원
총 지출: 215000원
잔액: 2785000원
예산: 500000원 (사용률 43.0%)        ← 예산이 있을 때만
[경고] 예산을 초과했습니다            ← over_budget 일 때만
지출 TOP 3                            ← 요청한 N 그대로 (결과가 N 개보다 적어도)
1) rent 150000원
2) food 45000원
3) transport 20000원
```

- 지출 거래가 하나도 없는 달(수입만 있음): `지출 TOP {N}` 다음 줄에 `지출 내역 없음`.
- 해당 월 거래가 0건(`tx_count == 0`): 첫 줄 `{month} 데이터 없음` (예: `2024-05 데이터 없음`). 예산이 있으면 다음 줄에 `예산: {budget}원 (사용률 0.0%)` 를 붙이고 끝낸다(합계·TOP 줄 없음). 예산이 없으면 그 한 줄만 출력한다. 종료 코드 0.

#### 명령 구성 (추가분, help 문구는 한국어 한 줄, `%` 금지)

```
python -m budget_app {add,list,search,summary,budget,update,delete,category} ...
  search  [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--category CATEGORY] [--type TYPE] [--q Q] [--tag TAG]
                              [--data-dir DIR]     조건 검색 (최신순, 조건은 모두 만족)
  summary --month YYYY-MM [--top N]   [--data-dir DIR]     월별 요약 (총수입/총지출/잔액, 예산 사용률, 지출 TOP N)
  budget {set}                                     월 예산 관리
    budget set --month YYYY-MM --amount AMOUNT [--data-dir DIR]   월 예산 저장 (같은 월은 덮어씀)
```

| 파서 | 인자 (모두 문자열, 값 검증은 서비스) |
| --- | --- |
| `search` (`**leaf`) | `add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", default=None, help="시작 날짜 (이 날짜 포함)")`, `add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", default=None, help="끝 날짜 (이 날짜 포함)")`, `--category` (help `"등록된 카테고리 (정확히 일치)"`), `--type` (`"거래 종류 (income 또는 expense)"`), `--q` (`"메모에 포함된 글자 (대소문자 구분)"`), `--tag` (`"태그 하나 (정확히 일치)"`). 모두 `default=None`. `--limit` 등 다른 옵션은 없다 |
| `summary` (`**leaf`) | `--month` (`required=True`, `metavar="YYYY-MM"`, help `"요약할 월 (필수)"`), `--top` (`default=None`, `metavar="N"`, help `"지출 TOP N 개수 (기본값: 3)"`) |
| `budget` (`**common`, `--data-dir` 없음) | `add_subparsers(dest="budget_command", required=True, metavar="{set}")`. 하위 명령은 `set` 하나뿐(`get/show/list` 없음) |
| `budget set` (`**leaf`) | `--month` (`required=True`, `metavar="YYYY-MM"`, help `"예산을 정할 월"`), `--amount` (`required=True`, `metavar="AMOUNT"`, help `"예산 금액 (1 이상의 정수)"`) |

- 각 말단 파서에 `set_defaults(handler=_cmd_search | _cmd_summary | _cmd_budget_set)`.
- import, export 는 여전히 등록하지 않는다(`invalid choice` → 2).

## 4. 계층 규칙

2단계와 같다. 새 import 도 이 표 안에서만 한다.

```
__main__.py → cli.py → services.py → storage.py → models.py
                 └──→ decorators.py ──→ models.py
```

| 모듈 | import 가능한 `budget_app` 모듈 |
| --- | --- |
| `models.py` | 없음 |
| `storage.py` | `models` |
| `services.py` | `storage`, `models` |
| `decorators.py` | `models` (`BudgetAppError` 만) |
| `cli.py` | `services`, `decorators`, `models` — **`storage` 금지** |
| `__main__.py` | `cli` |

- `print`/`input` 은 `cli.py`, `decorators.py` 에만 둔다. 사용률·초과 여부·TOP N 계산은 서비스, 문구 조립은 CLI.
- 상대 import 금지(`from budget_app.xxx import ...`).

## 5. 예외/경계 상황

| 상황 | 처리 | 종료 코드 |
| --- | --- | --- |
| search 조건 하나도 없음 | `[오류] 검색 조건이 없습니다` + 힌트 | 1 |
| search `--from`/`--to` 형식 오류·없는 날짜 (`2024-13-01`, `2024-1-5`) | `validate_date` 의 `[오류]/[힌트]` | 1 |
| search `--from` > `--to` | 오류 아님. `조건에 맞는 거래가 없습니다.` | 0 |
| search `--type refund` / 미등록 `--category nope` | `[오류]/[힌트]` (카테고리 힌트에 등록 목록) | 1 |
| search `--q "  "`, `--tag ""` | `[오류] --q 값이 비어 있습니다` 등 | 1 |
| search 결과 없음 (빈 파일 포함) | `조건에 맞는 거래가 없습니다.` | 0 |
| search 같은 날짜 여러 건 | id 숫자 내림차순 (`TX-1000000` 이 `TX-999999` 보다 먼저) | 0 |
| search `--q pizza` vs 메모 `Pizza` | 대소문자 구분 → 불일치 | 0 |
| search `--tag mea` vs 태그 `meal` | 정확히 일치만 → 불일치 | 0 |
| search `--limit` 등 없는 옵션, `-h`, `--cat` 같은 약어 | argparse 사용법 오류 | 2 |
| summary `--month` 누락 | argparse 사용법 오류 | 2 |
| summary `--month 2024-13`, `2024-1`, `2024-01-01` | `validate_month` 의 `[오류]/[힌트]` | 1 |
| summary `--top 0`, `-1`, `abc`, `1.5` | `[오류] --top 값이 올바르지 않습니다` | 1 |
| summary 해당 월 거래 없음 | `{month} 데이터 없음` (+예산이 있으면 사용률 0.0% 줄) | 0 |
| summary 수입만 있는 달 | 합계 3줄 + `지출 TOP N` + `지출 내역 없음` | 0 |
| summary 지출 > 수입 | `잔액: -12000원` | 0 |
| summary 지출 = 예산 | `사용률 100.0%`, 경고 없음 | 0 |
| summary 지출 > 예산 | 사용률(100 초과) + `[경고] 예산을 초과했습니다` | 0 |
| summary 카테고리 수 < N | 있는 만큼만 출력, 헤더는 `지출 TOP N` | 0 |
| budget set `--month`/`--amount` 누락, `budget` 하위 명령 없음, `budget get/show/list` | argparse 사용법 오류 (내부 이름 `budget_command` 가 메시지에 나오지 않음) | 2 |
| budget set 잘못된 월 / 금액 `0`, `-5`, `abc`, `1.5`, `1,000` | `[오류]/[힌트]`, budgets.jsonl 변경 없음 | 1 |
| budget set 같은 월 재설정 | 덮어쓰기(월마다 한 줄) | 0 |
| budgets.jsonl 손상 줄 | 1단계 `BudgetAppError`(파일 경로·줄 번호). budget set 은 원본 보존, 임시 파일 남지 않음 | 1 |
| transactions.jsonl 손상 줄 (search/summary) | 1단계 `BudgetAppError` | 1 |
| `--data-dir` 를 `budget` 과 `set` 사이, 또는 명령 앞에 둠 | argparse 사용법 오류 | 2 |
| 어떤 경우에도 | `Traceback` 없음. `[오류]/[힌트]` 는 stderr, `[경고]` 는 stdout | — |

### Python 3.10 호환 주의

1·2단계 금지 목록을 그대로 적용한다(`fromisoformat`, `typing.Self`, `datetime.UTC`, `except*`, `ExceptionGroup`, `tomllib`, PEP 695, argparse `color`/`suggest_on_error`). `@dataclasses.dataclass(frozen=True)`, `X | None`, `list[tuple[str, int]]`, `heapq.nsmallest` 는 3.10 에서 사용 가능하다.

## 6. 완료 기준 (에이전트 3 검증 절차)

아래 스크립트 하나에 정적 검사, 동작 검사, 스트리밍 메모리 검사, 1·2단계 회귀 검사를 모두 넣었다.

- **실행 방법**: 코드 블록 내용을 스크래치패드에 파일로 저장한 뒤 `bash <파일>` 로 실행한다(macOS 기본 bash 3.2 에서 동작하도록 작성). 저장한 스크립트 파일은 실행 후 지운다.
- 이 Mac 에는 `python` 이 없어 스크립트 첫머리에서 임시 폴더에 `python → python3` 링크를 만들고 PATH 앞에 둔다.
- 모든 임시 파일은 `W="$(mktemp -d)"` 아래에만 만들고, 끝나면(실패해도) `trap` 으로 지운다. macOS 의 `mktemp -d` 는 `TMPDIR` 와 관계없이 시스템 임시 폴더(`/var/folders/...`)에 만들기 때문에, 1·2단계 회귀 스크립트의 `mktemp -d` 도 `$W` 아래로 바꿔서 실행한다.
- `PYTHONDONTWRITEBYTECODE=1` 로 `__pycache__` 를 남기지 않는다. 프로젝트 루트에 `./data` 가 생기면 실패다.
- 성공 기준: `FAIL` 로 시작하는 줄이 하나도 없고, `MEMORY_OK` 와 마지막 줄 `STEP3_ALL_OK` 가 나온다. 전체 실행 시간은 1분 안팎이다(메모리 검사에 10만 건 파일 사용).

### 6.1 정적 검사 항목 (스크립트 S0~S10)

| # | 검사 | 기대 |
| --- | --- | --- |
| S0 | 변경 금지 파일 5개(`models`, `storage`, `decorators`, `__main__`, `__init__`)의 SHA-256 이 2단계 완료 시점과 같음 | 일치 |
| S1 | 파일 7개 존재 | 존재 |
| S2 | 3.10 문법 (`ast.parse(feature_version=(3, 10))`) | 통과 |
| S3 | 3.11+ 전용 API grep | 없음 |
| S4 | `.read()`/`readlines(` (전체 로드) grep | 없음 |
| S5 | 계층 규칙 (4장 표) | 위반 없음 |
| S6 | 모든 함수의 매개변수·반환 타입 힌트 (가변 인자 포함) | 누락 없음 |
| S7 | `def handle_errors` 1개, `@handle_errors` **10개**, `_cmd_*` 함수 10개(`add, list, update, delete, category_add, category_list, category_remove, search, summary, budget_set`) 전부 데코레이터 적용 | 일치 |
| S8 | 스트리밍 규칙 (3.3 "(h) 의 3단계 적용" 1~5) | 위반 없음 |
| S9 | 범위 밖 명령(`import`, `export`) 문자열 등록 없음 | 없음 |
| S10 | `print(`/`input(` 이 models/storage/services 에 없음 | 없음 |

### 6.2 검증 스크립트

```bash
# 3단계 검증 스크립트. 실행: bash <이 파일>
cd "/Users/khm04/codessey/pocket money" || exit 1
export PYTHONDONTWRITEBYTECODE=1
W="$(mktemp -d)"; export W                      # 이 스크립트의 임시 파일은 전부 여기 아래
cleanup() { chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"; }
trap cleanup EXIT
mkdir "$W/bin" && ln -s "$(command -v python3)" "$W/bin/python" || exit 1   # python 이 없어서 python3 로 연결
export PATH="$W/bin:$PATH"
python --version || exit 1
D="$W/run"; mkdir "$D"; DD="$D/data"; FAIL=0
TXF="$DD/transactions.jsonl"; BGF="$DD/budgets.jsonl"

fail()      { echo "FAIL $*"; FAIL=1; }
# t <기대 종료코드> <표준입력(printf %b 형식)> <인자...>
t() {
  local want=$1 input=$2; shift 2
  printf '%b' "$input" | python -m budget_app "$@" >"$D/out" 2>"$D/err"
  local rc=$?
  [ "$rc" = "$want" ] || { echo "FAIL rc=$rc want=$want :: $*"; cat "$D/err"; FAIL=1; }
  if grep -q "Traceback" "$D/out" "$D/err"; then echo "FAIL traceback :: $*"; FAIL=1; fi
}
out_has()   { grep -qF -- "$1" "$D/out" || fail "stdout에 없음: $1"; }
out_no()    { if grep -qF -- "$1" "$D/out"; then fail "stdout에 있으면 안 됨: $1"; fi; }
err_has()   { grep -qF -- "$1" "$D/err" || fail "stderr에 없음: $1"; }
err_no()    { if grep -qF -- "$1" "$D/err"; then fail "stderr에 있으면 안 됨: $1"; fi; }
out_eq()    { [ "$(cat "$D/out")" = "$1" ] || { echo "FAIL stdout 불일치"; echo "--- got"; cat "$D/out"; echo "--- want"; printf '%s\n' "$1"; FAIL=1; }; }
out_empty() { [ ! -s "$D/out" ] || { echo "FAIL stdout 이 비어 있어야 함"; cat "$D/out"; FAIL=1; }; }
err_empty() { [ ! -s "$D/err" ] || { echo "FAIL stderr 가 비어 있어야 함"; cat "$D/err"; FAIL=1; }; }
cnt()       { grep -oF -- "$2" "$D/$1" | wc -l | tr -d ' '; }
err_cnt()   { [ "$(cnt err '[오류]')" = "$1" ] && [ "$(cnt err '[힌트]')" = "$1" ] || { echo "FAIL [오류]/[힌트] 개수 != $1"; cat "$D/err"; FAIL=1; }; }
NONE="조건에 맞는 거래가 없습니다."

# ======================= S. 정적 검사 =======================
# S0 변경 금지 파일
shasum -a 256 -c - >/dev/null <<'SUMS' || fail "S0 변경 금지 파일이 바뀜 (models/storage/decorators/__main__/__init__)"
08b6a94954a6ca8d6619a69a026ac2fd2d028844e17a8c55cb8d6f02faca513f  budget_app/models.py
63a3d4493da74f683b4673050497238b7a1f59fce598673383e48d59816a77a5  budget_app/storage.py
775389d5609a7243ab96a9c0b0365ea93546c61055b5c6b254894a49a3b3a096  budget_app/decorators.py
6958ee4078ab3cdd31564e022cd9fccc673a5f2f8509c241b4771646a4e72753  budget_app/__main__.py
0cb00a1323d1945aa0e71486ffebaf612fde2efe434f13182806c00515b3605c  budget_app/__init__.py
SUMS
# S1 파일 존재
for f in __init__ __main__ models storage services decorators cli; do [ -f "budget_app/$f.py" ] || fail "S1 budget_app/$f.py 없음"; done
# S2 3.10 문법
python3 - budget_app/*.py <<'PY' || fail "S2 3.10 문법"
import ast, sys
for f in sys.argv[1:]:
    ast.parse(open(f, encoding="utf-8").read(), feature_version=(3, 10))
PY
# S3 3.11+ 전용 API
if grep -nE "fromisoformat|typing\.Self|from typing import .*Self|datetime\.UTC|except\*|ExceptionGroup|tomllib|suggest_on_error|color=" budget_app/*.py; then fail "S3 3.11+ API"; fi
# S4 전체 로드
if grep -nE "\.read\(\)|readlines\(" budget_app/*.py; then fail "S4 전체 로드"; fi
# S5 계층 규칙
python3 - <<'PY' || fail "S5 계층 규칙"
import ast, sys
allowed = {"models": set(), "storage": {"models"}, "services": {"storage", "models"},
           "decorators": {"models"}, "cli": {"services", "decorators", "models"},
           "__main__": {"cli"}, "__init__": set()}
bad = []
for m, ok in allowed.items():
    for n in ast.walk(ast.parse(open(f"budget_app/{m}.py", encoding="utf-8").read())):
        if isinstance(n, ast.ImportFrom):
            if n.level: bad.append((m, "relative import"))
            mods = [n.module or ""]
        elif isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        else:
            continue
        for mod in mods:
            if mod == "budget_app" or mod.startswith("budget_app."):
                tgt = mod.split(".")[1] if "." in mod else "?"
                if tgt not in ok: bad.append((m, mod))
print(bad) if bad else None
sys.exit(1 if bad else 0)
PY
# S6 타입 힌트
python3 - budget_app/*.py <<'PY' || fail "S6 타입 힌트"
import ast, sys
bad = []
for f in sys.argv[1:]:
    for n in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            args = a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]
            miss = [x.arg for x in args if x.annotation is None and x.arg not in ("self", "cls")]
            if n.returns is None or miss: bad.append((f, n.name, miss))
print(bad) if bad else None
sys.exit(1 if bad else 0)
PY
# S7 데코레이터
[ "$(grep -c "def handle_errors" budget_app/decorators.py)" = 1 ] || fail "S7 handle_errors 정의"
[ "$(grep -c "@handle_errors" budget_app/cli.py)" = 10 ] || fail "S7 @handle_errors 개수 != 10"
python3 - <<'PY' || fail "S7 _cmd_* 데코레이터 적용"
import ast, sys
tree = ast.parse(open("budget_app/cli.py", encoding="utf-8").read())
cmds = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("_cmd_")]
want = {"_cmd_add", "_cmd_list", "_cmd_update", "_cmd_delete", "_cmd_category_add", "_cmd_category_list",
        "_cmd_category_remove", "_cmd_search", "_cmd_summary", "_cmd_budget_set"}
names = {n.name for n in cmds}
undecorated = [n.name for n in cmds if not any(isinstance(d, ast.Name) and d.id == "handle_errors" for d in n.decorator_list)]
if names != want or undecorated:
    print("names:", sorted(names ^ want), "undecorated:", undecorated); sys.exit(1)
PY
# S8 스트리밍 규칙 (3.3)
python3 - <<'PY' || fail "S8 스트리밍 규칙"
import ast, sys
def callname(c):
    f = c.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
tree = ast.parse(open("budget_app/services.py", encoding="utf-8").read())
funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
def iterates(fn, target):
    return any(isinstance(n, ast.For) and isinstance(n.iter, ast.Call) and callname(n.iter) == target for n in ast.walk(fn))
def is_gen(fn):
    return any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(fn))
def calls(fn, name):
    return any(isinstance(n, ast.Call) and callname(n) == name for n in ast.walk(fn))
bad, sorted_args = [], []
for n in ast.walk(tree):
    if isinstance(n, ast.Call):
        name = callname(n)
        inner = callname(n.args[0]) if n.args and isinstance(n.args[0], ast.Call) else None
        if name == "sort": bad.append(".sort() 사용")
        if name in ("list", "tuple", "set", "sorted") and inner == "iter_transactions": bad.append(f"{name}(iter_transactions()) 전체 로드")
        if name == "sorted": sorted_args.append(inner)
    if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp)):
        if any(isinstance(g.iter, ast.Call) and callname(g.iter) == "iter_transactions" for g in n.generators):
            bad.append("컴프리헨션으로 전체 로드")
if sorted_args != ["_iter_matches"]: bad.append(f"sorted 는 _iter_matches 결과에만 1회 허용: {sorted_args}")
for g in ("_iter_matches", "_iter_month"):
    if g not in funcs or not is_gen(funcs[g]) or not iterates(funcs[g], "iter_transactions"):
        bad.append(f"{g} 가 iter_transactions() 를 for 로 도는 제너레이터가 아님")
if "search_transactions" not in funcs or not calls(funcs["search_transactions"], "sorted"): bad.append("search_transactions 에 sorted 없음")
if "summarize_month" not in funcs or not iterates(funcs["summarize_month"], "_iter_month"): bad.append("summarize_month 가 _iter_month() 를 for 로 누적하지 않음")
if "recent_transactions" not in funcs or not calls(funcs["recent_transactions"], "nlargest"): bad.append("list 의 nlargest 가 사라짐")
for n in ast.walk(ast.parse(open("budget_app/cli.py", encoding="utf-8").read())):
    if isinstance(n, ast.Call) and callname(n) in ("sorted", "sort", "nlargest", "nsmallest"): bad.append(f"cli.py 에서 {callname(n)}")
print(bad) if bad else None
sys.exit(1 if bad else 0)
PY
# S9 범위 밖 명령
if grep -nE "[\"'](import|export)[\"']" budget_app/cli.py; then fail "S9 import/export 등록됨"; fi
# S10 print/input 위치
if grep -nE "(^|[^A-Za-z0-9_.])(print|input)\(" budget_app/models.py budget_app/storage.py budget_app/services.py; then fail "S10 print/input 위치"; fi

# ======================= A. --help =======================
t 0 '' --help;             out_has "{add,list,search,summary,budget,update,delete,category}"
t 0 '' search --help;      out_has "usage:"; for o in --from --to --category --type --q --tag --data-dir YYYY-MM-DD; do out_has "$o"; done
t 0 '' summary --help;     out_has "usage:"; for o in --month --top --data-dir; do out_has "$o"; done
t 0 '' budget --help;      out_has "usage:"; out_has "{set}"
t 0 '' budget set --help;  out_has "usage:"; for o in --month --amount --data-dir; do out_has "$o"; done
[ ! -e data ] || fail "--help 가 ./data 를 만듦"

# ======================= B. 사용법 오류 (2) =======================
t 2 '' search -h;                                              err_cnt 1
t 2 '' summary -h;                                             err_cnt 1
t 2 '' budget set -h;                                          err_cnt 1
t 2 '' search --cat food --data-dir "$DD";                     err_cnt 1   # 약어 금지
t 2 '' summary --mon 2024-01 --data-dir "$DD";                 err_cnt 1
t 2 '' budget set --mon 2024-01 --amount 1 --data-dir "$DD";   err_cnt 1
t 2 '' search --limit 5 --q x --data-dir "$DD";                err_cnt 1   # PDF 에 없는 옵션
t 2 '' summary --data-dir "$DD";                               err_cnt 1; err_has "--month"
t 2 '' summary --top 3 --data-dir "$DD";                       err_cnt 1
t 2 '' budget set --amount 1 --data-dir "$DD";                 err_cnt 1
t 2 '' budget set --month 2024-01 --data-dir "$DD";            err_cnt 1
t 2 '' budget --data-dir "$DD";                                err_cnt 1; err_no "budget_command"
t 2 '' budget;                                                 err_cnt 1; err_no "budget_command"
t 2 '' budget --data-dir "$DD" set --month 2024-01 --amount 1; err_cnt 1   # --data-dir 는 말단 명령 뒤에만
t 2 '' --data-dir "$DD" summary --month 2024-01;               err_cnt 1
for c in get show list; do t 2 '' budget "$c" --data-dir "$DD"; err_cnt 1; done
for c in import export; do t 2 '' "$c" --data-dir "$DD"; err_cnt 1; done
[ ! -e "$DD" ] || fail "사용법 오류에서 data 폴더가 생김"

# ======================= C. 데이터 준비 (대화형 add) =======================
t 0 'salary\n' category add --data-dir "$DD"; out_has "[저장 완료] category=salary"
addtx() { t 0 "$1" add --data-dir "$DD"; out_has "[저장 완료] id=$2"; }
addtx '2024-01-15\nexpense\nfood\n15000\n점심\nmeal\n'               TX-000001
addtx '2024-01-14\nincome\nsalary\n3000000\n월급\n\n'                TX-000002
addtx '2024-01-12\nexpense\ntransport\n20000\n버스\ncommute\n'       TX-000003
addtx '2024-01-05\nexpense\nrent\n150000\n1월 월세\nhouse,fixed\n'   TX-000004
addtx '2024-01-15\nexpense\nfood\n30000\n저녁 Pizza\nmeal, friend\n' TX-000005
addtx '2024-02-03\nexpense\nfood\n12000\n점심\nmeal\n'               TX-000006
addtx '2023-12-31\nincome\netc\n50000\n용돈\n\n'                     TX-000007
X1='TX-000001 | 2024-01-15 | expense | food | 15000 | 점심'
X2='TX-000002 | 2024-01-14 | income | salary | 3000000 | 월급'
X3='TX-000003 | 2024-01-12 | expense | transport | 20000 | 버스'
X4='TX-000004 | 2024-01-05 | expense | rent | 150000 | 1월 월세'
X5='TX-000005 | 2024-01-15 | expense | food | 30000 | 저녁 Pizza'
X6='TX-000006 | 2024-02-03 | expense | food | 12000 | 점심'
X7='TX-000007 | 2023-12-31 | income | etc | 50000 | 용돈'
SUMT="$(cksum < "$TXF")"

# ======================= D. search =======================
t 0 '' search --category food --data-dir "$DD";                   err_empty; out_eq "$(printf '%s\n' "$X6" "$X5" "$X1")"
t 0 '' search --from 2024-01-01 --to 2024-01-31 --data-dir "$DD";  out_eq "$(printf '%s\n' "$X5" "$X1" "$X2" "$X3" "$X4")"
t 0 '' search --from 2024-01-14 --data-dir "$DD";                  out_eq "$(printf '%s\n' "$X6" "$X5" "$X1" "$X2")"   # 경계 포함
t 0 '' search --to 2024-01-05 --data-dir "$DD";                    out_eq "$(printf '%s\n' "$X4" "$X7")"               # 경계 포함
t 0 '' search --type income --data-dir "$DD";                      out_eq "$(printf '%s\n' "$X2" "$X7")"
t 0 '' search --q 점심 --data-dir "$DD";                           out_eq "$(printf '%s\n' "$X6" "$X1")"
t 0 '' search --q " 월세 " --data-dir "$DD";                       out_eq "$X4"      # 앞뒤 공백 제거, 부분 일치
t 0 '' search --q Pizza --data-dir "$DD";                          out_eq "$X5"
t 0 '' search --q pizza --data-dir "$DD";                          out_eq "$NONE"    # 대소문자 구분
t 0 '' search --tag meal --data-dir "$DD";                         out_eq "$(printf '%s\n' "$X6" "$X5" "$X1")"
t 0 '' search --tag friend --data-dir "$DD";                       out_eq "$X5"
t 0 '' search --tag fixed --data-dir "$DD";                        out_eq "$X4"
t 0 '' search --tag mea --data-dir "$DD";                          out_eq "$NONE"    # 태그는 정확히 일치
t 0 '' search --category food --type expense --from 2024-01-01 --to 2024-01-31 --q 점심 --tag meal --data-dir "$DD"; out_eq "$X1"
t 0 '' search --category food --type income --data-dir "$DD";      out_eq "$NONE"    # AND
t 0 '' search --from 2024-02-01 --to 2024-01-01 --data-dir "$DD";  out_eq "$NONE"    # from > to
t 0 '' search --type expense --data-dir "$D/empty";                out_eq "$NONE"    # 빈 파일
t 1 '' search --data-dir "$DD";                    err_cnt 1; out_empty; err_has "검색 조건이 없습니다"
t 1 '' search --from 2024-13-01 --data-dir "$DD";  err_cnt 1; out_empty
t 1 '' search --to 2024-1-5 --data-dir "$DD";      err_cnt 1; out_empty
t 1 '' search --type refund --data-dir "$DD";      err_cnt 1
t 1 '' search --category nope --data-dir "$DD";    err_cnt 1; err_has "등록되지 않은 카테고리"
t 1 '' search --q "   " --data-dir "$DD";          err_cnt 1; err_has "--q"
t 1 '' search --tag "" --data-dir "$DD";           err_cnt 1; err_has "--tag"
[ "$(cksum < "$TXF")" = "$SUMT" ] || fail "search 가 거래 파일을 바꿈"
# 같은 날짜: id 숫자 내림차순
python3 - "$D/ids" <<'PY'
import json, os, sys
os.makedirs(sys.argv[1])
with open(os.path.join(sys.argv[1], "transactions.jsonl"), "w", encoding="utf-8") as f:
    for i in ("TX-999999", "TX-1000000"):
        f.write(json.dumps({"id": i, "type": "expense", "date": "2024-03-31", "amount": 1,
                            "category": "food", "memo": "", "tags": []}) + "\n")
PY
t 0 '' search --category food --data-dir "$D/ids"
out_eq "$(printf '%s\n' 'TX-1000000 | 2024-03-31 | expense | food | 1 |' 'TX-999999 | 2024-03-31 | expense | food | 1 |')"

# ======================= E. summary (예산 없음) =======================
JAN="$(printf '%s\n' '총 수입: 3000000원' '총 지출: 215000원' '잔액: 2785000원')"
TOP3="$(printf '%s\n' '지출 TOP 3' '1) rent 150000원' '2) food 45000원' '3) transport 20000원')"
t 0 '' summary --month 2024-01 --data-dir "$DD";          err_empty; out_eq "$(printf '%s\n' "$JAN" "$TOP3")"   # 기본 --top 3
out_no "예산"
t 0 '' summary --month 2024-01 --top 1 --data-dir "$DD";  out_eq "$(printf '%s\n' "$JAN" '지출 TOP 1' '1) rent 150000원')"
t 0 '' summary --month 2024-01 --top 10 --data-dir "$DD"; out_eq "$(printf '%s\n' "$JAN" '지출 TOP 10' '1) rent 150000원' '2) food 45000원' '3) transport 20000원')"
t 0 '' summary --month 2024-02 --data-dir "$DD";          out_eq "$(printf '%s\n' '총 수입: 0원' '총 지출: 12000원' '잔액: -12000원' '지출 TOP 3' '1) food 12000원')"
t 0 '' summary --month 2023-12 --data-dir "$DD";          out_eq "$(printf '%s\n' '총 수입: 50000원' '총 지출: 0원' '잔액: 50000원' '지출 TOP 3' '지출 내역 없음')"
t 0 '' summary --month 2024-05 --data-dir "$DD";          out_eq "2024-05 데이터 없음"
for v in 2024-13 2024-1 2024-01-01 abc; do t 1 '' summary --month "$v" --data-dir "$DD"; err_cnt 1; out_empty; done
for v in 0 -1 abc 1.5; do t 1 '' summary --month 2024-01 --top "$v" --data-dir "$DD"; err_cnt 1; err_has "--top"; done
[ "$(cksum < "$TXF")" = "$SUMT" ] || fail "summary 가 거래 파일을 바꿈"

# ======================= F. budget set =======================
SUMB="$(cksum < "$BGF")"
for v in 2024-13 2024-1 2024-01-01 abc; do t 1 '' budget set --month "$v" --amount 1000 --data-dir "$DD"; err_cnt 1; out_empty; done
for v in 0 -5 abc 1.5 1,000; do t 1 '' budget set --month 2024-01 --amount "$v" --data-dir "$DD"; err_cnt 1; out_empty; done
[ "$(cksum < "$BGF")" = "$SUMB" ] || fail "실패한 budget set 이 예산 파일을 바꿈"
t 0 '' budget set --month 2024-01 --amount 500000 --data-dir "$DD"; err_empty; out_eq "[저장 완료] 2024-01 예산 500000원"
[ "$(cat "$BGF")" = '{"month": "2024-01", "amount": 500000}' ] || fail "budgets.jsonl 내용: $(cat "$BGF")"

# ======================= G. summary + 예산 =======================
t 0 '' summary --month 2024-01 --top 3 --data-dir "$DD"      # PDF 8장 예시 그대로
out_eq "$(printf '%s\n' "$JAN" '예산: 500000원 (사용률 43.0%)' "$TOP3")"
t 0 '' budget set --month 2024-01 --amount 200000 --data-dir "$DD"; out_eq "[저장 완료] 2024-01 예산 200000원"
[ "$(grep -c '"2024-01"' "$BGF")" = 1 ] || fail "같은 월 예산이 덮어써지지 않음"
t 0 '' summary --month 2024-01 --data-dir "$DD";   err_empty
out_eq "$(printf '%s\n' "$JAN" '예산: 200000원 (사용률 107.5%)' '[경고] 예산을 초과했습니다' "$TOP3")"
t 0 '' budget set --month 2024-01 --amount 215000 --data-dir "$DD"
t 0 '' summary --month 2024-01 --data-dir "$DD";   out_has "예산: 215000원 (사용률 100.0%)"; out_no "[경고]"
t 0 '' budget set --month 2024-06 --amount 100000 --data-dir "$DD"
t 0 '' summary --month 2024-06 --data-dir "$DD";   out_eq "$(printf '%s\n' '2024-06 데이터 없음' '예산: 100000원 (사용률 0.0%)')"
[ "$(grep -c . "$BGF")" = 2 ] || fail "budgets.jsonl 줄 수 != 2"
# TOP N 동점: 금액 내림차순, 같으면 이름 오름차순 (등록 순서·입력 순서는 transport 가 먼저)
DT="$D/tie"
t 0 '2024-03-01\nexpense\ntransport\n20000\n\n\n' add --data-dir "$DT"
t 0 '2024-03-02\nexpense\netc\n20000\n\n\n' add --data-dir "$DT"
t 0 '2024-03-03\nexpense\nfood\n5000\n\n\n' add --data-dir "$DT"
t 0 '' summary --month 2024-03 --top 2 --data-dir "$DT"
out_eq "$(printf '%s\n' '총 수입: 0원' '총 지출: 45000원' '잔액: -45000원' '지출 TOP 2' '1) etc 20000원' '2) transport 20000원')"
# 사용률 반올림 (6.25 → 6.3, 66.66… → 66.7)
DR="$D/rate"
t 0 '2024-04-10\nexpense\nfood\n1\n\n\n' add --data-dir "$DR"
t 0 '' budget set --month 2024-04 --amount 16 --data-dir "$DR"
t 0 '' summary --month 2024-04 --data-dir "$DR";   out_has "예산: 16원 (사용률 6.3%)"
t 0 '2024-07-10\nexpense\nfood\n2\n\n\n' add --data-dir "$DR"
t 0 '' budget set --month 2024-07 --amount 3 --data-dir "$DR"
t 0 '' summary --month 2024-07 --data-dir "$DR";   out_has "예산: 3원 (사용률 66.7%)"

# ======================= H. 손상 파일 =======================
DB="$D/badb"
t 0 '' budget set --month 2024-01 --amount 1000 --data-dir "$DB"
echo 'not json' >> "$DB/budgets.jsonl"; SUMX="$(cksum < "$DB/budgets.jsonl")"
t 1 '' summary --month 2024-02 --data-dir "$DB";                   err_cnt 1; err_has "budgets.jsonl"
t 1 '' budget set --month 2024-02 --amount 1000 --data-dir "$DB";  err_cnt 1; err_has "budgets.jsonl"
[ "$(cksum < "$DB/budgets.jsonl")" = "$SUMX" ] || fail "손상된 예산 파일이 바뀜"
if find "$DB" -name '*.tmp' | grep -q .; then fail "임시 파일 남음"; fi
DC="$D/badt"
t 0 '' list --data-dir "$DC"; echo 'not json' > "$DC/transactions.jsonl"
t 1 '' search --type expense --data-dir "$DC";   err_cnt 1; err_has "transactions.jsonl"
t 1 '' summary --month 2024-01 --data-dir "$DC"; err_cnt 1; err_has "transactions.jsonl"

# ======================= M. 스트리밍 메모리 (1만 건 vs 10만 건) =======================
# 같은 프로세스에서 cli.main 을 tracemalloc 으로 감싸 최대 메모리를 잰다. 첫 호출의 1회성 할당은 워밍업으로 뺀다.
python - "$W/mem" <<'PY' || FAIL=1
import contextlib, json, os, sys, tracemalloc
from budget_app.cli import main
M = sys.argv[1]
def gen(d, n):
    os.makedirs(d)
    cats = ("food", "transport", "etc")
    with open(os.path.join(d, "transactions.jsonl"), "w", encoding="utf-8") as f:
        for i in range(1, n + 1):
            needle = i % (n // 10) == 0        # rent 는 파일 크기와 관계없이 정확히 10건
            f.write(json.dumps({"id": f"TX-{i:06d}", "type": "income" if i % 4 == 0 else "expense",
                                "date": f"2024-{i % 12 + 1:02d}-{i % 28 + 1:02d}", "amount": i % 997 + 1,
                                "category": "rent" if needle else cats[i % 3], "memo": f"메모 {i}",
                                "tags": [f"t{i % 50}"]}, ensure_ascii=False) + "\n")
def peak(argv):
    with open(os.devnull, "w", encoding="utf-8") as dn, contextlib.redirect_stdout(dn):
        tracemalloc.start()
        rc = main(argv)
        p = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    assert rc == 0, (argv, rc)
    return p
small, big = os.path.join(M, "small"), os.path.join(M, "big")
gen(small, 10_000); gen(big, 100_000)
cmds = {"summary": ["summary", "--month", "2024-03", "--top", "3"],
        "search10": ["search", "--category", "rent"],          # 매칭 10건 (두 파일 같음)
        "searchN": ["search", "--category", "food"]}           # 매칭 약 3,300건 / 약 33,000건
for a in cmds.values():
    peak(a + ["--data-dir", small])                            # 워밍업
r = {(k, s): peak(a + ["--data-dir", d]) for k, a in cmds.items() for s, d in (("small", small), ("big", big))}
for k, v in r.items():
    print(f"  {k[0]:9s} {k[1]:5s} peak={v:,} bytes")
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
need(r["summary", "big"] < 2 * r["summary", "small"] and r["summary", "big"] < 2_000_000,
     "summary 최대 메모리가 거래 수(1만→10만)에 비례해 늘어남")
need(r["search10", "big"] < 2 * r["search10", "small"] and r["search10", "big"] < 2_000_000,
     "매칭 10건 search 의 최대 메모리가 파일 크기에 따라 늘어남 (전체 로드 의심)")
need(r["searchN", "big"] > 5 * r["searchN", "small"],
     "매칭 수가 10배일 때 search 메모리가 늘지 않음 (측정이 매칭 결과를 잡지 못함)")
print("MEMORY_OK" if ok else "MEMORY_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= R. 1·2단계 회귀 =======================
# 각 설계서 6.2 스크립트를 꺼내 mktemp 위치만 $W 아래로 바꾼다.
# 2단계 스크립트 B절의 "search summary budget 미등록" 검사는 3단계에서 등록되므로 import/export 만 남긴다.
python3 - <<'PY' || FAIL=1
import os
W = os.environ["W"]
FENCE = "`" * 3                                  # 이 설계서 코드 블록이 끊기지 않도록 백틱 3개를 직접 쓰지 않는다
def extract(md):
    sec = open(md, encoding="utf-8").read().split("### 6.2", 1)[1]
    return sec.split(FENCE + "bash\n", 1)[1].split(FENCE, 1)[0]
old, new = 'D="$(mktemp -d)"', 'D="$(mktemp -d "$W/reg.XXXXXX")"'
s1 = extract("docs/plans/step1-models-storage.md")
s2 = extract("docs/plans/step2-cli-core-commands.md")
b_old, b_new = "for c in search summary budget import export; do", "for c in import export; do"
assert s1.count(old) == 1 and s2.count(old) == 1 and s2.count(b_old) == 1, "회귀 스크립트 추출 실패"
open(os.path.join(W, "step1.sh"), "w", encoding="utf-8").write(s1.replace(old, new))
open(os.path.join(W, "step2.sh"), "w", encoding="utf-8").write(s2.replace(old, new).replace(b_old, b_new))
PY
bash "$W/step1.sh" >"$W/r1" 2>&1
grep -qx "ALL_OK" "$W/r1" || { echo "FAIL 1단계 회귀"; cat "$W/r1"; FAIL=1; }
bash "$W/step2.sh" >"$W/r2" 2>&1
if grep -qx "STEP2_ALL_OK" "$W/r2" && ! grep -q "^FAIL" "$W/r2"; then :; else echo "FAIL 2단계 회귀"; cat "$W/r2"; FAIL=1; fi

# ======================= 마무리 =======================
[ ! -e data ] || fail "프로젝트 루트에 ./data 가 생김"
if find budget_app -name __pycache__ | grep -q .; then fail "__pycache__ 생김"; fi
[ "$FAIL" = 0 ] && echo "STEP3_ALL_OK"
```

기대 출력: `FAIL` 로 시작하는 줄 없음, 메모리 측정값 6줄과 `MEMORY_OK`, 마지막 줄 `STEP3_ALL_OK`. 스크립트가 끝나면 `$W` 가 지워져 있어야 한다(`trap`).

참고(설계 시 실측, Python 3.14): 같은 측정 방법으로 summary 는 1만 건·10만 건 모두 약 0.18MB, 매칭 10건 search 도 두 파일 모두 약 0.18MB, 매칭 약 3,300건/33,000건 search 는 약 2.4MB/24MB 였다. 10만 건 파일 1회 처리는 tracemalloc 을 켠 상태에서 약 4초 걸린다.

## 7. 총괄 확인 필요

1. **조건 없는 search**: 조건이 하나도 없으면 오류(종료 코드 1)로 정했다. PDF 는 "조건 기반 검색"만 말하고 조건 없는 경우를 정하지 않았다. 대안은 "전체 거래를 최신순으로 모두 출력"인데, 그러면 3.3의 메모리 한계가 파일 전체가 된다.
2. **`--from` > `--to`**: 따로 검사하지 않고 AND 조건 그대로 "조건에 맞는 거래가 없습니다."(종료 코드 0)로 정했다(가장 단순한 해석). 오류로 막기를 원하면 알려 달라(4단계 export 의 `--from/--to` 와도 맞춰야 함).
3. **미등록 `--category` 로 검색**: 1장 입력 검증 "등록되지 않은 category 거부"를 그대로 적용해 오류(1)로 정했다. 대안은 "결과 없음"(0). 사용 중인 카테고리는 삭제가 막혀 있으므로 미등록 카테고리의 거래는 정상 데이터에 없다.
4. **`--q`/`--tag` 비교 방식**: 둘 다 앞뒤 공백 제거, **대소문자 구분**. `--q` 는 메모 부분 일치, `--tag` 는 태그 하나와 정확히 일치(쉼표가 든 값은 나누지 않아 결과 없음). 빈 값은 오류(1). PDF 근거가 없어 가장 단순한 비교를 택했다.
5. **search 메모리 한계**: 매칭 결과만 메모리에 모아 정렬하므로 메모리가 매칭 수에 비례한다(파일 전체 크기와는 무관). 매칭 수와 무관하게 메모리를 고정하려면 외부 정렬(`tempfile` + `heapq.merge`)이 필요하다(3.3 표). 현재 설계로 괜찮은지 확인이 필요하다.
6. **summary 세부 출력**: `--top` 기본값 3(PDF 예시값), 동점은 카테고리 이름 오름차순, 사용률은 소수 첫째 자리 반올림(half-up), "초과"는 지출 > 예산(100.0% 는 경고 없음), 경고 문구 `[경고] 예산을 초과했습니다` 는 stdout·종료 코드 0, 데이터 없는 달은 `{month} 데이터 없음` 에 예산이 있으면 `사용률 0.0%` 줄 추가, 지출이 없는 달은 `지출 내역 없음`. 모두 PDF 예시 형식에 맞춘 선택이며 문구는 바꿀 수 있다.
